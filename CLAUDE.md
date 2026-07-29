# CLAUDE.md

Maintainer notes for working *on* this repo. User-facing docs live in
[README.md](README.md) — don't duplicate them here. This file covers what
isn't obvious from reading the code.

## What this repo is

Two independent halves in one repo:

| Path | What | Ships as |
|---|---|---|
| `mcp/` | The Python MCP server (`speak` / `stop_speaking` / `status`) | PyPI package `voxtral-mcp` |
| `plugin/` | Claude Code plugin — manifest, `.mcp.json` wiring, `/voice-mode` skill | GitHub marketplace |

`plugin/.mcp.json` launches the server with plain `uvx voxtral-mcp`, i.e.
**from PyPI, unpinned**. Consequence: editing `mcp/src/` changes nothing for
an installed plugin until a new version is published. See *Releasing*.

All logic is in one 296-line file —
[mcp/src/voxtral_mcp/__main__.py](mcp/src/voxtral_mcp/__main__.py).

## Testing — there is no test suite

There are no unit tests, and importing the module proves little: the
failure modes live in the MCP handshake, the MLX model load, and CoreAudio.
Verify by driving stdio JSON-RPC yourself.

Note `main()` is just `mcp.run()` — there's **no argparse**, so
`voxtral-mcp --help` doesn't print help; the flag is swallowed and the
stdio server starts. It's still a useful import-level smoke test (exit 0
and no traceback), but nothing more.

For anything real, write a throwaway client that spawns `uv run voxtral-mcp`
(cwd `mcp/`) and speaks the protocol: `initialize` →
`notifications/initialized` → `tools/list` → `tools/call`. Two gotchas:

- **Don't pipe a static file into stdin.** EOF closes the server before it
  processes later requests. Keep stdin open and read responses line by line.
- **`speak()` returns immediately** — it only enqueues. To confirm audio
  actually rendered, poll `status()` until `gen_in_flight` is false and
  `audio_buffer` is 0, and check `last_error`. Then sleep a couple of
  seconds before closing stdin, or `atexit` aborts the PortAudio stream
  mid-tail.

Reaching the audio path is expensive here: the first `speak()` downloads
~2.5 GB from Hugging Face if cold and holds ~3 GB resident. Say so before
you trigger it, and prefer `tools/list` + `status()` for changes that don't
touch generation.

## Hard constraints

- **`mcp>=2.0.0`** — the SDK dropped `mcp.server.fastmcp` in 2.0; the class
  is `MCPServer` from `mcp.server.mcpserver`. `@mcp.tool()` and `mcp.run()`
  are unchanged. Never reintroduce a `FastMCP` import.
- **Apple Silicon only.** mlx-audio is MLX-backed; there is no CPU or CUDA
  fallback. Don't add a `device` knob pretending otherwise.
- **`requires-python = ">=3.10,<3.14"`**.
- **The model licence is CC BY-NC 4.0** (non-commercial) — unlike this
  wrapper's MIT. Don't describe the whole thing as freely usable
  commercially.
- `SAMPLE_RATE` is an env knob (`VOXTRAL_SAMPLE_RATE`, default 24000), *not*
  read back from the model. If it ever disagrees with what mlx-audio emits,
  playback skews rather than erroring.

## Threading invariants

Two long-lived daemon threads and two queues; breaking these produces
gaps, deadlocks, or audio that won't stop:

- `_gen_q` → generation thread → `_audio_q` → writer thread → OutputStream.
- The OutputStream is opened **without a callback**; the writer thread calls
  `stream.write()` in blocking mode so PortAudio absorbs all timing jitter
  and Python never runs in the audio realtime thread. Don't switch to
  callback mode.
- `_cancel_event` is checked in *both* loops. `_abort_all()` is the single
  path shared by `stop_speaking()` and `speak(interrupt=True)` — set the
  event, drain both queues, `stream.abort()`. Keep it that way rather than
  adding a second abort path.
- `_ensure_model` holds `_model_lock` across the heavy load on purpose —
  concurrent first-calls must not load twice.
- The generation loop reads chunks defensively: `chunk.audio`, falling back
  to `chunk.samples`, skipping when both are absent. That's absorbing
  mlx-audio API drift across versions — keep the fallback when touching it.
- `STREAMING_INTERVAL` (default 2.0 s) is the chunk size the model emits,
  and therefore roughly the TTFA floor. Lowering it trades latency for more
  frequent generate() turnarounds; it isn't free.

## Versioning & releasing

Three files must move together or `/plugin install` and marketplace sync
break:

- `mcp/pyproject.toml` → `version`
- `plugin/.claude-plugin/plugin.json` → `version`
- `.claude-plugin/marketplace.json` → `plugins[0].version`

Use the `/bump-version` skill ([.claude/skills/bump-version/SKILL.md](.claude/skills/bump-version/SKILL.md))
— it does the three-file edit, the commit, and the local tag. It refuses to
bump on a dirty tree or on out-of-sync versions.

Publishing is **two steps and the second is outward-facing**:

```bash
git push origin main && git push origin vX.Y.Z
gh release create vX.Y.Z --generate-notes   # ← triggers PyPI
```

Creating the GitHub release is what fires
[.github/workflows/publish.yml](.github/workflows/publish.yml), which builds
`mcp/` and publishes to PyPI over OIDC Trusted Publishing (no token in the
repo). PyPI versions are immutable — never publish without the user asking.

Regenerate `mcp/uv.lock` when dependency constraints change. Note that a
relock with a newer `uv` rewrites unrelated platform markers; that noise is
expected, `uv lock --check` is the thing to confirm.

## Conventions

- Conventional Commits (`feat(scope):`, `fix:`, `refactor:`, `docs:`,
  `chore:`, `ci:`), except version bumps which use `vX.Y.Z: <summary>`.
- **No `Co-Authored-By` trailer.** [.claude/settings.json](.claude/settings.json)
  sets `attribution.commit: ""`. History before that setting has trailers,
  and the `bump-version` skill still prescribes one — the setting wins;
  the skill text is stale on this point.
- `mcp/README.md` is the **PyPI landing page**, a condensed subset of the
  root README. When you change shared content (tool table, config table,
  install snippet), update both.
- The root README has a Versioning table — add a row for notable releases
  only, not for chores.
- [ROADMAP.md](ROADMAP.md) records deliberate *non*-goals. Check it before
  proposing those.

## Sibling project

[kyutai-tts-mcp](https://github.com/Vincweb/kyutai-tts-mcp) is the same
architecture around Kyutai Pocket TTS — smaller, faster TTFA, CPU-only,
permissively licensed — with an intentionally identical MCP API and a
shared `/voice-mode` skill. Differences that matter when porting a change:

- Kyutai caches **one model per language** and takes `language=` on
  `speak()`; here there's a single model and the language is implied by the
  voice preset.
- Kyutai derives its sample rate from the model; here it's an env knob.
- Kyutai has an `extract-voice` CLI subcommand (and hence argparse); this
  repo has no CLI surface at all.

API changes here usually want a matching change there, and vice versa.
