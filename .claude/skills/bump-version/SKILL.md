---
name: bump-version
description: "Bump the version of voxtral-mcp across the three sync'd files (mcp/pyproject.toml, plugin/.claude-plugin/plugin.json, .claude-plugin/marketplace.json), then commit + tag locally. Activate via /bump-version or 'bump version' / 'bump patch' / 'bump minor' / 'bump major'. Does NOT push or create a GitHub release — those stay manual."
---

# Bump version

Automates the version bump for `voxtral-mcp`. Three files have to move together
or `/plugin install` / marketplace sync goes weird. This skill does the boring
edit + commit + tag dance from the project root.

## What this skill does

1. Reads the **current version** from `mcp/pyproject.toml`.
2. Verifies the three files are **in sync** (same version everywhere). If they
   diverge, **stop and flag it** — don't bump on top of a broken state.
3. Determines the bump type (major / minor / patch). If the user said
   "bump version" without a qualifier, ask which one (default: patch).
4. Computes the new version using semver.
5. Asks the user for a **short one-line description** of what's in this
   release (used as the commit message subject).
6. Edits all three files atomically. Optionally adds a row to the
   README "Versioning" table — ask the user first; skip for trivial bumps.
7. Shows `git diff --stat` so the user sees exactly what changed.
8. **Commits** with message `vX.Y.Z: <description>` plus the standard
   `Co-Authored-By` trailer.
9. **Tags** with `git tag -a vX.Y.Z -m "vX.Y.Z"`.
10. Prints the **next manual commands** the user needs to run (push +
    `gh release create`) — never run them yourself.

## Files to edit

These three MUST stay in lockstep on every bump:

| Path | Field |
|---|---|
| `mcp/pyproject.toml` | `version = "x.y.z"` |
| `plugin/.claude-plugin/plugin.json` | `"version": "x.y.z"` |
| `.claude-plugin/marketplace.json` | inside `plugins[0].version`, `"version": "x.y.z"` |

The Versioning table in `README.md` (under `## Versioning`) gets a new
row only for notable releases (new features, breaking changes, perf wins).
For pure bugfix / chore releases, skip the README edit.

## Bump semantics (semver, pre-1.0 caveat)

- **major** (`0.5.0` → `1.0.0`): breaking changes when ≥ 1.0. Pre-1.0,
  we can put breaking changes in **minor** (as suggested by semver § 4).
- **minor** (`0.5.0` → `0.6.0`): new features, possibly breaking pre-1.0.
- **patch** (`0.5.0` → `0.5.1`): bugfixes, doc tweaks, dependency bumps.

When uncertain and the user didn't specify, ask once. Default to patch.

## Hard rules

- ❌ **Don't push** (`git push`). The user does that themselves.
- ❌ **Don't create the GitHub release** (`gh release create ...`). The user
  does that themselves — it's what triggers the OIDC publish workflow.
- ❌ **Don't amend** an existing commit. Always create a new commit.
- ❌ **Don't bump** if the working tree is dirty with unrelated changes —
  flag it and let the user commit / stash first.
- ❌ **Don't bump** if the three files are out of sync — say what the
  versions are and let the user reconcile manually.
- ✅ **Do verify** the final state after the bump with one `git status` +
  `git log --oneline -2`.

## Quick walkthrough

User: `/bump-version minor`

1. Read `mcp/pyproject.toml` → current = `0.5.0`. Confirm all three files
   show `0.5.0`. Working tree is clean.
2. Compute new version = `0.6.0`.
3. Ask: "What's in this release? (one-line description for the commit
   subject)"
4. User: "added voice presets list to status()"
5. Edit the three files. Show diff stat.
6. Ask: "Notable enough to add a row in the README Versioning table?"
7. User says yes → add a row like:
   ```
   | **0.6.0** | <description, ~one sentence>. |
   ```
8. Commit:
   ```
   git commit -am "v0.6.0: added voice presets list to status()

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
   ```
9. Tag:
   ```
   git tag -a v0.6.0 -m "v0.6.0"
   ```
10. Print:
    ```
    Done. Next steps (manual):
      git push origin main
      git push origin v0.6.0
      gh release create v0.6.0 --generate-notes
    The release creation triggers .github/workflows/publish.yml → PyPI via OIDC.
    ```

## When to refuse / escalate

- Working tree dirty with unrelated files → stop, list them, ask the user
  to commit or stash first.
- Three version files disagree → stop, show all three versions, let the
  user pick the source of truth.
- Bump skipping versions (e.g. patch should go 0.5.0 → 0.5.1, never
  0.5.0 → 0.5.3 — that's a user error worth flagging).
