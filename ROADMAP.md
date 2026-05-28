# Roadmap — voxtral-mcp

Current state: v0.4.2 published on GitHub. In-process model via mlx-audio,
native streaming via `stream=True`, write-mode sounddevice (fixed the
crackling). README and SKILL cleaned up; install order swapped to MCP-first.
No PyPI, no Docker, not submitted to any directory yet.

---

## 1. Publish on PyPI

**Why**: cleanest install UX — `uv tool install voxtral-mcp` everywhere.

**Effort**: ~20 min.

**Steps**:

1. Create PyPI + TestPyPI accounts, generate API token.
2. In `plugin/pyproject.toml`, add:
   - `readme = "README.md"`
   - `license = { text = "MIT" }`
   - `authors = [{ name = "Vincent Caudron", email = "vincent@volume7.io" }]`
   - `keywords = ["mcp", "tts", "voxtral", "mistral", "mlx", "claude", "voice"]`
   - `classifiers = [...]` (Beta, MIT, OS macOS, Python 3.10-3.13, Audio)
   - `[project.urls]` block (Homepage, Repository, Issues)
3. Verify name is free: `curl -sI https://pypi.org/pypi/voxtral-mcp/json` returns 404.
4. From `plugin/`: `uv build` then `uv publish --token "$PYPI_TOKEN"`.
5. Test: `uv tool install voxtral-mcp` → `voxtral-mcp --help`.

**Make sure to flag in the PyPI description** that this requires Apple
Silicon — pip won't enforce that automatically.

**Then**: update README to add the PyPI path. Heads-up to users that the
Voxtral model itself is CC BY-NC 4.0 (non-commercial) — keep this prominent
on the PyPI page too.

---

## 2. Docker image — **probably skip for this repo**

**Why not**: voxtral-mcp depends on MLX. MLX requires Apple Silicon. Docker
on macOS can't expose Apple Silicon GPU/Neural Engine to a container — so a
Docker image would either fall back to MLX CPU mode (very slow) or simply
fail.

The only viable Docker path would swap MLX for a PyTorch/transformers
backend, which is a different codebase. Out of scope.

**Recommendation**: leave Docker off the table here. Direct users to the
non-Apple-Silicon `mudler/voxtral-tts.c` or `second-state/voxtral_tts_rs`
projects if they need a portable Voxtral runtime.

---

## 3. Use mcp-submit to register on directories

**Why**: passive discoverability. Glama auto-indexes from GitHub (give it a
week); the long tail (mcp.so, mcpservers.org, Smithery, PulseMCP) needs
explicit submission. The OSS tool `mcp-submit` pushes to 10+ in one
command.

**Effort**: ~15 min.

**Worth it once**:

- Sample audio in the README so directories can preview the voice.
- PyPI install is live.

---

## 4. Make the repo more credible — minimum viable

Without overdoing it. Order by ROI:

- **Sample audio in the README** — host a 5-second `fr_female.wav` and a
  5-second `casual_male.wav` (English). For Voxtral specifically the
  quality differential vs cheaper TTS is the whole pitch — make it
  audible immediately.
- **Shields.io badges**: version, license (MIT), Python (3.10-3.13),
  platform (macOS only). The platform badge is important here — saves
  Linux users from cloning before realising it won't work.
- **CHANGELOG.md** generated from git log. The streaming-debug saga
  (0.3.0 → 0.3.1 → 0.3.2 → 0.4.0) is a good "this project actually went
  through real iteration" story.
- **Demo GIF or asciinema** of `/voice-mode` with Voxtral fr_female. The
  natural-prosody differential is hard to convey in text.
- **License callout** at the very top of the README — prominent so people
  understand non-commercial right away. Already in place.

Skip for now:

- ❌ Hugging Face Space demo — voxtral-mcp is local-only by design, a
  Space would defeat the point.
- ❌ Docs site (README is enough).
- ❌ Community Discord.

---

## Priority order

1. **PyPI publish** — unlocks the rest.
2. **Sample audio in README** — Voxtral's voice is the whole selling
   point; let people hear it without installing.
3. **mcp-submit run**.
4. **GH Actions OIDC release workflow** — once releases are routine.

---

## Open questions

- The voxtral model artifact (~2.5 GB) downloads from HF on first
  generate. Should we document this more prominently? People with slow
  connections might think the install hung.
- Worth adding voice-cloning examples to the README (export your own
  voice with `pocket-tts export-voice`, then use it here)? Cross-uses
  pocket-tts tooling, might confuse readers. Skip unless asked.
- Should we offer a 6-bit and bf16 variant via env var? Already supported
  via `VOXTRAL_MODEL` — just document the trade-off table in the README
  (4-bit = fast, bf16 = best quality, 6-bit = middle).
