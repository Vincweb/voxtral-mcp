# voxtral-mcp

Local voice for Claude Code on macOS Apple Silicon, via [Mistral Voxtral 4B
TTS](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603) (MLX 4-bit
quantization). Higher voice quality than the lightweight pocket-tts route,
at the cost of a larger model and slower TTFA.

- 9 languages: 🇬🇧 English, 🇫🇷 French, 🇩🇪 German, 🇪🇸 Spanish, 🇮🇹 Italian, 🇵🇹 Portuguese, 🇳🇱 Dutch, 🇮🇳 Hindi, 🇸🇦 Arabic
- 4 B parameters, 4-bit MLX quantization (~2.5 GB on disk)
- ~2.4× real-time generation on Apple Silicon M-series
- **TTFA ~2 s** thanks to native streaming via `mlx-audio` `stream=True`
- Non-blocking `speak()`, gap-free playback via `sounddevice` write-mode
- Bundled `/voice-mode` skill — Claude speaks summaries of its answers automatically
- Same plugin architecture as [`pocket-tts-mcp`](https://github.com/Vincweb/pocket-tts-mcp) v0.4.0

> 💡 Companion plugin: [**pocket-tts-mcp**](https://github.com/Vincweb/pocket-tts-mcp)
> wraps Kyutai Pocket TTS (smaller voice quality but ~10× faster TTFA and a
> third of the RAM). See the [comparison table](#voxtral-mcp-vs-pocket-tts-mcp)
> below — both plugins share the same MCP API and `/voice-mode` skill.

> ⚠️ **Licence**: the Voxtral model itself is distributed by Mistral under
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

The script `uv sync`'s the venv (≈500 MB with mlx-audio + transformers +
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

The first `speak()` after a Claude Code restart takes ~3–5 s (model load).
Subsequent calls have **~2 s TTFA** thanks to native streaming — you hear the
start of long narrations almost immediately while the rest is still being
generated.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `speak(text, voice?)` | Generate audio for `text` and queue for background playback. Returns immediately; streaming generation feeds the audio stream while you keep working. Multiple calls queue and play sequentially — no overlap. |
| `stop_speaking()` | Stop the currently-playing audio, drop everything queued behind it, and cancel any in-flight generation. Use at the start of a new turn to clear stale audio. |
| `status()` | Report model load state, sample rate, queue depths, last error. |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `VOXTRAL_MODEL` | `mlx-community/Voxtral-4B-TTS-2603-mlx-4bit` | Any Voxtral MLX model on HF (4-bit / 6-bit / bf16) |
| `VOXTRAL_STREAMING_INTERVAL` | `2.0` | Approx. seconds of audio per streaming chunk |
| `VOXTRAL_MAX_TOKENS` | `4096` | Generation cap (in audio tokens, not characters) |
| `VOXTRAL_SAMPLE_RATE` | `24000` | Output sample rate |

## Voices

Voxtral ships with **20 preset voices** across 9 languages:

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

Pass `voice="fr_female"` etc. in your `speak()` call, or ask Claude to "use
the cheerful female voice" — the active voice-mode skill picks up the
intent.

## Architecture (v0.4.0)

```
Claude Code  ──MCP stdio──▶  voxtral-mcp (Python, FastMCP)
                                  │
                                  │  speak(text)
                                  ▼
                              gen queue
                                  │
                                  ▼
                       generation thread
                            model.generate(stream=True, streaming_interval=2.0)
                            yields mx.array chunks
                                  │
                                  ▼
                          audio_q (numpy float32)
                                  │
                                  ▼
                       writer thread → stream.write() blocking
                                  │
                                  ▼
                       sounddevice OutputStream (write-mode)
                                  │
                                  ▼
                              CoreAudio
```

Key design choices:

- **In-process model**: Voxtral is loaded directly via
  `mlx_audio.tts.utils.load()`. No external daemon, no HTTP, no temp WAVs,
  no `afplay` subprocess.
- **Native streaming**: chunks are produced incrementally via
  `model.generate(stream=True, streaming_interval=2.0)` — first audible
  audio in ~2 s regardless of total text length.
- **Write-mode sounddevice**: the OutputStream is opened WITHOUT a
  callback, so a Python writer thread calls `stream.write(chunk)` in
  blocking mode. PortAudio's internal buffer absorbs all timing variation
  — yielding clean, gap-free playback (no crackles, no callback/GIL
  races).

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

## Versioning

| Version | Highlights |
|---|---|
| **0.4.0** | Switch from callback to write-mode sounddevice — kills the initial crackle that plagued earlier versions. Python never runs in PortAudio's realtime thread, so no more GIL-induced buffer underruns. |
| 0.3.2     | Bumped FADE_IN to 80 ms + trimmed first 30 ms of each generation to mask decoder warm-up (didn't fully solve it). |
| 0.3.1     | Lazy stream open + 10 ms fade-in (insufficient). |
| 0.3.0     | Continuous OutputStream callback (introduced the crackle). |
| 0.2.0     | Streaming generation via `mlx-audio` `stream=True` (~2-second chunks). |
| 0.1.x     | Initial: non-streaming, full WAV + afplay. |

## voxtral-mcp vs pocket-tts-mcp

Both plugins ship with the same MCP API (`speak`, `stop_speaking`,
`status`), the same `/voice-mode` skill, and the same in-process Python +
sounddevice write-mode pipeline (v0.4.0 on both sides). They differ in the
model they wrap:

|   | **voxtral-mcp** | [**pocket-tts-mcp**](https://github.com/Vincweb/pocket-tts-mcp) |
|---|---|---|
| Model | Mistral Voxtral 4B | Kyutai Pocket TTS |
| Parameters | 4 B | ~100 M (40× smaller) |
| Voice quality | More natural prosody ⭐ | Synthetic but intelligible |
| **TTFA** (post-load) | ~2 s | ~80–200 ms |
| Generation speed | ~2.4× real-time | ~4–5× real-time |
| Resident RAM | ~3 GB | ~1 GB |
| Disk (model cache) | ~2.5 GB | ~1 GB |
| Apple Silicon required | Yes (MLX-only) | No (works on Intel too) |
| Languages | EN, FR, ES, DE, IT, PT, NL, HI, AR | EN, FR, ES, DE, IT, PT |
| Voices | 20 presets (gender × language) | 6 built-in + voice cloning from `.wav` |
| Model licence | CC BY-NC 4.0 (non-commercial) | Permissive (Kyutai) |
| Architecture | In-process via mlx-audio | In-process via PyTorch |

**When to pick which:**

- **voxtral-mcp** for long narration where the voice quality difference
  is audible (≥ 30 s of speech), Apple Silicon hardware, personal use OK
  with non-commercial licence.
- **pocket-tts-mcp** for snappy short summaries (TTFA matters more than
  prosody on 1–3 sentences), low RAM footprint, Intel Macs, multi-project
  workflows, or any commercial use.

You can install **both** plugins side-by-side — the MCP server names
differ (`voxtral` vs `pocket-tts`) so the tools won't collide. The shared
`/voice-mode` skill defaults to voxtral when both are available; you can
override at runtime by asking Claude to "use pocket-tts" or "use voxtral".

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
