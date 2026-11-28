# `classic-vk` patch series

<!-- SPDX-FileCopyrightText: 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe -->
<!-- SPDX-License-Identifier: GPL-2.0-only -->

Applies to tx00100xt/SeriousSamClassic-VK at the commit pinned in [`upstream.lock.json`](../../upstream.lock.json). Apply with `tools/sstre_patches.py apply classic-vk` (see [`docs/sstre/patch-tooling.md`](../../docs/sstre/patch-tooling.md)). Exported from the local integration branch `sprint2/integration` (SSTRE EXP-017).

| Patches | Content | Origin |
|---|---|---|
| 0001–0006 | Windows build fixes (trusted win_flex/win_bison, no MFC) | SSTRE (EXP-001) |
| 0007 | Compile-time switch that removes master-server traffic (`SSTRE_MASTER_SERVER`, default off) | SSTRE (EXP-010, POC-32) |
| 0008–0009 | `FilterBitmap` row-buffer overflow fix for textures wider than 2048 px; `tex_iNormalSize` 12 and an oversized-upload log line | SSTRE (EXP-016) |
| 0010–0015 | Ray-tracing backend (`GAT_RT`, RTGL1) transplanted into TFE, runtime-optional | **ported from the secondary upstream Serious-Engine-RT** (see below), adapted by SSTRE (EXP-009) |
| 0016 | Log failed RTGL1 calls in Release builds | SSTRE (EXP-009) |
| 0017–0018 | `+demo` command-line option; clean end of demo playback (profile report, post-exec) | SSTRE (EXP-011) |
| 0019 | CMake/Linux builds compile TFE without the RT layer (`SE1_RAYTRACING=0`) | SSTRE (EXP-017) |

## Code from the secondary upstream (ADR-0008 amendment A1)

Patches 0010–0015 contain code ported from [sultim-t/Serious-Engine-RT](https://github.com/sultim-t/Serious-Engine-RT) at the commit pinned for `serious-engine-rt` in the lock (`0e7f223c`; RT-only changes since its fork point `77a955ba`), GPL-2.0-only, by Sultim Tsyrendashiev. The original copyright notices in the ported files are kept unchanged (the new `Engine/Raytracing/` files therefore carry the original GPL-2.0 notice instead of an SPDX tag), and each of these commit messages names the source and its author. SSTRE adaptations are described in the commit messages.

## Files flagged by the EXP-004 audit (reviewed, `--allow-flagged`)

Exported with 1 line of context (`--flagged-context 1`, ADR-0008 item 4):

| Patch | File | Flag |
|---|---|---|
| 0013 | `SamTFE/Sources/Entities/Common/HUD.cpp` | H6, TFE Entities of unclear provenance |
| 0013 | `SamTFE/Sources/Entities/Player.es` | H6 |
| 0013 | `SamTFE/Sources/Entities/PlayerWeapons.es` | H6 |
| 0015 | `SamTFE/Scripts/Menu/RenderingOptions.cfg` | G4, retail-identical scripts |
