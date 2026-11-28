# Patch-series tooling (`tools/sstre_patches.py`)

<!-- SPDX-FileCopyrightText: 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe -->
<!-- SPDX-License-Identifier: GPL-2.0-only -->

SSTRE-Engine publishes only SSTRE's own changes, as one patch series per upstream, against the commits pinned in [`upstream.lock.json`](../../upstream.lock.json) (SSTRE ADR-0008, backlog POC-27). `tools/sstre_patches.py` produces, checks and applies those series. It needs Python 3.10+ and git 2.33+, and uses only the standard library.

## Layout

- `upstream.lock.json`: one entry per upstream (`name`, `role` = `primary` / `secondary` / `dependency`, `repository`, full `commit` SHA, optional `swhid`, `patch_series` = `patches/<name>`).
- `patches/<name>/NNNN-<slug>.patch`: `git format-patch` output, numbered from `0001`, applied in file-name order.

## Commands

All commands take `--root` (default: this checkout) and `--cache` (default: `$SSTRE_UPSTREAM_CACHE`, otherwise `%LOCALAPPDATA%\sstre\upstream-cache` on Windows or `~/.cache/sstre/upstream-cache`).

| Command | What it does |
|---|---|
| `fetch [NAME...]` | Creates a bare cache repository per upstream and fetches **only the pinned commit** (`--depth 1` by default) from the lock's URL. It then verifies that the commit and its whole tree are present and that the `swhid` names the same commit. `--source NAME=PATH` fetches from an existing local clone instead. `--offline` forbids any network access (every upstream then needs a cache entry or `--source`). `--check-swh` also asks the Software Heritage API whether the revision is archived and whether its directory equals the git tree. |
| `apply [NAME...] --out DIR` | Adds a detached working tree at the pinned commit (`DIR/<name>`) and runs `git am --keep-cr` per patch. It then checks that there is one commit per patch, no merge and a clean tree, and prints the tree hash. Commits get a fixed committer (`SSTRE patch tool`) and the author date, so the resulting commit IDs are reproducible. `--expect-tree` fails on a different tree. |
| `export NAME --from BRANCH [--source-repo REPO]` | Formats the commits between the pin and `BRANCH` into `patches/<name>/` (see "Deterministic export"). The branch must be a single linear chain on top of the pin. The new series is checked in a temporary directory first; on any error the existing series is left unchanged. `--verify` runs the round trip afterwards. Context: `--unified N` (default 3) for ordinary files, `--flagged-context N` (default **1**) for files flagged by EXP-004, and `--path-context GLOB=N` (repeatable, first match wins) for any other path (see "Per-path context"). |
| `check [PATH...]` | Applies the content rules below to `patches/*/` (or to the given files or directories). `--validator <umbrella>/scripts/validate_repo.py` adds the umbrella's forbidden lists, which are read as data and never executed. |
| `verify NAME --from BRANCH` | Round trip: a fresh `apply` on the clean cached upstream, then a comparison of the tree hash with `BRANCH^{tree}`. This is the POC-27 acceptance test. |

Exit codes: `0` ok, `1` check or verification failure, `2` usage or environment error.

## Deterministic export

The export calls `git format-patch` with `--zero-commit --no-signature --full-index --no-numbered --no-thread --no-cover-letter --stat=72 --filename-max-length=64 --find-renames --diff-algorithm=myers --irreversible-delete --base=<pin>`. System and global git configuration are ignored (`GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_GLOBAL`), so the bytes do not depend on the developer's setup. Exporting the same branch twice gives identical files.

**Deletions** are exported with `--irreversible-delete`: a deleted file appears only as a header with its preimage blob ID, never as `-` lines. This matters because a full deletion hunk would republish the entire deleted (often third-party) file. Plain `git am` cannot apply such sections. `apply` therefore re-creates each full deletion locally with `git diff-tree`, from the blob in the pinned upstream, and refuses to apply if the blob ID in the patch does not match the file at that point. **Always apply with this tool, not with plain `git am`.**

## Per-path context

ADR-0008 item 4 asks for minimal context in patches that touch EXP-004 flagged files, because every context line reproduces an excerpt of such a file. `git format-patch` has a single `--unified` setting, so `export` re-generates the affected file sections afterwards: for each section whose path matches a rule (`--path-context` rules first, then `--flagged-context` for the flagged list), it runs `git diff-tree` on the same commit with the export's diff options and the rule's context. As a safety net it first re-generates the section with the default context and refuses (exit 2) unless that reproduces the `format-patch` bytes exactly. Commit message, diffstat and all other sections stay byte for byte; additions and content-free deletions carry no context and are left alone. Context must be at least 1 (`git am` cannot apply zero-context hunks). The rewritten sections are listed as `note:` lines. `check` reports the largest context run of each touched flagged file in its `--allow-flagged` warning, and hints at `--flagged-context 1` when it is larger than 1.

## Content rules (`check`)

Errors:

- binary patches (`GIT binary patch`, `Binary files … differ`) or NUL bytes;
- deletion sections that contain the removed content (re-export with the tool);
- added or modified files with a game-data, demo, audio or model-weight extension (the umbrella validator's `FORBIDDEN_EXTENSIONS`), or with a binary, archive, image or texture extension (`.exe .dll .lib .so .png .jpg .dds .ktx2 .zip …`);
- paths under `extracted/` or `workspace/`, `Demos/`, `Images/`, `Github/` (screenshots), `OverridenTextures/` or `Tools.Win32/` (SSTRE EXP-004 G3, G7–G9b, B1);
- changes to files flagged by the EXP-004 audit, unless reviewed and passed with `--allow-flagged`: TFE `Sources/Entities/**` (H6), `DSOUND.H` (H1), `LWSkaExporter/**` (H2), and the retail-identical game-root `Scripts/`, `Controls/`, `Help/`, `Data/` and `Mods/` (G4–G6). `export` gives such files 1 line of context by default (`--flagged-context`);
- `Signed-off-by` trailers (SSTRE commits never carry one), and trailers that are not in the source commit;
- submodule or symlink changes, abbreviated `index` lines, non-zero `From` lines, version signatures;
- file names other than `NNNN-<slug>.patch`, gaps in the numbering, series directories with no lock entry;
- patches larger than `--max-patch-kib` (default 1024 KiB).

Warnings:

- a deletion without content of a forbidden or flagged file. Removing such material is allowed and reproduces nothing, but it is reported;
- a modification that removes 500 or more upstream lines (the `-` lines reproduce them);
- a new file with no `SPDX-License-Identifier` in its first 30 lines.

## Typical workflow

```sh
python tools/sstre_patches.py fetch                       # online, from the lock URLs
# or, without network, from the local upstream imports:
python tools/sstre_patches.py fetch --offline --source classic-vk=<clone> --source serious-engine-rt=<clone>
python tools/sstre_patches.py export classic-vk --from <local branch> --source-repo <clone> --verify
python tools/sstre_patches.py check
python tools/sstre_patches.py apply --out build/upstream   # build from build/upstream/<name>
python -m unittest discover -s tools/tests -v              # synthetic tests, no network
```

CI (`.github/workflows/sstre-patches.yml`) runs the unit tests and `check`. It also fetches every upstream at its pin from GitHub and applies all series.
