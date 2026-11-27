# Upstream import procedure (proposal)

Status: **Proposal — requires ADR-005 accepted and explicit owner approval
before any step that writes to the remote.** Nothing here has been executed.
Date: 2026-11-27.

## Goal

Bring the selected upstream engine into SSTRE-Engine **with its full Git
history, licenses and notices intact**, without destructive operations on the
existing repository, so that later upstream changes can still be merged.

## Starting point (observed)

- SSTRE-Engine `main` @ `d17edbb`: one commit containing only `README.md`
  ("Serious Sam - The Raytraced encounter - Engine"). Not a GitHub fork.
- Upstream candidates have unrelated histories. Observed locally on
  2026-11-27: `sultim-t/Serious-Engine-RT` @ `0e7f223c19a28014b60d900878c28831db522120`
  (449 commits, pack ≈ 116 MiB, has `LICENSE`, `README.md`, `.gitattributes`
  and an empty `.gitmodules`); `tx00100xt/SeriousSamClassic-VK` @
  `510d36f901cbe883c56b155b53717e4efdeb6522` (311 commits, pack ≈ 50 MiB).
- **Both candidates already track Serious Engine data files**: the RT fork
  tracks `SE1_10.gro`; Classic-VK tracks `SE1_10b.gro` (TFE and TSE) and
  13 `.tex` files (demo/mod thumbnails). Their redistribution status is part
  of the licensing audit (RD-007). They are upstream history and must not be
  removed by rewriting history; whether to delete them in a normal commit is
  an owner/licensing decision.

## Known conflicts

- **`README.md`** exists in both histories and will conflict. Proposed
  resolution: keep the upstream `README.md` unchanged at the root (upstream
  documentation is preserved), and move the SSTRE description into
  [`docs/sstre/README.md`](./README.md), which already exists for this purpose.
  A short SSTRE note may later be added to the root README only if the owner
  prefers; it must not remove upstream content.
- **`.gitignore` / CI**: the umbrella's forbidden-file check
  (`scripts/validate_repo.py`) and the SSTRE `.gitignore` block `*.gro`/`*.tex`.
  They must **not** be applied as-is to this repository, or they would flag
  upstream files. No SSTRE `.gitignore` is added here before the import.

## Options

**Recommended sequence (lead, reconciling RD-001 and proposed ADR-005).** Proposed ADR-005 uses *two* upstreams: SeriousSamClassic-VK as the candidate main line, and Serious-Engine-RT as an unmodified reference for the RT backend port. This leads to the following order:

1. **Option B for both upstreams first.** Push the unmodified histories as namespaced reference branches, such as `upstream/classic-vk-main` @ `510d36f` and `upstream/rt-main` @ `0e7f223`. This step is purely additive. It lets Phase 1 build both candidates from the project's own repository.
2. **Option A for the main-line candidate only, after ADR-005 is accepted.** Merge with unrelated histories into an `import/…` branch, then open a PR into `main`.

Each step needs explicit owner approval before any push.

### A. Merge upstream with unrelated histories (recommended for the selected main line)

Preserves all upstream commits and the existing SSTRE commit; no force-push.

```sh
# in a fresh clone of SSTRE-Engine
git remote add upstream https://github.com/<upstream-owner>/<upstream-repo>.git
git fetch upstream
git switch -c import/upstream-<short-sha> upstream/<default-branch>
# Bring the existing SSTRE commit in as a second parent:
git merge --allow-unrelated-histories --no-ff origin/main
#   -> resolve README.md: keep upstream version (git checkout --ours README.md),
#      docs/sstre/ comes in without conflict
git commit -s
# Review locally: license files, headers, file count, no unintended changes
git push origin import/upstream-<short-sha>   # only after owner approval
# then open a PR into main for review
```

Notes:

- Branching from upstream and merging SSTRE `main` into it makes the upstream
  line the first parent, which keeps `git log --first-parent` readable along
  upstream history. The PR then merges into `main` as a normal fast-forward or
  merge commit — no history rewrite.
- Record the exact upstream commit in `docs/sstre/README.md` and later in the
  umbrella `release-pins.json` (`upstream` field).
- Keep the `upstream` remote for future merges; never push to it.

### B. Keep upstream as a separate branch, integrate later

Push the unmodified upstream history to a branch such as `upstream/main` in
SSTRE-Engine and do SSTRE work on top of it. Non-destructive, but making it the
default branch is a **repository settings change** that needs owner approval,
and the existing `main` would diverge. Useful if the owner wants a pristine
mirror branch in addition to option A.

### C. Recreate the repository as a GitHub fork

Gives a visible fork relationship and the upstream "sync fork" button, but
requires deleting or renaming the existing repository (destructive; loses its
issues/settings) because an existing repository cannot be converted into a
fork. **Not recommended**; listed only for completeness.

### D. Squash/subtree import without history

Rejected: loses upstream authorship and history, makes license provenance and
future merges harder, and contradicts the plan (§7: keep engine fork history
intact).

## Pre-import checklist

1. ADR-005 accepted; exact upstream repository, branch and commit recorded.
2. RD-007 has reviewed the upstream license, per-file headers and any bundled
   third-party code and data (including the `.gro`/`.tex` files noted above).
3. Owner approval recorded for: pushing the import branch, the README
   resolution, and (if option B) default-branch changes.
4. Upstream is treated as untrusted code: no build scripts, hooks or binaries
   from it are executed during the import; review happens by reading.
5. Large-file check: confirm no Git LFS pointers or oversized blobs that GitHub
   would reject (none expected; verify on the chosen commit).

## After import

- Add SSTRE-specific CI only for checks that actually run (for example a
  CMake configure/build once it is known to work), with pinned actions and
  read-only permissions.
- Keep all SSTRE documentation under `docs/sstre/`.
