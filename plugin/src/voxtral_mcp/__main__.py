"""MCP server wrapping Mistral Voxtral 4B TTS via mlx-audio.

The model loads in-process on first speak() call (~3-5 s) and stays in RAM.
Audio plays through a background queue + thread, so speak() returns as soon
as the WAV is generated.
"""
import atexit
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from mcp.server.fastmcp import FastMCP

MODEL_ID = os.environ.get("VOXTRAL_MODEL", "mlx-community/Voxtral-4B-TTS-2603-mlx-4bit")

mcp = FastMCP("voxtral")

# Lazy-loaded TTS model. None until first speak() call.
_model: Any = None
_model_lock = threading.Lock()
_model_load_error: str | None = None

# Playback queue: speak() generates the WAV synchronously then enqueues the
# temp file path for a background thread to play sequentially via afplay.
_play_queue: "queue.Queue[str | None]" = queue.Queue()
_player_thread: threading.Thread | None = None
_player_lock = threading.Lock()
_current_play_proc: subprocess.Popen | None = None
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


def _ensure_player() -> None:
    global _player_thread
    if _player_thread is None or not _player_thread.is_alive():
        _player_thread = threading.Thread(target=_player_loop, daemon=True)
        _player_thread.start()


def _drain_queue() -> int:
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


def _cleanup() -> None:
    with _player_lock:
        if _current_play_proc and _current_play_proc.poll() is None:
            _current_play_proc.terminate()
    _drain_queue()


atexit.register(_cleanup)


def _generate_wav(text: str, voice: str | None) -> tuple[str, dict]:
    """Run Voxtral and return (wav_path, metadata)."""
    import mlx.core as mx
    model = _ensure_model()
    kwargs: dict[str, Any] = {"text": text}
    if voice:
        kwargs["voice"] = voice
    chunks = list(model.generate(**kwargs))
    if not chunks:
        raise RuntimeError("voxtral returned no audio chunks")
    audio_arr = None
    for c in chunks:
        a = getattr(c, "audio", None) or getattr(c, "samples", None)
        if a is None:
            continue
        if isinstance(a, mx.array):
            a = np.array(a)
        audio_arr = a if audio_arr is None else np.concatenate([audio_arr, a])
    if audio_arr is None:
        raise RuntimeError("voxtral chunks contained no audio data")

    last = chunks[-1]
    sample_rate = getattr(last, "sample_rate", 24000)
    if isinstance(sample_rate, str):
        sample_rate = int(sample_rate)

    meta = {
        "audio_duration": getattr(last, "audio_duration", None),
        "real_time_factor": getattr(last, "real_time_factor", None),
        "processing_time_seconds": getattr(last, "processing_time_seconds", None),
        "sample_rate": sample_rate,
    }

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    sf.write(wav_path, audio_arr, sample_rate)
    return wav_path, meta


@mcp.tool()
def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud through Mistral Voxtral 4B TTS (local, Apple Silicon MLX).

    Returns as soon as the WAV is generated (~2-5 s for a typical sentence,
    longer on first call due to model load); audio plays in a background
    thread so you can continue working. Multiple speak() calls queue and
    play sequentially — they never overlap.

    Use `stop_speaking()` at the start of a new conversational turn to drop
    any audio still queued from the previous turn.

    Args:
        text: Text to read aloud. Supports French, English, German, Spanish,
              Italian, Portuguese, Dutch, Hindi, Arabic.
        voice: Optional voice preset name (e.g. "casual_male"). Defaults to
               the model's built-in voice.
    """
    _ensure_player()
    wav_path, meta = _generate_wav(text, voice)
    _play_queue.put(wav_path)
    dur = meta.get("audio_duration") or "?"
    rtf = meta.get("real_time_factor")
    rtf_str = f"{rtf:.1f}x" if isinstance(rtf, (int, float)) else "?"
    return (
        f"queued {len(text)} chars (voice={voice or 'default'}, "
        f"audio_duration={dur}, real_time_factor={rtf_str}, "
        f"queue depth ~{_play_queue.qsize()})"
    )


@mcp.tool()
def stop_speaking() -> str:
    """Stop the currently-playing audio and drop any audio queued behind it.

    Call this at the start of a new conversational turn if a previous turn's
    spoken summary may still be playing — it prevents the user from hearing
    audio that no longer matches what's on screen.
    """
    with _player_lock:
        killed = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
        if killed:
            _current_play_proc.terminate()
    dropped = _drain_queue()
    return f"dropped {dropped} queued, {'killed' if killed else 'no'} current"


@mcp.tool()
def status() -> dict:
    """Report model load state, queue depth, and last playback/load errors."""
    with _player_lock:
        playing = (
            _current_play_proc is not None
            and _current_play_proc.poll() is None
        )
    return {
        "model_id": MODEL_ID,
        "model_loaded": _model is not None,
        "model_load_error": _model_load_error,
        "queue_depth": _play_queue.qsize(),
        "currently_playing": playing,
        "last_error": _last_error,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
