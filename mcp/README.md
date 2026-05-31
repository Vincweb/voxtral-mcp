# voxtral-mcp

Local voice for any MCP client (Claude Code, Claude Desktop, Cursor, etc.) via
[Mistral Voxtral 4B TTS](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603)
(MLX 4-bit). Higher voice quality than the lightweight pocket-tts route, at the
cost of a larger model and slower TTFA.

- 9 languages: 🇬🇧 English, 🇫🇷 French, 🇩🇪 German, 🇪🇸 Spanish, 🇮🇹 Italian, 🇵🇹 Portuguese, 🇳🇱 Dutch, 🇮🇳 Hindi, 🇸🇦 Arabic
- 4 B parameters, 4-bit MLX quantization (~2.5 GB on disk)
- ~2.4× real-time generation on Apple Silicon M-series
- **TTFA ~2 s** thanks to native streaming via `mlx-audio` `stream=True`
- Non-blocking `speak()`, gap-free playback via `sounddevice` write-mode
- ~3 GB resident RAM once the model is loaded

> ⚠️ **Licence**: the Voxtral model itself is distributed by Mistral under
> **CC BY-NC 4.0** — non-commercial use only. This wrapper's code is MIT.

## Requirements

- **macOS Apple Silicon** (M1/M2/M3/M4) — required, MLX doesn't run on Intel
- **≥16 GB RAM** recommended (the 4-bit model keeps ~3 GB resident)
- Python 3.10 – 3.13

## Install

```bash
uvx voxtral-mcp --help
```

Or persistent:

```bash
uv tool install voxtral-mcp
```

Then add to your MCP client's `.mcp.json`:

```json
{
  "mcpServers": {
    "voxtral": {
      "command": "uvx",
      "args": ["voxtral-mcp"]
    }
  }
}
```

## MCP tools

| Tool | Purpose |
|---|---|
| `speak(text, voice?, interrupt?)` | Generate audio for `text` and queue it for background playback. Returns immediately, streaming generation. By default, calls queue and play sequentially (including across turns). Pass `interrupt=True` to abort current playback and clear the queue first. |
| `stop_speaking()` | Stop current playback, drop queue, cancel in-flight generation. Use for explicit "mute" requests. For mid-turn interruption + new speech, use `speak(..., interrupt=True)` instead. |
| `status()` | Report model load state, queue depths, sample rate, last error. |

## Configuration

All env vars (in the `env` block of `.mcp.json`):

| Variable | Default | Notes |
|---|---|---|
| `VOXTRAL_MODEL` | `mlx-community/Voxtral-4B-TTS-2603-mlx-4bit` | Any Voxtral MLX model on HF (4-bit / 6-bit / bf16) |
| `VOXTRAL_STREAMING_INTERVAL` | `2.0` | Approx. seconds of audio per streaming chunk |
| `VOXTRAL_MAX_TOKENS` | `4096` | Generation cap (in audio tokens, not characters) |
| `VOXTRAL_SAMPLE_RATE` | `24000` | Output sample rate |

## Voices

Voxtral ships with **20 preset voices** across 9 languages. A non-exhaustive
sample:

| Language | Voices |
|---|---|
| English | `casual_male`, `casual_female`, `cheerful_female`, `neutral_male`, `neutral_female` |
| French | `fr_male`, `fr_female` |
| Spanish | `es_male`, `es_female` |
| German | `de_male`, `de_female` |
| Italian | `it_male`, `it_female` |
| Portuguese | `pt_male`, `pt_female` |
| Dutch | `nl_male`, `nl_female` |
| Arabic | `ar_male` |
| Hindi | `hi_male`, `hi_female` |

Pass `voice="fr_female"` in your `speak()` call to switch.

## Claude Code users

If you're on Claude Code (CLI, desktop, or via Cursor), install the bundled
plugin (MCP wiring + `/voice-mode` skill) in one shot:

```
/plugin marketplace add Vincweb/voxtral-mcp
/plugin install voxtral@vincweb-tools
```

See the [main repo](https://github.com/Vincweb/voxtral-mcp) for architecture
details and a side-by-side comparison with
[kyutai-tts-mcp](https://github.com/Vincweb/kyutai-tts-mcp) (smaller / faster
TTFA / permissive licence).

## License

MIT for this wrapper. The underlying Voxtral model is **CC BY-NC 4.0**
(non-commercial) — see [Mistral](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603).
