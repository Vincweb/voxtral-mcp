"""MCP server wrapping Mistral Voxtral 4B TTS via mlx-audio.

The model loads in-process on first speak() call (~3-5 s) and stays in RAM.
Generation streams: chunks of ~2 s audio are produced by the model and
fed into a sounddevice OutputStream in *write mode* (no PortAudio
callback, so no GIL/real-time contention) — yielding clean, gap-free
playback from the first sample.
"""
import atexit
import os
import queue
import threading
from typing import Any

import numpy as np
import sounddevice as sd
from mcp.server.fastmcp import FastMCP

MODEL_ID = os.environ.get("VOXTRAL_MODEL", "mlx-community/Voxtral-4B-TTS-2603-mlx-4bit")
STREAMING_INTERVAL = float(os.environ.get("VOXTRAL_STREAMING_INTERVAL", "2.0"))
MAX_TOKENS = int(os.environ.get("VOXTRAL_MAX_TOKENS", "4096"))
SAMPLE_RATE = int(os.environ.get("VOXTRAL_SAMPLE_RATE", "24000"))

mcp = FastMCP("voxtral")

_model: Any = None
_model_lock = threading.Lock()
_model_load_error: str | None = None

# Audio queue: generation thread puts numpy chunks, writer thread pulls
# and calls _stream.write() in blocking mode. PortAudio's internal buffer
# handles all real-time concerns — Python never runs in the audio thread.
_audio_q: "queue.Queue[np.ndarray | None]" = queue.Queue()
_writer_thread: threading.Thread | None = None
_stream: sd.OutputStream | None = None
_stream_lock = threading.Lock()

# Generation queue (FIFO of speak requests).
_gen_q: "queue.Queue[tuple[str, str | None] | None]" = queue.Queue()
_gen_thread: threading.Thread | None = None
_cancel_event = threading.Event()
_gen_in_flight = threading.Event()

_last_error: str | None = None


def _ensure_model() -> Any:
    global _model, _model_load_error
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from mlx_audio.tts.utils import load as load_tts  # heavy import
            _model = load_tts(MODEL_ID)
            return _model
        except Exception as e:  # noqa: BLE001
            _model_load_error = f"{type(e).__name__}: {e}"
            raise


def _ensure_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is None or _stream.closed:
            _stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            _stream.start()
        elif _stream.stopped:
            _stream.start()


def _close_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is not None and not _stream.closed:
            try:
                _stream.abort()
                _stream.close()
            except Exception:  # noqa: BLE001
                pass
            _stream = None


def _writer_loop() -> None:
    global _last_error
    while True:
        chunk = _audio_q.get()
        if chunk is None:
            return
        if _cancel_event.is_set():
            continue  # drop the chunk — we're aborting
        try:
            stream = _stream
            if stream is None or stream.closed:
                continue
            stream.write(chunk)  # blocks until PortAudio has room
        except Exception as e:  # noqa: BLE001
            _last_error = f"writer: {type(e).__name__}: {e}"


def _ensure_writer() -> None:
    global _writer_thread
    if _writer_thread is None or not _writer_thread.is_alive():
        _writer_thread = threading.Thread(target=_writer_loop, daemon=True)
        _writer_thread.start()


def _to_float32(audio: Any) -> np.ndarray:
    import mlx.core as mx
    if isinstance(audio, mx.array):
        audio = np.array(audio)
    arr = np.asarray(audio).astype(np.float32, copy=False)
    if arr.ndim > 1:
        arr = arr.squeeze()
    return arr


def _generation_loop() -> None:
    global _last_error
    while True:
        req = _gen_q.get()
        if req is None:
            return
        text, voice = req
        _cancel_event.clear()
        _gen_in_flight.set()
        try:
            model = _ensure_model()
            kwargs: dict[str, Any] = {
                "text": text,
                "stream": True,
                "streaming_interval": STREAMING_INTERVAL,
                "max_tokens": MAX_TOKENS,
            }
            if voice:
                kwargs["voice"] = voice
            opened_stream = False
            for chunk in model.generate(**kwargs):
                if _cancel_event.is_set():
                    break
                audio = getattr(chunk, "audio", None)
                if audio is None:
                    audio = getattr(chunk, "samples", None)
                if audio is None:
                    continue
                if not opened_stream:
                    _ensure_stream()
                    _ensure_writer()
                    opened_stream = True
                _audio_q.put(_to_float32(audio))
        except Exception as e:  # noqa: BLE001
            _last_error = f"generation: {type(e).__name__}: {e}"
        finally:
            _gen_in_flight.clear()


def _ensure_gen_thread() -> None:
    global _gen_thread
    if _gen_thread is None or not _gen_thread.is_alive():
        _gen_thread = threading.Thread(target=_generation_loop, daemon=True)
        _gen_thread.start()


def _drain_audio_q() -> int:
    dropped = 0
    while True:
        try:
            x = _audio_q.get_nowait()
        except queue.Empty:
            return dropped
        if x is None:
            continue
        dropped += 1


def _drain_gen_q() -> int:
    dropped = 0
    while True:
        try:
            x = _gen_q.get_nowait()
        except queue.Empty:
            return dropped
        if x is None:
            continue
        dropped += 1


def _cleanup() -> None:
    _cancel_event.set()
    _drain_audio_q()
    _drain_gen_q()
    _close_stream()


atexit.register(_cleanup)


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Mistral Voxtral 4B TTS (local, Apple Silicon MLX).

    Returns immediately. The text is queued for streaming generation in a
    background thread, which emits chunks of ~2 s audio. A writer thread
    feeds each chunk into a continuous sounddevice OutputStream in blocking
    write mode — no PortAudio callback, so Python never runs in the audio
    realtime thread, and playback is gap-free and crackle-free.

    First audio is audible in ~2-3 s even for long texts. Multiple speak()
    calls queue and play sequentially.

    Use `stop_speaking()` at the start of a new conversational turn to drop
    any audio still playing/queued from the previous turn AND cancel any
    in-flight generation.

    Args:
        text: Text to read aloud. Supports French, English, German, Spanish,
              Italian, Portuguese, Dutch, Hindi, Arabic.
        voice: Optional voice preset name (e.g. "fr_male", "fr_female",
               "casual_male", "neutral_female"). Defaults to the model's
               built-in voice.
    """
    _ensure_gen_thread()
    _gen_q.put((text, voice))
    return (
        f"enqueued {len(text)} chars (voice={voice or 'default'}, "
        f"gen_pending={_gen_q.qsize()}, audio_buffer={_audio_q.qsize()})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio, drop pending audio chunks, AND
    cancel any in-flight generation.

    Call this at the start of a new conversational turn so the previous
    turn's audio doesn't bleed into the new one.
    """
    _cancel_event.set()
    dropped_gen = _drain_gen_q()
    dropped_audio = _drain_audio_q()
    # Discard PortAudio's internal buffer (sample data already handed off
    # to the soundcard but not yet played). abort() requires a restart of
    # the stream — _ensure_stream() will do that on the next speak().
    with _stream_lock:
        if _stream is not None and not _stream.closed:
            try:
                _stream.abort()
            except Exception:  # noqa: BLE001
                pass
    return (
        f"cancelled generation, dropped {dropped_audio} audio chunks "
        f"+ {dropped_gen} pending requests, aborted current playback"
    )


@mcp.tool()
def status() -> dict:
    """Report model load state, queue depths, and last error."""
    with _stream_lock:
        stream_active = (
            _stream is not None
            and not _stream.closed
            and not _stream.stopped
        )
    return {
        "model_id": MODEL_ID,
        "model_loaded": _model is not None,
        "model_load_error": _model_load_error,
        "streaming_interval_seconds": STREAMING_INTERVAL,
        "sample_rate": SAMPLE_RATE,
        "gen_pending": _gen_q.qsize(),
        "gen_in_flight": _gen_in_flight.is_set(),
        "audio_buffer": _audio_q.qsize(),
        "stream_active": stream_active,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
