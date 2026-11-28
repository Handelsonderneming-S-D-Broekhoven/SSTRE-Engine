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
| 0020–0024, 0026–0027 | Ray-tracing backend replayed into the TSE tree (engine, game exe, menu, EntitiesMP hooks, flashlight key) | **ported from Serious-Engine-RT**, adapted by SSTRE (track E5) |
| 0025 | Log failed RTGL1 calls in Release builds (TSE) | SSTRE (E5) |
| 0028–0029, 0031 | Data-driven RT world tuning: `CustomInfoTuning.cpp` and `SSTRE/RT/WorldTuning.txt` (TSE, TFE) replace Serious-Engine-RT's hard-coded tables | SSTRE (E5); the TFE table migrates Serious-Engine-RT's public values and texture lists |
| 0030 | CMake/Linux builds compile TSE without the RT layer | SSTRE (EXP-017) |
| 0032 | TSE RT tuning: `haze = 0` by default (fixes darkness beyond ~20 m; SE1 fog/haze was rendered as under-water media) | SSTRE (E5, EXP-018) |
| 0033 | RT brush export batched per entity and material (5127 → 1405 geometries on `1_2_Palenque`), plus a guard for RTGL1's 4096-geometry static capacity (TFE, TSE) | SSTRE (E5, EXP-018); changes files ported from Serious-Engine-RT |
| 0034 | Build RT particles only inside the RT particle pass (null-scene crash from first-person particles; TFE, TSE) | SSTRE (E5, EXP-018); changes a file ported from Serious-Engine-RT |
| 0035 | TSE RT tuning: `[world 1_2_Palenque]` whitelists 25 static lights of the start cave (`cutscene_light` world positions; no texture paths) | SSTRE (E5, EXP-018) |
| 0036 | TSE `GameMP/Controls.cpp`: existing player control profiles get the RT "Flashlight" button, bound to L if L is free | SSTRE (E5) |

## Code from the secondary upstream (ADR-0008 amendment A1)

Patches 0010–0015, 0020–0024 and 0026–0029 contain code ported from [sultim-t/Serious-Engine-RT](https://github.com/sultim-t/Serious-Engine-RT) at the commit pinned for `serious-engine-rt` in the lock (`0e7f223c`; RT-only changes since its fork point `77a955ba`), GPL-2.0-only, by Sultim Tsyrendashiev. The original copyright notices in the ported files are kept unchanged (the new `Engine/Raytracing/` files therefore carry the original GPL-2.0 notice instead of an SPDX tag), and each of these commit messages names the source and its author. SSTRE adaptations are described in the commit messages.

## Files flagged by the EXP-004 audit

Exported with 1 line of context (`--flagged-context 1`, ADR-0008 item 4). A flagged patch passes `check` only with a matching entry (patch SHA-256) in [`REVIEWED-FLAGGED.json`](REVIEWED-FLAGGED.json); any change to the patch needs a new review.

| Patch | File | Flag | Change | Review |
|---|---|---|---|---|
| 0013 | `SamTFE/Sources/Entities/Common/HUD.cpp` | H6, TFE Entities of unclear provenance | RT hooks | lead, 2026-11-28 |
| 0013 | `SamTFE/Sources/Entities/Player.es` | H6 | flashlight toggle, RT-only `BodyRemoveItem()` | lead, 2026-11-28 |
| 0013 | `SamTFE/Sources/Entities/PlayerWeapons.es` | H6 | first-person weapon render flag | lead, 2026-11-28 |
| 0015 | `SamTFE/Scripts/Menu/RenderingOptions.cfg` | G4, retail-identical scripts | one `Include:` line; the RT options live in the new SSTRE file `SamTFE/SSTRE/Menu/RenderingOptionsRT.cfg` | lead, 2026-11-28 |
| 0024 | `SamTSE/Scripts/Menu/RenderingOptions.cfg` | G4 | one `Include:` line (`SamTSE/SSTRE/Menu/RenderingOptionsRT.cfg`) | lead, 2026-11-28 |
| 0027 | `SamTSE/Controls/00-Default.ctl` | G4, retail-identical controls | +7 lines: "Flashlight" button on L (the controls parser has no include) | lead, 2026-11-28 |
