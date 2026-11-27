# SSTRE integration notes (SSTRE-Engine)

This directory holds **SSTRE-specific** notes for the engine repository. It is
kept separate from upstream files so that upstream merges stay clean and
upstream documentation, licenses and notices are never edited for project
purposes.

## Status (2026-11-27)

- **Distribution model: own patches against pinned upstream commits** (SSTRE ADR-0008, accepted provisionally by the owner on 2026-11-27). The pins are in [`../../upstream.lock.json`](../../upstream.lock.json). No upstream history or files are published here.
- **Engine direction:** SeriousSamClassic-VK is the primary baseline and Serious-Engine-RT the secondary upstream (SSTRE ADR-0005, provisional). The final selection depends on the Phase 1 build and rendering results.
- **Local development** happens on local branches based on the imported upstream histories. A local pre-push hook prevents publishing them.

## Role of this repository

Engine fork for SSTRE: rendering (ray/path tracing target, with a non-RT path
investigated for portability), TFE/TSE game compatibility, runtime, and later
platform ports. It **loads precompiled assets** produced by
[SSTRE-AssetCompiler](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE-AssetCompiler)
and must not depend on Python, ComfyUI, the
[Remaster-Toolkit](https://github.com/Handelsonderneming-S-D-Broekhoven/Remaster-Toolkit)
or any live inference service. Interfaces: SSTRE
[`docs/architecture/cross-repo-contracts.md`](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE/blob/main/docs/architecture/cross-repo-contracts.md).

## Licensing

Upstream engine code keeps its own license, copyright headers and notices, verbatim. SSTRE never relicenses engine code. The engine is **`GPL-2.0-only`** (all candidate upstreams; audited in SSTRE `docs/research/RD-007-licensing.md`), and SSTRE modifications to it are contributed under the same `GPL-2.0-only` terms, with the notice `Copyright © 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe` added for our own changes only. Existing third-party copyright notices are preserved unchanged. Because no upstream code is stored in this repository (ADR-0008), it carries its own `GPL-2.0-only` [`LICENSE`](../../LICENSE) for SSTRE's patches and files.


## Upstream and patches

See [upstream-import-procedure.md](./upstream-import-procedure.md). Its history-import options are **superseded for publication** by ADR-0008. They remain valid only for building local development branches.

## Planned contents of this directory (after import)

Only once there is something real to record:

- exact upstream repository, branch and commit the fork is based on;
- list of SSTRE changes relative to upstream, and their rationale;
- build instructions verified on the reference PC (with exact toolchain versions);
- how compiled SSTRE asset packages are located and loaded.

## Related repositories

- [SSTRE](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE) — umbrella, documentation, release pins
- [SSTRE-AssetCompiler](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE-AssetCompiler)
- [SSTRE-Manifests](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE-Manifests)
- [Remaster-Toolkit](https://github.com/Handelsonderneming-S-D-Broekhoven/Remaster-Toolkit)

Contribution guide: SSTRE
[CONTRIBUTING.md](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE/blob/main/CONTRIBUTING.md).
