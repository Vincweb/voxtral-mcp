"""MCP server wrapping Mistral Voxtral 4B TTS via mlx-audio.

The model loads in-process on first speak() call (~3-5 s) and stays in RAM.
Generation streams: chunks of ~2 s audio are produced by the model and
fed directly into a continuous CoreAudio output stream via `sounddevice`
— no temp WAV files, no per-chunk `afplay` spawning, no gaps between
chunks. First audio is audible in ~2-3 s even for long texts.
"""
import atexit
import os
import threading
from collections import deque
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

# Continuous-playback architecture: the generation thread appends numpy
# chunks (float32) to a deque; the sounddevice OutputStream callback drains
# the deque sample-by-sample to fill the soundcard buffer, with no gaps
# between chunks.
_audio_chunks: deque = deque()
_remainder: np.ndarray | None = None  # carry-over between callback invocations
_stream: sd.OutputStream | None = None
_stream_lock = threading.Lock()

# Generation queue (FIFO of speak requests).
_gen_queue: "deque[tuple[str, str | None]]" = deque()
_gen_event = threading.Event()  # signals new requests
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


def _audio_callback(outdata: np.ndarray, frames: int, _time, _status) -> None:
    global _remainder
    pos = 0
    while pos < frames:
        if _remainder is None or _remainder.size == 0:
            try:
                _remainder = _audio_chunks.popleft()
            except IndexError:
                outdata[pos:, 0] = 0.0
                return
        take = min(frames - pos, _remainder.size)
        outdata[pos:pos + take, 0] = _remainder[:take]
        _remainder = _remainder[take:] if take < _remainder.size else None
        pos += take


def _ensure_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is None or _stream.closed:
            _stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=_audio_callback,
            )
            _stream.start()


def _close_stream() -> None:
    global _stream
    with _stream_lock:
        if _stream is not None and not _stream.closed:
            try:
                _stream.stop()
                _stream.close()
            except Exception:  # noqa: BLE001
                pass
            _stream = None


def _clear_audio() -> int:
    global _remainder
    n = len(_audio_chunks)
    _audio_chunks.clear()
    _remainder = None
    return n


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
        _gen_event.wait()
        try:
            req = _gen_queue.popleft()
        except IndexError:
            _gen_event.clear()
            continue
        if req is None:
            return

        text, voice = req
        _cancel_event.clear()
        _gen_in_flight.set()
        try:
            model = _ensure_model()
            _ensure_stream()
            kwargs: dict[str, Any] = {
                "text": text,
                "stream": True,
                "streaming_interval": STREAMING_INTERVAL,
                "max_tokens": MAX_TOKENS,
            }
            if voice:
                kwargs["voice"] = voice
            for chunk in model.generate(**kwargs):
                if _cancel_event.is_set():
                    break
                audio = getattr(chunk, "audio", None)
                if audio is None:
                    audio = getattr(chunk, "samples", None)
                if audio is None:
                    continue
                _audio_chunks.append(_to_float32(audio))
        except Exception as e:  # noqa: BLE001
            _last_error = f"generation: {type(e).__name__}: {e}"
        finally:
            _gen_in_flight.clear()


def _ensure_gen_thread() -> None:
    global _gen_thread
    if _gen_thread is None or not _gen_thread.is_alive():
        _gen_thread = threading.Thread(target=_generation_loop, daemon=True)
        _gen_thread.start()


def _cleanup() -> None:
    _cancel_event.set()
    _clear_audio()
    _close_stream()


atexit.register(_cleanup)


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Mistral Voxtral 4B TTS (local, Apple Silicon MLX).

    Returns immediately. The text is queued for streaming generation in a
    background thread, which emits chunks of ~2 s audio that play through
    a continuous sounddevice OutputStream — no gaps between chunks.
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
    _gen_queue.append((text, voice))
    _gen_event.set()
    return (
        f"enqueued {len(text)} chars (voice={voice or 'default'}, "
        f"gen_pending={len(_gen_queue)}, audio_buffer_chunks={len(_audio_chunks)})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio, drop pending audio chunks, AND
    cancel any in-flight generation.

    Call this at the start of a new conversational turn so the previous
    turn's audio doesn't bleed into the new one.
    """
    _cancel_event.set()
    # Drain pending generation requests.
    dropped_gen = len(_gen_queue)
    _gen_queue.clear()
    # Drain audio buffer (mid-flight chunks already produced).
    dropped_audio = _clear_audio()
    return (
        f"cancelled generation, dropped {dropped_audio} audio chunks "
        f"+ {dropped_gen} pending requests"
    )


@mcp.tool()
def status() -> dict:
    """Report model load state, queue depths, and last error."""
    with _stream_lock:
        stream_active = _stream is not None and not _stream.closed
    return {
        "model_id": MODEL_ID,
        "model_loaded": _model is not None,
        "model_load_error": _model_load_error,
        "streaming_interval_seconds": STREAMING_INTERVAL,
        "sample_rate": SAMPLE_RATE,
        "gen_pending": len(_gen_queue),
        "gen_in_flight": _gen_in_flight.is_set(),
        "audio_buffer_chunks": len(_audio_chunks),
        "stream_active": stream_active,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
