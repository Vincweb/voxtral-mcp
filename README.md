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

> 💡 Companion plugin: [**kyutai-tts-mcp**](https://github.com/Vincweb/kyutai-tts-mcp)
> wraps Kyutai Pocket TTS (smaller voice quality but ~10× faster TTFA and a
> third of the RAM, runs on Intel too, permissive licence). See the
> [comparison table](#voxtral-mcp-vs-kyutai-tts-mcp) below — both plugins
> share the same MCP API and `/voice-mode` skill.

> ⚠️ **Licence**: the Voxtral model itself is distributed by Mistral under
> **CC BY-NC 4.0** — non-commercial use only. This wrapper's code is MIT.

## Requirements

- **macOS Apple Silicon** (M1/M2/M3/M4) — required, MLX doesn't run on Intel
- **≥16 GB RAM** recommended (the 4-bit model keeps ~3 GB resident)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Claude Code (CLI, desktop app, or Cursor extension)

## Install

### Option A — standalone MCP (works with any MCP client)

This is the universal path: a regular MCP server you wire into any client
that speaks the Model Context Protocol (Claude Desktop, Claude Code CLI,
Cursor's Claude Code extension, etc.).

Add this entry to the `mcpServers` block of your project's `.mcp.json`
(or `~/.claude.json` for a global install):

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

`uvx` pulls the package from [PyPI](https://pypi.org/project/voxtral-mcp/)
on first launch, caches the venv, and spawns the MCP. No clone, no local
install script. If you'd rather have the binary persistent in `~/.local/bin`,
`uv tool install voxtral-mcp` once and use `"command": "voxtral-mcp"` in
the JSON instead.

For other knobs (model variant, streaming interval, max tokens, sample
rate), see the [Configuration](#configuration) table below.

If you want the bundled `/voice-mode` skill (only relevant in Claude
Code / Cursor), also drop it in:

```bash
mkdir -p ~/.claude/skills/voice-mode
curl -sLo ~/.claude/skills/voice-mode/SKILL.md \
  https://raw.githubusercontent.com/Vincweb/voxtral-mcp/main/plugin/skills/voice-mode/SKILL.md
```

Then restart your MCP client.

### Option B — Claude Code plugin (recommended if you use Claude Code or Cursor)

If you're already on Claude Code (CLI, desktop, or the Cursor extension),
the plugin path bundles the MCP server, the `/voice-mode` skill, and the
wiring in one step:

```
/plugin marketplace add Vincweb/voxtral-mcp
/plugin install voxtral@vincweb-tools
```

Restart Claude Code. On first use, `uvx` pulls `voxtral-mcp` from
[PyPI](https://pypi.org/project/voxtral-mcp/) (~30 s) and the Voxtral
4-bit model downloads from Hugging Face (~2.5 GB, once). Subsequent runs
are instant.

> 💡 The plugin layer is a Claude Code feature; Cursor inherits it because
> it ships the Claude Code CLI. Claude Desktop (the native app) and
> non-Claude MCP clients don't expose `/plugin install` — use Option A
> there.

## Use

In any conversation, type **`/voice-mode`** or say **"parle-moi"** / **"voice mode"**.
Claude will:

- Reply with normal text (markdown, code, links — unchanged)
- Call `speak()` with a short spoken summary of the turn (1–3 sentences,
  audio plays in the background while Claude continues with other work)
- Let consecutive turns' audio queue and play sequentially — no choppy
  cuts mid-sentence. When you interrupt ("non", "wait"), Claude calls
  `speak(..., interrupt=True)` to abort and restart cleanly.
- Skip speaking pure code dumps / long diffs

Stop with **"mute"**, **"silence"**, **"stop talking"**, **"arrête de parler"**.

The first `speak()` after a Claude Code restart takes ~3–5 s (model load).
Subsequent calls have **~2 s TTFA** thanks to native streaming — you hear the
start of long narrations almost immediately while the rest is still being
generated.

## MCP tools exposed

| Tool | Purpose |
|---|---|
| `speak(text, voice?, interrupt?)` | Generate audio for `text` and **queue it for background playback**. Returns immediately; streaming generation feeds the audio stream while you keep working. By default, multiple calls queue and play sequentially — including across conversational turns. Pass `interrupt=True` to abort current playback and clear the queue first (use when the user has clearly interrupted). |
| `stop_speaking()` | Stop playback, drop the queue, cancel in-flight generation. Use when the user explicitly asked to be quiet ("mute" / "silence"). For mid-turn interruption where you still want to speak something new, use `speak(text, interrupt=True)` instead — it does both atomically. |
| `status()` | Report model load state, sample rate, queue depths, last error. |

## Configuration

All env vars (in the `env` block of `.mcp.json`):

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

## Architecture

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
voxtral-mcp/                             repo root
├── mcp/                                 the MCP server (published to PyPI)
│   ├── src/voxtral_mcp/                 Python source
│   ├── pyproject.toml                   declares mcp + mlx-audio + sounddevice deps
│   ├── README.md                        the PyPI page
│   └── uv.lock
├── plugin/                              the Claude Code plugin
│   ├── .claude-plugin/plugin.json       plugin manifest
│   ├── .mcp.json                        MCP wiring — launches `mcp/` via uvx
│   └── skills/voice-mode/SKILL.md       /voice-mode skill
├── .claude-plugin/
│   └── marketplace.json                 declares the marketplace
├── README.md
└── LICENSE
```

The two halves are independent: `mcp/` can be installed and used on its
own (Option A), and `plugin/` just declares how Claude Code should
discover and wire it up (Option B).

## Versioning

| Version | Highlights |
|---|---|
| **0.5.0** | **First PyPI release.** `uvx voxtral-mcp` / `uv tool install voxtral-mcp`. **`speak(interrupt=True)`** to abort current playback before speaking (replaces the always-`stop_speaking()`-first pattern — audio now queues across turns naturally). Repo split into `mcp/` (Python package) + `plugin/` (Claude Code wrapper); `install.sh` retired in favor of `uvx`. CI release workflow via OIDC Trusted Publishing. |
| 0.4.0     | **In-process model + native streaming + write-mode sounddevice.** Drops `afplay` and temp WAVs. Kills the initial crackle that plagued earlier versions. Python never runs in PortAudio's realtime thread, so no more GIL-induced buffer underruns. Mirrors the [kyutai-tts-mcp](https://github.com/Vincweb/kyutai-tts-mcp) v0.4.0 architecture. |
| 0.3.2     | Bumped FADE_IN to 80 ms + trimmed first 30 ms of each generation to mask decoder warm-up (didn't fully solve it). |
| 0.3.1     | Lazy stream open + 10 ms fade-in (insufficient). |
| 0.3.0     | Continuous OutputStream callback (introduced the crackle). |
| 0.2.0     | Streaming generation via `mlx-audio` `stream=True` (~2-second chunks). |
| 0.1.x     | Initial: non-streaming, full WAV + afplay. |

## voxtral-mcp vs kyutai-tts-mcp

Both plugins ship with the same MCP API (`speak`, `stop_speaking`,
`status`), the same `/voice-mode` skill, and the same in-process Python +
sounddevice write-mode pipeline. They differ in the model they wrap:

|   | **voxtral-mcp** | [**kyutai-tts-mcp**](https://github.com/Vincweb/kyutai-tts-mcp) |
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
- **kyutai-tts-mcp** for snappy short summaries (TTFA matters more than
  prosody on 1–3 sentences), low RAM footprint, Intel Macs, multi-project
  workflows, or any commercial use.

You can install **both** plugins side-by-side — the MCP server names
differ (`voxtral` vs `kyutai-tts`) so the tools won't collide. The shared
`/voice-mode` skill defaults to voxtral when both are available; you can
override at runtime by asking Claude to "use kyutai-tts" or "use voxtral".

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
uv cache clean voxtral-mcp   # drop the uvx-cached venv
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
