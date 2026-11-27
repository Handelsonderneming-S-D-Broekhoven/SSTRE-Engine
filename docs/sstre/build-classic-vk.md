# Building the Classic-VK baseline (Windows x64 and Linux x64)

Status: **executed successfully on 2026-11-27** on the SSTRE reference PC, except where a step is marked *untested*. The evidence is in [SSTRE EXP-001](https://github.com/Handelsonderneming-S-D-Broekhoven/SSTRE/blob/phase1/validation/docs/experiments/EXP-001-classic-vk-build.md) (local branch, not yet pushed).

These steps build the **game runtime** of SeriousSamClassic-VK (`SeriousSam`, `DedicatedServer`, `Engine`, `Entities`/`EntitiesMP`, `Game`/`GameMP`, `Shaders`, `Ecc` and the bundled audio libraries) for The First Encounter (TFE, `SamTFE/`) and The Second Encounter (TSE, `SamTSE/`). The MFC editors and tools (WorldEditor, Modeler, SeriousSkaStudio, EngineGUI, GameGUI and others) are **not** built. See "Known gaps".

No binaries built with these steps may be distributed. Game data is user-supplied and is never committed.

## Source revisions

| Platform | Branch / commit | Modifications |
|---|---|---|
| Linux x64 | `upstream/classic-vk-main` = `510d36f901cbe883c56b155b53717e4efdeb6522` | none |
| Windows x64 | `phase1/cvk-build` = `510d36f` + 6 build commits (`d4c43f15`, `9cb83850`, `bbf04b04`, `4677963f`, `4206e38f`, `ba0c12e8`) | MSVC project, `.rc` and one Windows-only `.l` file. See below |

The six Windows commits change only files that the CMake (Unix) build does not use:

1. `d4c43f15`: call `win_bison`/`win_flex` (trusted WinFlexBison) instead of bare `bison`/`flex`. The bare names resolve to the unverified `Tools.Win32/Bison.exe` and `Flex.exe`, because those projects put `$(SolutionDir)..\Tools.Win32` first in `ExecutablePath`.
2. `9cb83850`: drop `-S Flex.skl` / `-S smcFlex.skl`. flex 2.6.4 rejects the flex-2.5 skeletons. The CMake build never uses them either.
3. `bbf04b04`: add `--wincompat` to `win_flex` (avoids `#include <unistd.h>`).
4. `4677963f`: force-include `Engine/StdH.h` into the generated `SCANNER.CPP` (PCH disabled for that file) and `Smcscan.cpp`. The dropped skeletons used to inject that include.
5. `4206e38f`: declare `syywrap` as `extern "C"` in `Engine/Ska/smcScwin.l` (C2732 with flex 2.6.4). The Unix variant `smcScan.l` already does this.
6. `ba0c12e8`: `#include <winres.h>` instead of the MFC header `afxres.h` in `SeriousSam.rc` and `DedicatedServer.rc`.

## Windows x64 (MSVC)

### Prerequisites (versions used)

| Tool | Version |
|---|---|
| Visual Studio 2022 Community | 17.5.1, MSVC 14.35.32215, toolset **v143** (the projects ask for v140, which is not installed) |
| Windows SDK | 10.0.22000.0 (the projects ask for 10.0.14393.0, which is not installed) |
| Vulkan SDK | 1.4.363.0 at `C:\VulkanSDK\1.4.363.0` |
| WinFlexBison | 2.5.25 (bison 3.8.2, flex 2.6.4), directory on `PATH` |
| MFC | **not required** for these steps (the MFC component was not installed on the reference PC) |

### Steps

```powershell
git -C <SSTRE-Engine> worktree add <work>\cvk phase1/cvk-build
$env:VULKAN_SDK = 'C:\VulkanSDK\1.4.363.0'
$env:PATH = '<path-to>\winflexbison;' + $env:VULKAN_SDK + '\Bin;' + $env:PATH
$msb = 'C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\MSBuild.exe'
$common = '/m','/p:Configuration=Release','/p:Platform=x64','/p:PlatformToolset=v143',
          '/p:WindowsTargetPlatformVersion=10.0.22000.0','/p:UseOfMfc=false'

# TFE
& $msb <work>\cvk\SamTFE\Sources\SamTFE.sln @common `
  '/t:Ecc;Engine;Entities;Game;Shaders;SeriousSam;DedicatedServer;libogg;libvorbis;libvorbisfile;amp11lib'
# TSE
& $msb <work>\cvk\SamTSE\Sources\SamTSE.sln @common `
  '/t:Ecc;Engine;EntitiesMP;GameMP;Shaders;SeriousSam;DedicatedServer;libogg;libvorbis;libvorbisfile;amp11lib'
```

Outputs go to `SamTFE\Bin\` and `SamTSE\Bin\`. A clean rebuild (`<Project>:Rebuild` targets) took 150 s (TFE) and 82 s (TSE) on a 12-thread CPU, with 0 errors and 187 warnings each.

`/p:UseOfMfc=false` only removes the `_AFXDLL` define and the MFC link setting. No runtime source includes MFC headers. `Build` of the whole solution fails with `MSB8041` (MFC libraries required) in DecodeReport, Depend, EngineGUI, Entities, MakeFONT and RCon when MFC is absent.

The flex/bison generated sources (`Parser.cpp`, `Scanner.cpp` and the `.es`-generated `.cpp/.h/_tables.h`) are written into the source tree and are untracked. Remove them before building the same worktree with CMake, or build Linux from `git archive` as below.

*Untested:* Debug configuration, Win32 (x86), the upstream CI's XPLUS variant, and building with the MFC component installed and without `/p:UseOfMfc=false`.

### Runtime layout (Windows)

Create a runtime directory outside any repository:

1. Copy the upstream game-root template (`SamTFE/` or `SamTSE/` without `Sources/`, `Tools.Win32/` and `Bin/`). It includes upstream `SE1_10b.gro` and `ModEXT.txt`.
2. Copy into the same directory from your own Steam install. TFE: all `*.gro`, `Help/` and `Levels/`. TSE: all `*.gro` and `Help/`. This follows upstream `README.md`, "Running".
3. Copy the built `*.exe` and `*.dll` into `Bin/`.
4. Run `Bin\SeriousSam.exe`. Useful options: `+level <path.wld>` and `+script <file.ini>`. The script runs before the video mode is set, so it can set `sam_iGfxAPI=0|1` (OpenGL/Vulkan), `sam_bFullScreen=0`, `sam_iScreenSizeI/J`, and `sam_bAutoPlayDemos=0`. The log is `SeriousSam.log` in the runtime root.

## Linux x64 (Docker, Ubuntu 22.04 as in upstream CI)

### Steps

```sh
# on the host: export the pristine upstream tree (LF line endings!)
git -C <SSTRE-Engine> -c core.autocrlf=false archive --format=tar -o src.tar 510d36f901cbe883c56b155b53717e4efdeb6522

docker pull ubuntu:22.04   # resolved 2026-11-27 to:
# ubuntu@sha256:b000e69a50ff940390233025e7a337fb8469b509e2334fa4d018ac30f3e18cdb
docker run --rm -v <abs>/src.tar:/in/src.tar:ro -v <abs>/build-linux.sh:/in/build.sh:ro -v <abs>/out:/out \
  ubuntu@sha256:b000e69a50ff940390233025e7a337fb8469b509e2334fa4d018ac30f3e18cdb sh /in/build.sh
```

`build-linux.sh` (as executed):

```sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -qq -y --no-install-recommends build-essential cmake ninja-build git \
  libsdl2-dev libogg-dev libvorbis-dev bison flex zlib1g-dev libxxhash-dev \
  libvulkan1 libvulkan-dev vulkan-validationlayers vulkan-validationlayers-dev nasm
mkdir -p /work/src && tar -xf /in/src.tar -C /work/src && cd /work/src
cmake -B /work/build -DCMAKE_BUILD_TYPE=Release
cmake --build /work/build -j"$(nproc)"
cmake --install /work/build          # installs into /work/src/SamT?E/Bin
cp -a /work/src/SamTFE/Bin /out/SamTFE/ && cp -a /work/src/SamTSE/Bin /out/SamTSE/
```

Key package versions resolved on 2026-11-27: gcc 11.4.0, cmake 3.22.1, bison 3.8.2, flex 2.6.4, libsdl2-dev 2.0.20, libvulkan-dev 1.3.204.1, libvorbis-dev 1.3.7, zlib1g-dev 1.2.11, nasm 2.15.05. apt packages are **not** pinned. Re-running later may pull newer patch versions. Keep the `dpkg -l` output of each run.

The CMake build writes generated parser/entity sources into the source tree. That is why the tree is extracted inside the container rather than built from a read-only mount. A tarball made with `core.autocrlf=true` (the Git for Windows default) contains CRLF and fails in `ecc` with `Unrecognized character (ASCII 0x0d)`.

The build took 62 s and 67 s in two runs. The two clean builds produced byte-identical binaries (same container image, same paths).

*Untested:* running the Linux client on real Linux hardware (Mesa RADV or NVIDIA), Steam Deck, the XPLUS variant, and `-march=native` portability (upstream CI replaces it with `-mtune=generic`; these steps keep the upstream default, so binaries may not run on older CPUs).

### Runtime layout (Linux)

The binary expects the data next to `Bin/` (non-system install): `<root>/Bin/SeriousSam` with the `.gro` files etc. in `<root>/`. That is the same layout as on Windows, using the Linux `Bin/`. For the system-install alternative, see upstream `README.md`, "Install the game in system". On 2026-11-27 only a headless `DedicatedServer` smoke test was run in Docker (see EXP-001). The graphical client was not run on Linux.
