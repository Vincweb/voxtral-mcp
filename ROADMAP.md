# Roadmap — voxtral-mcp

Current state: **v0.5.0 — ready for first PyPI release.** Repo split into
`mcp/` (Python package, fully metadated for PyPI) and `plugin/` (Claude Code
marketplace plugin). `.mcp.json` switched to `uvx voxtral-mcp`. GH Actions
workflow publishes via OIDC Trusted Publishing on release creation — no
long-lived token to manage. `install.sh` retired. `speak(interrupt=True)`
replaces the always-`stop_speaking()`-first pattern; SKILL.md updated to
match.

Done since the previous iteration: repo restructure, `mcp/README.md`,
PyPI metadata, OIDC release workflow, `speak(interrupt=)`, bump-version
maintainer skill.

Pending one-shot: **trigger the first PyPI publish.** Steps:

1. Verify name is free on PyPI: `curl -sI https://pypi.org/pypi/voxtral-mcp/json` → 404.
2. Create the `pypi` GH environment under repo settings → Environments
   (so OIDC has somewhere to attach to). No secrets needed; OIDC handles auth.
3. On [PyPI Trusted Publishers](https://pypi.org/manage/account/publishing/),
   register the workflow: repo `Vincweb/voxtral-mcp`, workflow `publish.yml`,
   env `pypi`.
4. `gh release create v0.5.0 --generate-notes` → workflow fires.
5. Smoke-test: `uvx voxtral-mcp --help` from a clean machine (or
   `uv cache clean voxtral-mcp` first).

---

## 1. Docker image — **probably skip for this repo**

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

## 2. Use mcp-submit to register on directories

**Why**: passive discoverability. Glama auto-indexes from GitHub (give it a
week post-PyPI); the long tail (mcp.so, mcpservers.org, Smithery, PulseMCP)
needs explicit submission. The OSS tool `mcp-submit` pushes to 10+ in one
command.

**Effort**: ~15 min.

**Worth it once**:

- Sample audio in the README so directories can preview the voice.
- PyPI install is live.

---

## 3. Make the repo more credible — minimum viable

Without overdoing it. Order by ROI:

- **Sample audio in the README** — host a 5-second `fr_female.wav` and a
  5-second `casual_male.wav` (English). For Voxtral specifically the
  quality differential vs cheaper TTS is the whole pitch — make it
  audible immediately.
- **Shields.io badges**: PyPI version, license (MIT), Python (3.10-3.13),
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

1. **First PyPI publish** — workflow is in place, just needs the GH
   release to fire.
2. **Sample audio in README** — Voxtral's voice is the whole selling
   point; let people hear it without installing.
3. **mcp-submit run**.

---

## Open questions

- The voxtral model artifact (~2.5 GB) downloads from HF on first
  generate. Should we document this more prominently? People with slow
  connections might think the install hung.
- Worth adding voice-cloning examples to the README (export your own
  voice with `kyutai-tts-mcp extract-voice`, then use it here)? Cross-uses
  kyutai-tts tooling, might confuse readers. Skip unless asked.
- Should we offer a 6-bit and bf16 variant via env var? Already supported
  via `VOXTRAL_MODEL` — just document the trade-off table in the README
  (4-bit = fast, bf16 = best quality, 6-bit = middle).
