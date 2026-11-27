# SSTRE-Engine

Engine work for **SSTRE — Serious Sam: The Raytraced Encounter**, an unofficial, open-source modernization project. It is not affiliated with Croteam or Devolver Digital.

> **Status: Phase 1, technical validation.** Nothing here is a playable release. No engine binaries are distributed.

## How this repository works

This repository does **not** contain a copy of the engine. Per [SSTRE ADR-0008](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE/blob/main/docs/adr/0008-engine-patch-distribution.md) it contains only:

- [`upstream.lock.json`](upstream.lock.json): the upstream engine repositories and the exact commits SSTRE builds on:
  - **SeriousSamClassic-VK**, primary baseline;
  - **Serious-Engine-RT**, secondary upstream and the source of the ray-tracing backend.
- `patches/<upstream>/NNNN-*.patch`: SSTRE's own changes, applied in order with `git am`. This directory is created with the first patch.
- [`docs/sstre/`](docs/sstre/): integration notes and build instructions.

Upstream code is always fetched from its original host at the pinned commit. Both pinned commits are also archived by Software Heritage (SWHIDs are in the lock file).

## Licensing

SSTRE's patches and files in this repository are `GPL-2.0-only` ([`LICENSE`](LICENSE)), the same license as the upstream engine. Copyright © 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe, and contributors, for SSTRE's own changes only. Upstream code keeps its own license, copyright headers and notices. Contributions use the Developer Certificate of Origin (`git commit -s`).

## Related repositories

[SSTRE](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE) (umbrella and docs) · [SSTRE-AssetCompiler](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE-AssetCompiler) · [SSTRE-Manifests](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE-Manifests) · [Remaster-Toolkit](https://github.com/Handelsonderneming-S-D-Broekhoven/Remaster-Toolkit)
