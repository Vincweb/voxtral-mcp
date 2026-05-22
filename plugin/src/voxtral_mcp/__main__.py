"""MCP server wrapping Mistral Voxtral 4B TTS via mlx-audio.

The model loads in-process on first speak() call (~3-5 s) and stays in RAM.
Generation streams: chunks of ~2 s audio are written to disk and queued for
playback as soon as they're produced, so the first audio plays in ~2-3 s
even for long texts.
"""
import atexit
import os
import queue
import subprocess
import tempfile
import threading
from typing import Any

import numpy as np
import soundfile as sf
from mcp.server.fastmcp import FastMCP

MODEL_ID = os.environ.get("VOXTRAL_MODEL", "mlx-community/Voxtral-4B-TTS-2603-mlx-4bit")
STREAMING_INTERVAL = float(os.environ.get("VOXTRAL_STREAMING_INTERVAL", "2.0"))
MAX_TOKENS = int(os.environ.get("VOXTRAL_MAX_TOKENS", "4096"))

mcp = FastMCP("voxtral")

# Lazy-loaded TTS model.
_model: Any = None
_model_lock = threading.Lock()
_model_load_error: str | None = None

# Playback queue: chunks of generated audio. Player thread plays them in order.
_play_queue: "queue.Queue[str | None]" = queue.Queue()
_player_thread: threading.Thread | None = None
_player_lock = threading.Lock()
_current_play_proc: subprocess.Popen | None = None

# Generation queue: pending speak() requests. Worker thread generates them
# sequentially (mlx is single-threaded on the GPU anyway).
_gen_queue: "queue.Queue[tuple[str, str | None] | None]" = queue.Queue()
_gen_thread: threading.Thread | None = None
_cancel_event = threading.Event()
_gen_in_flight = threading.Event()  # set while a generation is actively producing chunks

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


def _write_chunk_wav(audio: Any, sample_rate: int) -> str:
    import mlx.core as mx
    if isinstance(audio, mx.array):
        audio = np.array(audio)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    sf.write(wav_path, audio, sample_rate)
    return wav_path


def _generation_loop() -> None:
    global _last_error
    while True:
        req = _gen_queue.get()
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
            for chunk in model.generate(**kwargs):
                if _cancel_event.is_set():
                    break
                audio = getattr(chunk, "audio", None)
                if audio is None:
                    audio = getattr(chunk, "samples", None)
                if audio is None:
                    continue
                sr = getattr(chunk, "sample_rate", 24000)
                if isinstance(sr, str):
                    sr = int(sr)
                wav_path = _write_chunk_wav(audio, sr)
                _play_queue.put(wav_path)
        except Exception as e:  # noqa: BLE001
            _last_error = f"generation: {type(e).__name__}: {e}"
        finally:
            _gen_in_flight.clear()


def _player_loop() -> None:
    global _current_play_proc, _last_error
    while True:
        wav_path = _play_queue.get()
        if wav_path is None:
            return
        try:
            with _player_lock:
                _current_play_proc = subprocess.Popen(["afplay", wav_path])
            ret = _current_play_proc.wait()
            with _player_lock:
                _current_play_proc = None
            if ret not in (0, -15):  # -15 = SIGTERM from stop_speaking
                _last_error = f"afplay exited {ret} for {wav_path}"
        except Exception as e:  # noqa: BLE001
            _last_error = f"player thread error: {e}"
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _ensure_threads() -> None:
    global _player_thread, _gen_thread
    if _player_thread is None or not _player_thread.is_alive():
        _player_thread = threading.Thread(target=_player_loop, daemon=True)
        _player_thread.start()
    if _gen_thread is None or not _gen_thread.is_alive():
        _gen_thread = threading.Thread(target=_generation_loop, daemon=True)
        _gen_thread.start()


def _drain_play_queue() -> int:
    dropped = 0
    while True:
        try:
            wav = _play_queue.get_nowait()
        except queue.Empty:
            return dropped
        if wav is None:
            continue
        try:
            os.unlink(wav)
        except OSError:
            pass
        dropped += 1


def _drain_gen_queue() -> int:
    dropped = 0
    while True:
        try:
            req = _gen_queue.get_nowait()
        except queue.Empty:
            return dropped
        if req is None:
            continue
        dropped += 1


def _cleanup() -> None:
    _cancel_event.set()
    with _player_lock:
        if _current_play_proc and _current_play_proc.poll() is None:
            _current_play_proc.terminate()
    _drain_play_queue()
    _drain_gen_queue()


atexit.register(_cleanup)


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Mistral Voxtral 4B TTS (local, Apple Silicon MLX).

    Returns immediately. The text is queued for streaming generation in a
    background thread, which emits chunks of ~2 s audio that play through
    `afplay` as soon as they're produced. First audio is audible in ~2-3 s
    even for long texts. Multiple speak() calls queue and play sequentially.

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
    _ensure_threads()
    _gen_queue.put((text, voice))
    return (
        f"enqueued {len(text)} chars (voice={voice or 'default'}, "
        f"gen_pending={_gen_queue.qsize()}, play_queue={_play_queue.qsize()})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio, drop pending audio chunks, AND
    cancel any in-flight generation.

    Call this at the start of a new conversational turn so the previous
    turn's audio doesn't bleed into the new one.
    """
    _cancel_event.set()
    with _player_lock:
        killed = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
        if killed:
            _current_play_proc.terminate()
    dropped_play = _drain_play_queue()
    dropped_gen = _drain_gen_queue()
    return (
        f"cancelled generation, dropped {dropped_play} audio chunks "
        f"+ {dropped_gen} pending requests, {'killed' if killed else 'no'} current playback"
    )


@mcp.tool()
def status() -> dict:
    """Report model load state, queue depths, and last error."""
    with _player_lock:
        playing = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
    return {
        "model_id": MODEL_ID,
        "model_loaded": _model is not None,
        "model_load_error": _model_load_error,
        "streaming_interval_seconds": STREAMING_INTERVAL,
        "gen_pending": _gen_queue.qsize(),
        "gen_in_flight": _gen_in_flight.is_set(),
        "play_queue_depth": _play_queue.qsize(),
        "currently_playing": playing,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
