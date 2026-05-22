# voxtral-mcp

Local voice for Claude Code on macOS Apple Silicon, via [Mistral Voxtral 4B
TTS](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603) (MLX 4-bit
quantization). Higher voice quality than the lightweight pocket-tts route,
at the cost of a larger model and slower generation.

- 9 languages: 🇬🇧 English, 🇫🇷 French, 🇩🇪 German, 🇪🇸 Spanish, 🇮🇹 Italian, 🇵🇹 Portuguese, 🇳🇱 Dutch, 🇮🇳 Hindi, 🇸🇦 Arabic
- 4 B parameters, 4-bit MLX quantization (~2.5 GB on disk)
- ~2–3× real-time generation on Apple Silicon M-series
- Non-blocking `speak()` — audio queues + plays in background while Claude keeps working
- Bundled `/voice-mode` skill — Claude speaks summaries of its answers automatically
- Same plugin architecture as [`pocket-tts-mcp`](https://github.com/Vincweb/pocket-tts-mcp), but with a larger model and no daemon subprocess

> **Licence**: the Voxtral model itself is distributed by Mistral under
> **CC BY-NC 4.0** — non-commercial use only. This wrapper's code is MIT.

## Requirements

- **macOS Apple Silicon** (M1/M2/M3/M4) — required, MLX doesn't run on Intel
- **≥16 GB RAM** recommended (the 4-bit model keeps ~3 GB resident)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Claude Code (CLI, desktop app, or Cursor extension)

## Install — option A: Claude Code plugin (recommended)

```
/plugin marketplace add Vincweb/voxtral-mcp
/plugin install voxtral@vincweb-tools
```

Restart Claude Code. On first use, `uv run` materializes the Python venv
(~30 s) and Voxtral's 4-bit model downloads from Hugging Face (~2.5 GB,
once). Subsequent runs are instant.

## Install — option B: standalone

```bash
git clone https://github.com/Vincweb/voxtral-mcp.git
cd voxtral-mcp/plugin
./install.sh
```

The script `uv sync`'s the venv (≈1.5 GB with mlx-audio + transformers +
mistral-common) and prints the `.mcp.json` snippet to paste into your
project. You'll also need to copy `plugin/skills/voice-mode/SKILL.md` to
`~/.claude/skills/voice-mode/SKILL.md`.

## Use

In any conversation, type **`/voice-mode`** or say **"parle-moi"** / **"voice mode"**.
Claude will:

- Reply with normal text (markdown, code, links — unchanged)
- Call `stop_speaking()` at the start of each turn to drop stale audio
- Call `speak()` with a short spoken summary (1–3 sentences, audio plays
  in background while Claude continues with other work)
- Skip speaking pure code dumps / long diffs

Stop with **"mute"**, **"silence"**, **"stop talking"**, **"arrête de parler"**.

The first `speak()` after a restart takes ~3–5 s (model load). Subsequent
calls take ~2–5 s of generation per turn (depends on text length), then
playback runs in the background.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `speak(text, voice?)` | Generate audio for `text` and queue for background playback. Returns as soon as the WAV is written. |
| `stop_speaking()` | Stop the currently-playing audio and drop everything queued behind it. |
| `status()` | Report model load state, queue depth, last error. |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `VOXTRAL_MODEL` | `mlx-community/Voxtral-4B-TTS-2603-mlx-4bit` | Any Voxtral MLX model on HF (4-bit / 6-bit / bf16) |

## Architecture

```
Claude Code  ──MCP stdio──▶  voxtral-mcp (Python, FastMCP)
                                  │
                                  │  speak(text)
                                  ▼
                            mlx-audio TTS load + generate
                            (Voxtral 4B in-process, MLX)
                                  │
                                  ▼
                            WAV file in /tmp
                                  │
                                  ▼
                            playback queue
                                  │
                                  ▼
                            player thread
                                  │
                                  ▼
                                afplay
```

Unlike [`pocket-tts-mcp`](https://github.com/Vincweb/pocket-tts-mcp) which
spawns a separate FastAPI daemon (`pocket-tts serve`), this MCP loads the
Voxtral model directly in-process via `mlx_audio.tts.utils.load()`. Trade-
offs:

- ✅ One less process to manage; cleaner shutdown
- ✅ No HTTP roundtrip per call
- ❌ Model lives in the MCP process — restarting the MCP reloads the model
  (~3-5 s). The pocket-tts daemon survives MCP restarts (until you Cmd+Q
  Cursor).

## Repo layout

```
voxtral-mcp/                             marketplace root
├── .claude-plugin/marketplace.json
├── plugin/                              plugin root
│   ├── .claude-plugin/plugin.json
│   ├── .mcp.json
│   ├── skills/voice-mode/SKILL.md
│   ├── src/voxtral_mcp/__main__.py
│   ├── pyproject.toml
│   ├── uv.lock
│   └── install.sh
├── README.md
└── LICENSE
```

## voxtral-mcp vs pocket-tts-mcp

| | voxtral-mcp | pocket-tts-mcp |
|---|---|---|
| Backend model | Voxtral 4 B, 4-bit MLX | Kyutai pocket-tts (~100 M params) |
| Voice quality | Higher (more natural prosody) | Lower (recognizably synthetic) |
| Generation speed (M-series) | ~2-3× real-time | ~4-5× real-time |
| Disk footprint | ~2.5 GB model + ~1.5 GB venv | ~1 GB model + ~600 MB venv |
| Apple Silicon required | Yes (MLX) | No (CPU PyTorch — runs on Intel too) |
| Language coverage | EN, FR, DE, ES, IT, PT, NL, HI, AR | EN, FR, ES, DE, IT, PT |
| Model licence | CC BY-NC 4.0 (Mistral) — non-commercial | Permissive (Kyutai) |
| Architecture | Model in-process | Separate FastAPI daemon |

Pick **voxtral-mcp** if voice quality matters and you're on Apple Silicon
for personal use. Pick **pocket-tts-mcp** if you want a smaller / faster /
more permissively-licensed setup.

## Uninstall

If installed as a plugin:
```
/plugin uninstall voxtral@vincweb-tools
/plugin marketplace remove vincweb-tools
```

If installed standalone:
```bash
rm -rf ~/.claude/skills/voice-mode
# Remove the "voxtral" entry from your project's .mcp.json
rm -rf ~/path/to/voxtral-mcp
# Optionally delete the cached model:
rm -rf ~/.cache/huggingface/hub/models--mlx-community--Voxtral-4B-TTS-2603-mlx-4bit
```

## Credits

- [Mistral AI](https://mistral.ai/) for Voxtral
- [mlx-community](https://huggingface.co/mlx-community) for the MLX-quantized variants
- [Blaizzy/mlx-audio](https://github.com/Blaizzy/mlx-audio) for the unified MLX audio library
- [Anthropic](https://anthropic.com/) for Claude Code & the MCP spec
- This wrapper: just glue

## License

MIT for this wrapper — see [LICENSE](LICENSE). The underlying Voxtral model
remains under **CC BY-NC 4.0** (non-commercial).
