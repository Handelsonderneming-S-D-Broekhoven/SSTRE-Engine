# SSTRE integration notes (SSTRE-Engine)

This directory holds **SSTRE-specific** notes for the engine repository. It is
kept separate from upstream files so that upstream merges stay clean and
upstream documentation, licenses and notices are never edited for project
purposes.

## Status (2026-11-27)

- **No engine source has been imported.** The repository contains a single
  "Initial commit" with a README (`main` @ `d17edbb`). It is not a GitHub fork
  and has no upstream history.
- **The base engine is not chosen.** The decision is ADR-005 (engine
  foundation, *proposed*) in the SSTRE umbrella, informed by
  `docs/research/RD-001-engine-baseline.md`. Candidates under evaluation:
  - https://github.com/sultim-t/Serious-Engine-RT (primary candidate, ray tracing)
  - https://github.com/tx00100xt/SeriousSamClassic-VK (alternative foundation)
  - references: https://github.com/Croteam-official/Serious-Engine,
    https://github.com/sultim-t/Serious-Engine-Vk,
    https://github.com/sultim-t/RayTracedGL1
- Nothing builds or runs from this repository yet.

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

Upstream engine code keeps its own license, copyright headers and notices, verbatim. SSTRE never relicenses engine code. The engine is **`GPL-2.0-only`** (all candidate upstreams; audited in SSTRE `docs/research/RD-007-licensing.md`), and SSTRE modifications to it are contributed under the same `GPL-2.0-only` terms, with the notice `Copyright © 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe` added for our own changes only. Existing third-party copyright notices are preserved unchanged. No SSTRE license file is added before the upstream import, because the imported upstream `LICENSE` applies.


## Importing upstream

See [upstream-import-procedure.md](./upstream-import-procedure.md). The import
requires ADR-005 to be accepted and explicit owner approval.

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
