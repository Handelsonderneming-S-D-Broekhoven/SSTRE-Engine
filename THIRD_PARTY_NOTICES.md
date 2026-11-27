# Third-party notices (SSTRE-Engine)

This repository contains no upstream engine source; upstreams are fetched from their original hosts at the commits pinned in [`upstream.lock.json`](upstream.lock.json) (SSTRE ADR-0008). Upstream code keeps its own licenses and notices.

The patch series in `patches/` contain the following material that was not authored by SSTRE contributors (ADR-0008 amendment A1):

| Series / patch | Material | Origin | License |
|---|---|---|---|
| `rtgl1/0001` | Adapted backport of upstream RayTracedGL1 commit `a2ad71e` ("Make getTexture a macro", Friedrich Vock, 2023-11-26) | https://github.com/sultim-t/RayTracedGL1 | MIT (RayTracedGL1) |
| `rtgl1/0003` | Zstandard 1.5.7 single-file decompressor (`Source/zstd/zstddeclib.c`), generated with the upstream `combine.py` from the release tarball; SHA-256 recorded in the patch series | https://github.com/facebook/zstd (release v1.5.7) | BSD-3-Clause OR GPL-2.0-only (upstream header) |
| `serious-engine-rt/0004`, `classic-vk` build patches | Parser/scanner sources regenerated with GNU Bison 3.8.2 / Flex 2.6.4 from the upstream grammars | upstream grammars (GPL-2.0-only); generator output | GPL-2.0-only (as part of the engine) |

The RayTracedGL1 files touched by the `rtgl1` series are MIT; new SSTRE files in that series are GPL-2.0-only, so an RTGL1 build from this series is distributed (if ever) under GPL-2.0-only as a whole. No engine or RTGL1 binaries are distributed by the project (ADR-0006).
