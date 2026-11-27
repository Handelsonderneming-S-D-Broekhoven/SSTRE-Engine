# Building Serious-Engine-RT (TFE, Windows x64) with RayTracedGL1

Status: **executed successfully on 2026-11-27** on the SSTRE reference PC, except where a step is marked *untested*. The evidence is in [SSTRE EXP-002](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE/blob/phase1/validation/docs/experiments/EXP-002-rt-build-and-s1.md) (local branch, not yet pushed).

These steps build the **TFE game runtime** of sultim-t/Serious-Engine-RT (`SeriousSamTFE`, `Engine`, `Entities`, `Game`, `Shaders`, `Ecc` and the bundled audio libraries) against RayTracedGL1 (RTGL1). The MFC editors and tools, `DedicatedServer` (it needs TSE `EntitiesMP`) and TSE (`All.sln`) are **not** built. See "Known gaps".

No binaries built with these steps may be distributed. Game data is user-supplied and is never committed. NVIDIA DLSS is **disabled**: never set `RG_WITH_NVIDIA_DLSS`, and never download the DLSS SDK or `nvngx_dlss.dll`.

## Source revisions

| Component | Branch / commit | Modifications |
|---|---|---|
| Serious-Engine-RT | `phase1/rt-build` = `upstream/rt-main` (`0e7f223c19a28014b60d900878c28831db522120`, tag v1.5) + 7 build commits | MSVC projects, `.l`/`.y` grammar prologues, two `.rc` files |
| RayTracedGL1 | local branch `phase1/rtgl1-v1.1.0-sdk1.4` = tag `v1.1.0` (`b1eb3d8ca3fe75f6f4dda16a53aeb99ea613aead`) + 1 commit (`4bcf13e`) | one GLSL header |

RTGL1 `v1.1.0` is the last RTGL1 commit dated before SE-RT `0e7f223` (2022-04-20 00:25 vs 20:24 +0100); the next RTGL1 commits are dated 2022-04-23 or later. SE-RT links and runs against it (EXP-002).

### Build commits on `phase1/rt-build`

1. `33e8b255`: call `win_bison`/`win_flex` (trusted WinFlexBison) instead of bare `bison`/`flex`. The bare names resolve to the unverified `Tools.Win32/Bison.exe` and `Flex.exe` through `ExecutablePath` (Ecc, Engine, SeriousSkaStudio projects).
2. `46ce9ace`: drop `-S Flex.skl` / `-S smcFlex.skl`. flex 2.6.4 fails with "bad line in skeleton file".
3. `cc74881f`: add a `%top{ #include "StdH.h" }` block to `Engine/Base/Scanner.l` and `%top{ #include <Engine/StdH.h> }` to `Engine/Ska/smcScan.l`. The dropped skeletons emitted these PCH includes; without them MSVC fails with C1010.
4. `4b464aa2`: add `--wincompat` to the Engine `win_flex` commands (C1083 `unistd.h`).
5. `e6ac425b`: `#define YY_SKIP_YYWRAP` in the same `%top` blocks (C2732 `yywrap` linkage).
6. `47e4eff1`: `#define YYINITDEPTH 1000` in `Ecc/Parser.y`. With bison 3.8 the parser stack cannot grow for the C++ `SType`, so `Entities/Player.es` fails with "memory exhausted". Classic-VK uses the same value.
7. `4d18ac11`: `#include "winres.h"` instead of the MFC header `afxres.h` in `SeriousSam/SeriousSam.rc` and `DedicatedServer/DedicatedServer.rc`.

### RTGL1 commit on `phase1/rtgl1-v1.1.0-sdk1.4`

- `4bcf13e`: `Source/Shaders/ShaderCommonGLSLFunc.h`: turn the unused function `sampler2D getTexture(uint)` into a macro. glslang in Vulkan SDK 1.4.363.0 rejects functions that return a sampler ("sampler or image cannot be used as return type when generating SPIR-V"), which broke 8 of 45 shaders. This is a backport of upstream RTGL1 `a2ad71e` (Friedrich Vock, 2023-11-26).

## Prerequisites (versions used)

| Tool | Version |
|---|---|
| Visual Studio 2022 Community | 17.5, MSVC 14.35.32215, toolset v143 (the projects already ask for v143) |
| MFC | **not installed** on the reference PC (ATL only). Not needed: build with `-p:UseOfMfc=false` (see below) |
| CMake | 4.4.4 (RTGL1 asks for >= 3.15; no policy override needed) |
| Ninja | 1.13.2 |
| Vulkan SDK | 1.4.363.0 at `C:\VulkanSDK\1.4.363.0` (glslc: shaderc v2026.4, glslang 11.1.0-1566) |
| Python | 3.10 (RTGL1 shader script) |
| WinFlexBison | 2.5.25 (bison 3.8.2, flex 2.6.4), directory on `PATH` |

## Steps

The helper scripts used on the reference PC are in `<workspace>\local-work\rt-tools\` (`build-rtgl1.bat`, `build-sert.bat`, `assemble-runtime.sh`, `run-se.ps1`). The commands below are what they run.

### 1. Worktrees

```powershell
git -C <SSTRE-Engine> worktree add <work>\rt -b phase1/rt-build upstream/rt-main
git -C <RTGL1 clone> worktree add <work>\rtgl1-v1.1.0 v1.1.0
# then create branch phase1/rtgl1-v1.1.0-sdk1.4 there with commit 4bcf13e (or cherry-pick a2ad71e by hand)
```

### 2. RTGL1 library (in a VS x64 developer prompt)

```bat
set VULKAN_SDK=C:\VulkanSDK\1.4.363.0
set PATH=%VULKAN_SDK%\Bin;<ninja dir>;%PATH%
cmake -S <work>\rtgl1-v1.1.0 -B <work>\rtgl1-v1.1.0\Build\x64-Release -G Ninja ^
      -DCMAKE_BUILD_TYPE=RelWithDebInfo -DRG_WITH_SURFACE_WIN32=ON ^
      -DRG_WITH_NVIDIA_DLSS=OFF -DRG_WITH_EXAMPLES=OFF
cmake --build <work>\rtgl1-v1.1.0\Build\x64-Release
```

`RelWithDebInfo` matches upstream `CMakeSettings.json` for `x64-Release`. SE-RT expects `Build\x64-Release\RayTracedGL1.{lib,dll}`.

### 3. RTGL1 shaders

```sh
cd <work>/rtgl1-v1.1.0/Source/Shaders
PATH="/c/VulkanSDK/1.4.363.0/Bin:$PATH" python -I GenerateShaders.py -r
```

This writes 45 `*.spv` files to `<work>/rtgl1-v1.1.0/Build/`. The script treats any glslc output as a failure, so check for "> Done.".

### 4. SE-RT game runtime (in a VS x64 developer prompt)

```bat
set VULKAN_SDK=C:\VulkanSDK\1.4.363.0
set RTGL1_SDK_PATH=<work>\rtgl1-v1.1.0
set PATH=<winflexbison dir>;%VULKAN_SDK%\Bin;%PATH%
msbuild <work>\rt\Sources\AllTFE.sln /m ^
  "/t:Ecc;Engine;Entities;Game;SeriousSamTFE;libogg;libvorbis;libvorbisfile;Shaders" ^
  /p:Configuration=Release /p:Platform=x64 -p:UseOfMfc=false /v:m
```

- `-p:UseOfMfc=false` is needed because `Entities` and `Game` are marked `UseOfMfc=Dynamic` but do not use MFC, and MFC is not installed (MSB8041). It is a command-line property, not a source change.
- Outputs go to `<work>\rt\Bin\`. The Engine post-build step copies `RayTracedGL1.dll` there.
- Pitfall: Ecc's copy-to-`Bin` custom build step does not always re-run after `Ecc.exe` is rebuilt. Delete `Bin\Ecc.exe` after changing `Ecc/Parser.y`, or the stale Ecc is used.
- Clean rebuild on the reference PC: exit code 0 in 139 s, with 222 distinct warning lines (mostly C4267/C4244; also 22 C4477 `CTString` passed to `%s`).

### 5. Runtime directory (copy only; never modify the Steam install)

```text
<runtime>\Bin\                  <- <work>\rt\Bin\*.dll, *.exe
<runtime>\Shaders\              <- <work>\rtgl1-v1.1.0\Build\*.spv
<runtime>\OverridenTextures\    <- BlueNoise_LDR_RGBA_128.ktx2, WaterNormal_n.ktx2 from <work>\rt\OverridenTextures
<runtime>\OverridenTextures\Compressed\   (empty, or your own KTX2 overrides)
<runtime>\Data, Scripts, Controls, Players, Help, VirtualTrees, SE1_10.gro, ModEXT.txt  <- <work>\rt\
<runtime>\Levels\, 1_00_ExtraTools.gro, 1_00_music.gro, 1_00c.gro, 1_00c_Logo.gro,
          1_00c_scripts.gro, 1_04_patch.gro   <- user's Steam TFE install (list from the SE-RT v1.5 release notes)
<runtime>\Demos\                <- optional, Steam TFE install
```

Do **not** download `TFE_RT_Textures.zip`.

### 6. Launch

Create `<runtime>\Scripts\PersistentSymbols.ini` containing `sam_bFirstStarted=(INDEX)0;`, which suppresses the first-start message box. Then:

```text
<runtime>\Bin\SeriousSamTFE.exe +script Scripts\sstre_lvl_api2.ini +level Levels\<level>.wld
```

Contents of `sstre_lvl_api<N>.ini`: `sam_iGfxAPI=<N>; sam_bFullScreen=0; sam_iScreenSizeI=1920; sam_iScreenSizeJ=1080; hud_iStats=1;`. For RT, add `srt_bVSync=0; srt_bDebugValidation=0;`. The API values are `2` = Vulkan ray tracing (RTGL1), `1` = Vulkan raster, `0` = OpenGL. Validation: set `srt_bDebugValidation=1;`. This cvar is *persistent*, so set it back to 0 explicitly. The log is written to `<runtime>\SeriousSamTFE.log`.

## Known gaps

- **TSE is not buildable here.** `Sources/All.sln` and the TSE projects (`SeriousSam`, `EntitiesMP`, `GameMP`) define only Win32 configurations and no `SE1_RAYTRACING`. RTGL1 is x64-only.
- MFC tools and `DedicatedServer` were not built. *Untested.*
- Demo playback: `PlayDemo("…")` receives a garbled argument on x64. The workaround `dem_bPlay=1; dem_bPlayByName=1;` plus `+level Demos\<demo>.dem` showed a black screen, and the process exited after 37 s (EXP-002).
- The OpenGL backend renders brushes untextured (EXP-002).
- A debug build, the `Sources/RTGL1` submodule layout from the README and RTGL1 with DLSS are not covered and are deliberately *untested*.
