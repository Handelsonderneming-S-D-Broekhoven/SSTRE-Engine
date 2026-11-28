#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe
# SPDX-License-Identifier: GPL-2.0-only
"""SSTRE-Engine patch-series tooling (SSTRE ADR-0008, backlog POC-27).

SSTRE-Engine publishes only SSTRE's own changes, as one ``git format-patch``
series per upstream, against the upstream commits pinned in
``upstream.lock.json``. This script is the only supported way to produce and
consume those series. Python 3.10+ and git 2.33+; standard library only.

Subcommands
  fetch   Fetch each pinned upstream commit into a local cache (bare repos) and
          verify it. Online from the lock's repository URL, or offline from an
          existing local clone (``--source NAME=PATH``, ``--offline``).
  apply   Create a working tree at the pinned commit and ``git am`` the series
          in ``patches/<name>/`` in order; verify commit count, clean tree and
          print the resulting tree hash.
  export  ``git format-patch`` the commits between the pinned commit and a
          local branch into ``patches/<name>/`` with deterministic file names
          and headers, then run ``check`` (and, with ``--verify``, the
          round trip).
  check   Enforce the ADR-0008 content rules on patch files (no binary
          patches, no game data/binaries/forbidden paths, review gate for
          files flagged by the EXP-004 publication audit, no Signed-off-by,
          size limit, deterministic headers).
  verify  Round trip: fresh apply of the series on the clean pinned upstream
          and compare the tree hash with a local source branch.

Typical use (see docs/sstre/patch-tooling.md):
  python tools/sstre_patches.py fetch --source classic-vk=../SSTRE-Engine --offline
  python tools/sstre_patches.py export classic-vk --from phase1/cvk-build --verify
  python tools/sstre_patches.py check
  python tools/sstre_patches.py apply classic-vk --out build/upstream

Exit codes: 0 ok, 1 check/verification failure, 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent  # SSTRE-Engine root
LOCK_NAME = "upstream.lock.json"
ZERO_FROM = "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001"
PATCH_NAME = re.compile(r"^(\d{4})-[A-Za-z0-9._-]+\.patch$")
REVIEW_FILE = "REVIEWED-FLAGGED.json"
REVIEW_SCHEMA = "sstre-reviewed-flagged/1"
SERIES_EXTRA_FILES = {"README.md", ".gitkeep", REVIEW_FILE}
DEFAULT_MAX_PATCH_KIB = 1024
LARGE_DELETION_LINES = 500
# Identity used for the commits that ``git am`` creates in throw-away working
# trees. Together with --committer-date-is-author-date this makes the applied
# commit IDs reproducible on every machine.
APPLY_IDENTITY = {"GIT_COMMITTER_NAME": "SSTRE patch tool",
                  "GIT_COMMITTER_EMAIL": "sstre-patches@invalid"}

# --- content rules ---------------------------------------------------------
# Copy of the umbrella validator's lists (SSTRE scripts/validate_repo.py,
# FORBIDDEN_EXTENSIONS / FORBIDDEN_DIR_PARTS). The umbrella file is GPL-3.0-only
# and is therefore read as data (``--validator``), never imported. A unit test
# and the CI job compare this copy with the umbrella list.
FORBIDDEN_EXTENSIONS = {
    ".gro", ".tex", ".mdl", ".wld", ".ani", ".bm", ".bs", ".ba", ".smc",
    ".fnt", ".tbn",
    ".dem", ".sav",
    ".ogg", ".wav", ".mp3",
    ".safetensors", ".ckpt", ".pth", ".pt", ".onnx", ".gguf",
}
FORBIDDEN_DIR_PARTS = {"extracted", "workspace"}
# ADR-0008 item 4: prebuilt binaries, archives, images/screenshots and GPU
# texture containers may never be added or changed by a patch.
PATCH_FORBIDDEN_EXTENSIONS = {
    ".exe", ".dll", ".lib", ".obj", ".o", ".a", ".so", ".dylib", ".pdb", ".ilk",
    ".exp", ".zip", ".7z", ".rar", ".gz", ".xz", ".bz2", ".tar",
    ".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".dds", ".ktx", ".ktx2",
    ".ifr",
}
# Paths (fnmatch, case-insensitive, matched against the path and every
# sub-path after a '/') that a patch must never touch. EXP-004 G3, G7-G9b, B1.
FORBIDDEN_PATHS = [
    ("Demos/*", "demo recordings (EXP-004 G3)"),
    ("Images/*", "README screenshots (EXP-004 G9)"),
    ("Github/*", "README screenshots (EXP-004 G9b)"),
    ("OverridenTextures/*", "override textures (EXP-004 G7/G8)"),
    ("Tools.Win32/*", "bundled prebuilt tools (EXP-004 B1)"),
]
# Paths flagged by EXP-004: context lines reproduce excerpts of files whose
# redistribution status is unclear. Touching them needs explicit review
# (--allow-flagged); deleting them is never allowed (the deletion hunk would
# reproduce the whole file).
FLAGGED_PATHS = [
    ("Sources/Entities/*", "TFE Entities, provenance unclear (EXP-004 H6)"),
    ("DSOUND.H", "Microsoft DSOUND.H, all rights reserved (EXP-004 H1)"),
    ("LWSkaExporter/*", "LightWave SDK / NewTek files (EXP-004 H2)"),
    ("SamTFE/Scripts/*", "retail-identical scripts (EXP-004 G4)"),
    ("SamTSE/Scripts/*", "retail-identical scripts (EXP-004 G4)"),
    ("SamTFE/Controls/*", "retail-identical controls (EXP-004 G4)"),
    ("SamTSE/Controls/*", "retail-identical controls (EXP-004 G4)"),
    ("SamTFE/Help/*", "retail-identical help files (EXP-004 G4)"),
    ("SamTSE/Help/*", "retail-identical help files (EXP-004 G4)"),
    ("SamTFE/Data/*", "game data files (EXP-004 G4/G6)"),
    ("SamTSE/Data/*", "game data files (EXP-004 G4/G6)"),
    ("SamTFE/Mods/*", "mod descriptors/thumbnails (EXP-004 G5)"),
    ("SamTSE/Mods/*", "mod descriptors/thumbnails (EXP-004 G5)"),
]
SIGNOFF = re.compile(r"^\s*Signed-off-by\s*:", re.IGNORECASE)
TRAILER = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)\s*:\s*(.+)$")


class ToolError(Exception):
    """Usage or environment problem (exit code 2)."""


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------
GIT_OVERRIDES = [
    "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", "core.eol=lf",
    "-c", "core.quotepath=true", "-c", "core.longpaths=true", "-c", "color.ui=never",
    "-c", "advice.detachedHead=false", "-c", "gc.auto=0", "-c", "commit.gpgsign=false",
]


def _isolated_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for local-only git operations: ignore system and global git
    configuration so that output does not depend on the developer's setup."""
    env = dict(os.environ)
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        env.pop(k, None)
    if extra:
        env.update(extra)
    return env


def git(args: list[str], cwd: Path | str | None = None, *, isolated: bool = True,
        env_extra: dict[str, str] | None = None, check: bool = True,
        text: bool = True) -> subprocess.CompletedProcess:
    if isolated:
        env = _isolated_env(env_extra)
    else:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        env.update(env_extra or {})
    cmd = ["git", *GIT_OVERRIDES, *args]
    try:
        cp = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=text,
                            encoding="utf-8" if text else None,
                            errors="surrogateescape" if text else None)
    except OSError as exc:
        raise ToolError(f"cannot run git: {exc}") from exc
    if check and cp.returncode != 0:
        err = cp.stderr if text else cp.stderr.decode("utf-8", "replace")
        raise ToolError(f"git {' '.join(args)} failed in {cwd}:\n{err.strip()}")
    return cp


def git_out(args: list[str], cwd: Path | str | None = None, **kw) -> str:
    return git(args, cwd, **kw).stdout.strip()


def has_commit(repo: Path, sha: str) -> bool:
    cp = git(["cat-file", "-t", sha], repo, check=False)
    return cp.returncode == 0 and cp.stdout.strip() == "commit"


def _rm_tree(path: Path) -> None:
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=onerror)


# --------------------------------------------------------------------------
# lock file
# --------------------------------------------------------------------------
@dataclass
class Upstream:
    name: str
    role: str
    repository: str
    commit: str
    patch_series: str
    license: str | None = None
    swhid: str | None = None
    raw: dict = field(default_factory=dict)

    def series_dir(self, root: Path) -> Path:
        return root / self.patch_series


LOCK_ROLES = {"primary", "secondary", "dependency"}


def load_lock(root: Path) -> list[Upstream]:
    """Load and sanity-check upstream.lock.json (the full JSON Schema check is
    done by the umbrella validator; this repeats the rules the tool relies on)."""
    path = root / LOCK_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"{path}: cannot read lock file: {exc}") from exc
    if data.get("schema_version") != "0.1" or not isinstance(data.get("upstreams"), list):
        raise ToolError(f"{path}: expected schema_version 0.1 and an 'upstreams' array")
    out, seen = [], set()
    for i, u in enumerate(data["upstreams"]):
        where = f"{path.name}: upstreams[{i}]"
        try:
            up = Upstream(u["name"], u["role"], u["repository"], u["commit"], u["patch_series"],
                          u.get("license"), u.get("swhid"), u)
        except (KeyError, TypeError) as exc:
            raise ToolError(f"{where}: missing field {exc}") from exc
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", up.name) or up.name in seen:
            raise ToolError(f"{where}: invalid or duplicate name {up.name!r}")
        seen.add(up.name)
        if up.role not in LOCK_ROLES:
            raise ToolError(f"{where}: role must be one of {sorted(LOCK_ROLES)}")
        if not re.fullmatch(r"[0-9a-f]{40}", up.commit):
            raise ToolError(f"{where}: commit must be a full 40-hex SHA-1")
        if up.patch_series != f"patches/{up.name}":
            raise ToolError(f"{where}: patch_series must be 'patches/{up.name}'")
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", up.repository):
            raise ToolError(f"{where}: repository must be a https://github.com/<owner>/<repo> URL")
        if up.swhid is not None and up.swhid != f"swh:1:rev:{up.commit}":
            raise ToolError(f"{where}: swhid {up.swhid} does not name commit {up.commit}")
        out.append(up)
    return out


def select(upstreams: list[Upstream], names: list[str] | None) -> list[Upstream]:
    if not names:
        return upstreams
    by = {u.name: u for u in upstreams}
    missing = [n for n in names if n not in by]
    if missing:
        raise ToolError(f"unknown upstream(s): {', '.join(missing)} (lock has {', '.join(by)})")
    return [by[n] for n in names]


# --------------------------------------------------------------------------
# cache / fetch
# --------------------------------------------------------------------------
def default_cache() -> Path:
    env = os.environ.get("SSTRE_UPSTREAM_CACHE")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "sstre" / "upstream-cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "sstre" / "upstream-cache"


def cache_repo(cache: Path, up: Upstream) -> Path:
    return cache / f"{up.name}.git"


def ensure_cache_repo(repo: Path) -> None:
    if not (repo / "HEAD").is_file():
        repo.mkdir(parents=True, exist_ok=True)
        git(["init", "--quiet", "--bare", str(repo)])
    git(["config", "core.autocrlf", "false"], repo)
    git(["config", "core.longpaths", "true"], repo)
    git(["config", "gc.auto", "0"], repo)


def verify_pinned(repo: Path, up: Upstream) -> str:
    """The pinned commit must be present as a commit with its full tree; returns the tree SHA."""
    if not has_commit(repo, up.commit):
        raise ToolError(f"{up.name}: pinned commit {up.commit} is not present in {repo}")
    resolved = git_out(["rev-parse", "--verify", f"{up.commit}^{{commit}}"], repo)
    if resolved != up.commit:
        raise ToolError(f"{up.name}: {up.commit} resolves to {resolved}")
    tree = git_out(["rev-parse", f"{up.commit}^{{tree}}"], repo)
    # every object of the pinned tree must be present (shallow fetches included)
    git(["rev-list", "--objects", "--missing=error", "--no-walk", up.commit], repo)
    git(["ls-tree", "-r", "-t", "--full-tree", up.commit], repo)
    return tree


def check_swh(up: Upstream, tree: str, timeout: float = 30.0) -> str:
    """Ask the Software Heritage API whether the pinned revision is archived and
    whether its directory equals the git tree."""
    url = f"https://archive.softwareheritage.org/api/1/revision/{up.commit}/"
    req = urllib.request.Request(url, headers={"User-Agent": "sstre-patches"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network errors are reported, not fatal
        return f"not verified ({exc})"
    if data.get("directory") != tree:
        raise ToolError(f"{up.name}: Software Heritage directory {data.get('directory')} != tree {tree}")
    return f"archived, directory {tree}"


def cmd_fetch(args) -> int:
    root = args.root
    ups = select(load_lock(root), args.names)
    cache = args.cache
    sources = {}
    for spec in args.source or []:
        name, sep, path = spec.partition("=")
        if not sep:
            raise ToolError(f"--source expects NAME=PATH, got {spec!r}")
        sources[name] = Path(path).resolve()
    if args.offline and args.check_swh:
        raise ToolError("--check-swh needs the network; it cannot be combined with --offline")
    for up in ups:
        repo = cache_repo(cache, up)
        ensure_cache_repo(repo)
        if has_commit(repo, up.commit) and not args.refetch:
            origin = "cache"
        else:
            src = sources.get(up.name)
            if src is None and args.offline:
                raise ToolError(f"{up.name}: --offline and no --source {up.name}=PATH given, "
                                f"and the pinned commit is not cached in {repo}")
            if src is not None:
                if not has_commit(src, up.commit):
                    raise ToolError(f"{up.name}: local source {src} does not contain {up.commit}")
                url, isolated, origin = str(src), True, f"local {src}"
            else:
                url, isolated, origin = up.repository, False, up.repository
            fetch = ["fetch", "--quiet", "--no-tags", "--no-write-fetch-head"]
            if args.depth > 0:
                fetch.append(f"--depth={args.depth}")
            # fetch exactly the pinned commit by SHA (protocol v2; GitHub and
            # local repositories serve reachable commits by ID)
            git(["-c", "protocol.version=2", *fetch, url,
                 f"+{up.commit}:refs/sstre/pinned/{up.name}"], repo, isolated=isolated)
        git(["update-ref", f"refs/sstre/pinned/{up.name}", up.commit], repo)
        tree = verify_pinned(repo, up)
        line = f"{up.name}: {up.commit} ok (tree {tree}, from {origin})"
        if args.check_swh:
            line += f"; Software Heritage: {check_swh(up, tree)}"
        print(line)
    return 0


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------
def series_files(series_dir: Path) -> list[Path]:
    if not series_dir.is_dir():
        return []
    return sorted(p for p in series_dir.iterdir() if p.is_file() and p.suffix == ".patch")


_DEL_HEADER = re.compile(rb"^deleted file mode [0-7]{6}\r?\n$")
_DEL_INDEX = re.compile(rb"^index ([0-9a-f]{40})\.\.0{40}\r?\n$")


def expand_irreversible_deletes(raw: bytes, wt: Path, tmp: Path) -> tuple[bytes, int]:
    """Turn content-free deletion sections (format-patch --irreversible-delete,
    which plain git am cannot apply) back into full deletions, generated by git
    from the blob present in ``wt`` at HEAD. The blob ID recorded in the patch
    must match HEAD exactly, so a deletion can never remove anything else."""
    lines = raw.splitlines(keepends=True)
    blocks = []  # (start, end, path, blob)
    for i in range(len(lines) - 2):
        if not lines[i].startswith(b"diff --git "):
            continue
        m = _DEL_INDEX.match(lines[i + 2])
        if not (_DEL_HEADER.match(lines[i + 1]) and m):
            continue
        nxt = lines[i + 3] if i + 3 < len(lines) else b""
        if nxt.startswith((b"--- ", b"Binary files ", b"GIT binary patch")):
            continue  # already a full deletion
        a, b = _diff_git_paths(lines[i][len(b"diff --git "):].rstrip(b"\r\n").decode("utf-8", "surrogateescape"))
        if a is None or a != b:
            raise ToolError(f"cannot parse deletion header: {lines[i]!r}")
        blocks.append((i, i + 3, a, m.group(1).decode()))
    if not blocks:
        return raw, 0
    paths = [blk[2] for blk in blocks]
    for _s, _e, path, blob in blocks:
        cp = git(["rev-parse", "--verify", "--quiet", f"HEAD:{path}"], wt, check=False)
        if cp.stdout.strip() != blob:
            raise ToolError(f"deletion of {path}: expected blob {blob}, HEAD has "
                            f"{cp.stdout.strip() or 'no such file'}")
    index = {"GIT_INDEX_FILE": str((tmp / "expand.index").resolve())}
    git(["read-tree", "HEAD"], wt, env_extra=index)
    git(["update-index", "--force-remove", "--", *paths], wt, env_extra=index)
    tree = git_out(["write-tree"], wt, env_extra=index)
    (tmp / "expand.index").unlink()
    full = git(["diff-tree", "-p", "--full-index", "--binary", "--no-renames", "--no-ext-diff",
                "--src-prefix=a/", "--dst-prefix=b/", "HEAD", tree, "--", *paths],
               wt, text=False).stdout
    sections: dict[str, bytes] = {}
    cur_path, cur = None, []
    for ln in full.splitlines(keepends=True):
        if ln.startswith(b"diff --git "):
            if cur_path is not None:
                sections[cur_path] = b"".join(cur)
            cur_path = _diff_git_paths(ln[len(b"diff --git "):].rstrip(b"\r\n").decode("utf-8", "surrogateescape"))[0]
            cur = []
        cur.append(ln)
    if cur_path is not None:
        sections[cur_path] = b"".join(cur)
    if set(sections) != set(paths):
        raise ToolError(f"could not regenerate deletions for {sorted(set(paths) - set(sections))}")
    out, pos = [], 0
    for start, end, path, _blob in blocks:
        out.append(b"".join(lines[pos:start]))
        out.append(sections[path])
        pos = end
    out.append(b"".join(lines[pos:]))
    return b"".join(out), len(blocks)


def apply_series(repo: Path, up: Upstream, series_dir: Path, out: Path, force: bool) -> dict:
    """Check out the pinned commit into ``out`` (a linked worktree of the cache
    repo) and apply the series with git am. Returns a result dict."""
    verify_pinned(repo, up)
    if out.exists():
        if not force:
            raise ToolError(f"{out} exists; use --force to replace it")
        git(["worktree", "remove", "--force", str(out)], repo, check=False)
        _rm_tree(out)
    git(["worktree", "prune"], repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "--quiet", "--detach", str(out), up.commit], repo)
    git(["config", "core.autocrlf", "false"], out)
    patches = series_files(series_dir)
    expanded_total = 0
    with tempfile.TemporaryDirectory(prefix="sstre-am-") as tmp:
        for p in patches:
            data, n = expand_irreversible_deletes(p.read_bytes(), out, Path(tmp))
            expanded_total += n
            src = p.resolve()
            if n:
                src = Path(tmp) / p.name
                src.write_bytes(data)
            cp = git(["am", "--quiet", "--keep-cr", "--quoted-cr=nowarn", "--no-3way",
                      "--committer-date-is-author-date", "--whitespace=nowarn", str(src)],
                     out, env_extra=APPLY_IDENTITY, check=False)
            if cp.returncode != 0:
                git(["am", "--abort"], out, check=False)
                raise ToolError(f"{up.name}: git am failed on {p.name}:\n{(cp.stdout + cp.stderr).strip()}")
    head = git_out(["rev-parse", "HEAD"], out)
    count = int(git_out(["rev-list", "--count", f"{up.commit}..HEAD"], out))
    if count != len(patches):
        raise ToolError(f"{up.name}: {len(patches)} patch(es) but {count} commit(s) on top of the pin")
    if git_out(["rev-list", "--min-parents=2", f"{up.commit}..HEAD"], out):
        raise ToolError(f"{up.name}: unexpected merge commit after git am")
    dirty = git_out(["status", "--porcelain", "--untracked-files=all"], out)
    if dirty:
        raise ToolError(f"{up.name}: working tree not clean after git am:\n{dirty}")
    return {"name": up.name, "pinned": up.commit, "patches": len(patches),
            "expanded_deletions": expanded_total, "head": head,
            "tree": git_out(["rev-parse", "HEAD^{tree}"], out), "worktree": str(out)}


def cmd_apply(args) -> int:
    root = args.root
    for up in select(load_lock(root), args.names):
        repo = cache_repo(args.cache, up)
        if not (repo / "HEAD").is_file():
            raise ToolError(f"{up.name}: no cache at {repo}; run 'fetch' first")
        res = apply_series(repo, up, up.series_dir(root), args.out / up.name, args.force)
        if args.expect_tree and res["tree"] != args.expect_tree:
            print(json.dumps(res))
            print(f"ERROR: {up.name}: tree {res['tree']} != expected {args.expect_tree}")
            return 1
        print(json.dumps(res))
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------
@dataclass
class FileChange:
    old: str | None
    new: str | None
    kind: str = "modify"          # add, delete, modify, rename, copy
    old_mode: str | None = None
    new_mode: str | None = None
    binary: bool = False
    added: list[str] = field(default_factory=list)
    removed: int = 0
    full_index: bool = True
    context: int = 0              # largest leading/trailing context run of any hunk

    def paths(self) -> list[str]:
        return sorted({p for p in (self.old, self.new) if p})


@dataclass
class ParsedPatch:
    from_line: str
    headers: dict[str, str]
    message: list[str]
    files: list[FileChange]
    signature: bool
    nul: bool


_CQUOTE = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
           "\\": "\\", '"': '"'}


def _unquote(s: str) -> str:
    """Decode a git C-quoted path ("..." with backslash/octal escapes)."""
    if not (s.startswith('"') and s.endswith('"')):
        return s
    body, out, i = s[1:-1], bytearray(), 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            if n in "01234567" and i + 3 < len(body) + 1:
                out.append(int(body[i + 1:i + 4], 8))
                i += 4
                continue
            out.extend(_CQUOTE.get(n, n).encode())
            i += 2
            continue
        out.extend(c.encode("utf-8", "surrogateescape"))
        i += 1
    return out.decode("utf-8", "replace")


def _strip_prefix(p: str) -> str | None:
    p = _unquote(p.split("\t", 1)[0].rstrip("\r"))
    if p == "/dev/null":
        return None
    return p[2:] if p[:2] in ("a/", "b/") else p


def _diff_git_paths(rest: str) -> tuple[str | None, str | None]:
    rest = rest.rstrip("\r")
    if rest.startswith('"'):
        m = re.match(r'("(?:[^"\\]|\\.)*")\s+(.*)$', rest)
        if m:
            return _strip_prefix(m.group(1)), _strip_prefix(m.group(2))
    if rest.startswith("a/") and (len(rest) - 5) % 2 == 0:
        n = (len(rest) - 5) // 2
        a, b = rest[2:2 + n], rest[2 + n:]
        if b == f" b/{a}":
            return a, a
    return None, None


def parse_patch(raw: bytes) -> ParsedPatch:
    text = raw.decode("utf-8", "surrogateescape")
    lines = text.split("\n")
    from_line = lines[0].rstrip("\r") if lines else ""
    i, headers, last = 1, {}, None
    while i < len(lines) and lines[i].strip("\r") != "":
        ln = lines[i].rstrip("\r")
        if ln[:1] in (" ", "\t") and last:
            headers[last] += " " + ln.strip()
        elif ":" in ln:
            last, _, val = ln.partition(":")
            headers[last] = val.strip()
        i += 1
    message = []
    i += 1
    while i < len(lines) and lines[i].rstrip("\r") != "---" and not lines[i].startswith("diff --git "):
        message.append(lines[i].rstrip("\r"))
        i += 1
    files: list[FileChange] = []
    cur: FileChange | None = None
    in_hunk = False
    signature = False
    hunk = {"lead": None, "run": 0}   # context-run bookkeeping of the open hunk

    def end_hunk() -> None:
        if cur is not None and in_hunk:
            lead = hunk["run"] if hunk["lead"] is None else hunk["lead"]
            cur.context = max(cur.context, lead, hunk["run"])
        hunk.update(lead=None, run=0)

    for j in range(i, len(lines)):
        ln = lines[j]
        if ln.startswith("diff --git "):
            end_hunk()
            a, b = _diff_git_paths(ln[len("diff --git "):])
            cur = FileChange(a, b)
            files.append(cur)
            in_hunk = False
            continue
        if ln.rstrip("\r") == "-- " and j + 1 < len(lines) and re.match(r"^\d+\.\d+", lines[j + 1]):
            signature = True
            end_hunk()
            cur = None
            continue
        if cur is None:
            continue
        if in_hunk:
            if ln.startswith(("+", "-")):
                if ln.startswith("+"):
                    cur.added.append(ln[1:])
                else:
                    cur.removed += 1
                if hunk["lead"] is None:
                    hunk["lead"] = hunk["run"]
                hunk["run"] = 0
                continue
            if ln.startswith(" "):
                hunk["run"] += 1
                continue
            if ln.startswith("\\") or ln == "":
                continue
            end_hunk()
            in_hunk = False
        if ln.startswith("@@"):
            in_hunk = True
        elif ln.startswith("new file mode "):
            cur.kind, cur.new_mode, cur.old = "add", ln.split()[-1], None
        elif ln.startswith("deleted file mode "):
            cur.kind, cur.old_mode, cur.new = "delete", ln.split()[-1], None
        elif ln.startswith("old mode "):
            cur.old_mode = ln.split()[-1]
        elif ln.startswith("new mode "):
            cur.new_mode = ln.split()[-1]
        elif ln.startswith("rename from ") or ln.startswith("copy from "):
            cur.kind = "rename" if ln.startswith("rename") else "copy"
            cur.old = _unquote(ln.split(" ", 2)[2].rstrip("\r"))
        elif ln.startswith("rename to ") or ln.startswith("copy to "):
            cur.new = _unquote(ln.split(" ", 2)[2].rstrip("\r"))
        elif ln.startswith("index "):
            m = re.match(r"index ([0-9a-f]+)\.\.([0-9a-f]+)(?: (\d+))?", ln)
            if m:
                cur.full_index = len(m.group(1)) == 40 and len(m.group(2)) == 40
                if m.group(3):
                    cur.old_mode = cur.old_mode or m.group(3)
                    cur.new_mode = cur.new_mode or m.group(3)
        elif ln.startswith("GIT binary patch") or (ln.startswith("Binary files ") and ln.rstrip("\r").endswith(" differ")):
            cur.binary = True
        elif ln.startswith("--- "):
            p = _strip_prefix(ln[4:])
            if cur.kind != "add":
                cur.old = p if p is not None else cur.old
        elif ln.startswith("+++ "):
            p = _strip_prefix(ln[4:])
            if cur.kind != "delete":
                cur.new = p if p is not None else cur.new
    end_hunk()
    return ParsedPatch(from_line, headers, message, files, signature, b"\0" in raw)


def _match_any(path: str, patterns: list[tuple[str, str]]) -> str | None:
    """Case-insensitive fnmatch against the path and every sub-path."""
    low = path.lower()
    parts = low.split("/")
    subpaths = ["/".join(parts[k:]) for k in range(len(parts))]
    for pat, why in patterns:
        lp = pat.lower()
        if any(fnmatch.fnmatchcase(sp, lp) for sp in subpaths):
            return why
    return None


def message_trailers(lines: list[str]) -> list[str]:
    """Trailer lines (``Key: value``) of the last paragraph of a commit message."""
    paras, cur = [], []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                paras.append(cur)
            cur = []
        else:
            cur.append(ln.strip())
    if cur:
        paras.append(cur)
    if len(paras) < 2:
        return []
    last = paras[-1]
    return [ln for ln in last if TRAILER.match(ln)] if all(TRAILER.match(ln) for ln in last) else []


@dataclass
class CheckOptions:
    allow_flagged: bool = False
    allow_signoff: bool = False
    max_patch_kib: int = DEFAULT_MAX_PATCH_KIB
    forbidden_ext: set[str] = field(default_factory=lambda: set(FORBIDDEN_EXTENSIONS))
    forbidden_dirs: set[str] = field(default_factory=lambda: set(FORBIDDEN_DIR_PARTS))
    # patch file name -> review entry from patches/<series>/REVIEWED-FLAGGED.json
    reviews: dict[str, dict] = field(default_factory=dict)


@dataclass
class CheckReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    patches: int = 0


def check_patch_file(path: Path, opts: CheckOptions, rep: CheckReport, label: str | None = None) -> None:
    label = label or path.as_posix()
    raw = path.read_bytes()
    rep.patches += 1
    review = opts.reviews.get(path.name)
    digest = hashlib.sha256(raw).hexdigest()
    err = lambda m: rep.errors.append(f"{label}: {m}")
    warn = lambda m: rep.warnings.append(f"{label}: {m}")
    if len(raw) > opts.max_patch_kib * 1024:
        err(f"patch is {len(raw) // 1024} KiB, above the {opts.max_patch_kib} KiB limit; split it")
    pp = parse_patch(raw)
    if pp.nul:
        err("contains NUL bytes (binary content)")
    if pp.from_line != ZERO_FROM:
        err("first line is not the --zero-commit mbox line; re-export with tools/sstre_patches.py export")
    if pp.signature:
        err("ends with a git version signature; re-export with --no-signature")
    for h in ("From", "Date", "Subject"):
        if h not in pp.headers:
            err(f"missing '{h}:' header")
    if any(SIGNOFF.match(ln) for ln in pp.message):
        (warn if opts.allow_signoff else err)(
            "commit message carries a Signed-off-by trailer (SSTRE commits never add one; "
            "--allow-signoff only for trailers that exist in an upstream-authored commit)")
    if not pp.files:
        warn("contains no file changes")
    for fc in pp.files:
        paths = fc.paths()
        if not paths:
            err("could not determine the path of a diff section")
            continue
        shown = " -> ".join(p for p in (fc.old, fc.new) if p) if fc.kind in ("rename", "copy") else paths[0]
        if fc.binary:
            err(f"{shown}: binary patch (ADR-0008 forbids binary patches)")
        if not fc.full_index:
            err(f"{shown}: abbreviated 'index' line; re-export with --full-index")
        for mode in (fc.old_mode, fc.new_mode):
            if mode == "160000":
                err(f"{shown}: submodule (gitlink) change")
            elif mode == "120000":
                err(f"{shown}: symbolic link")
        if fc.kind == "delete" and (fc.removed or fc.binary):
            err(f"{shown}: deletion reproduces the full removed content; "
                "re-export with --irreversible-delete (tools/sstre_patches.py export)")
        # a content-free (irreversible) deletion reproduces nothing of the file:
        # removing forbidden material is allowed, but reported
        clean_delete = fc.kind == "delete" and not fc.removed and not fc.binary
        bad = warn if clean_delete else err
        note = " - deleted without content" if clean_delete else ""
        for p in paths:
            suffix = Path(p).suffix.lower()
            if suffix in opts.forbidden_ext:
                bad(f"{p}: forbidden extension '{suffix}' (game data, demos/savegames, audio or model weights){note}")
            elif suffix in PATCH_FORBIDDEN_EXTENSIONS:
                bad(f"{p}: forbidden extension '{suffix}' (binaries, archives, images or textures){note}")
            dirs = {part.lower() for part in p.split("/")[:-1]}
            if dirs & opts.forbidden_dirs:
                bad(f"{p}: under a local-only directory ({'/'.join(sorted(opts.forbidden_dirs))}){note}")
            why = _match_any(p, FORBIDDEN_PATHS)
            if why:
                bad(f"{p}: forbidden path: {why}{note}")
            why = _match_any(p, FLAGGED_PATHS)
            if why:
                if fc.kind == "delete" and not clean_delete:
                    err(f"{p}: deleting a flagged file with its content reproduces it ({why})")
                elif clean_delete:
                    warn(f"{p}: deletes a flagged file without content ({why})")
                elif review is not None and p in review["paths"] and review["sha256"] == digest:
                    warn(f"{p}: touches a flagged file ({why}); reviewed by {review['reviewer']} "
                         f"on {review['date']} ({REVIEW_FILE}), {fc.context} context line(s)")
                elif opts.allow_flagged:
                    hint = ("" if fc.context <= 1 else
                            "; prefer 1 line of context (export --flagged-context 1)")
                    warn(f"{p}: touches a flagged file ({why}); reviewed via --allow-flagged, "
                         f"{fc.context} context line(s){hint}")
                elif review is not None and p in review["paths"]:
                    err(f"{p}: touches a flagged file ({why}); the patch changed since its review "
                        f"(sha256 {digest} != reviewed {review['sha256']}), needs re-review in {REVIEW_FILE}")
                else:
                    err(f"{p}: touches a flagged file ({why}); needs explicit review "
                        f"(an entry in {REVIEW_FILE}, or --allow-flagged locally)")
        if fc.removed >= LARGE_DELETION_LINES:
            warn(f"{shown}: removes {fc.removed} upstream lines; the patch reproduces them "
                 "(check that this is not generated or third-party content)")
        if fc.kind == "add" and not fc.binary:
            head = "\n".join(fc.added[:30])
            if "SPDX-License-Identifier" not in head:
                warn(f"{fc.new}: new file without an SPDX-License-Identifier header")


def find_series_dirs(root: Path, upstreams: list[Upstream] | None, rep: CheckReport) -> list[Path]:
    pdir = root / "patches"
    dirs = sorted(p for p in pdir.iterdir() if p.is_dir()) if pdir.is_dir() else []
    if upstreams is not None:
        known = {u.name for u in upstreams}
        for d in dirs:
            if d.name not in known:
                rep.errors.append(f"patches/{d.name}: no upstream with this name in {LOCK_NAME}")
    if pdir.is_dir():
        for f in pdir.iterdir():
            if f.is_file() and f.name not in SERIES_EXTRA_FILES:
                rep.errors.append(f"patches/{f.name}: unexpected file (patches live in patches/<name>/)")
    return dirs


def load_reviews(d: Path, rep: CheckReport, label: str) -> dict[str, dict]:
    """Read patches/<series>/REVIEWED-FLAGGED.json: the per-patch record of a
    reviewed change to EXP-004 flagged files. An entry passes a patch only while
    the SHA-256 of the patch file is unchanged, so any change needs re-review."""
    f = d / REVIEW_FILE
    if not f.is_file():
        return {}
    where = f"{label}/{REVIEW_FILE}"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.errors.append(f"{where}: cannot read: {exc}")
        return {}
    if not isinstance(data, dict) or data.get("schema") != REVIEW_SCHEMA or not isinstance(data.get("reviews"), list):
        rep.errors.append(f"{where}: expected {{\"schema\": \"{REVIEW_SCHEMA}\", \"reviews\": [...]}}")
        return {}
    out: dict[str, dict] = {}
    for i, e in enumerate(data["reviews"]):
        ok = (isinstance(e, dict) and isinstance(e.get("patch"), str) and PATCH_NAME.match(e["patch"])
              and isinstance(e.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
              and isinstance(e.get("paths"), list) and e["paths"] and all(isinstance(x, str) for x in e["paths"])
              and all(isinstance(e.get(k), str) and e[k].strip() for k in ("reviewer", "date", "rationale"))
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.get("date") or ""))
        if not ok:
            rep.errors.append(f"{where}: reviews[{i}]: needs patch (NNNN-<slug>.patch), sha256 (64 hex), "
                              "non-empty paths, reviewer, date (YYYY-MM-DD) and rationale")
            continue
        if e["patch"] in out:
            rep.errors.append(f"{where}: reviews[{i}]: duplicate entry for {e['patch']}")
            continue
        if not (d / e["patch"]).is_file():
            rep.warnings.append(f"{where}: reviews[{i}]: {e['patch']} is not in the series (stale entry)")
        out[e["patch"]] = e
    return out


def check_series_dir(d: Path, opts: CheckOptions, rep: CheckReport, label: str) -> None:
    opts = dataclasses.replace(opts, reviews=load_reviews(d, rep, label))
    nums = []
    for f in sorted(d.iterdir()):
        rel = f"{label}/{f.name}"
        if f.is_dir():
            rep.errors.append(f"{rel}: unexpected directory")
            continue
        if f.name in SERIES_EXTRA_FILES:
            continue
        m = PATCH_NAME.match(f.name)
        if not m:
            rep.errors.append(f"{rel}: file name must be NNNN-<slug>.patch")
            continue
        nums.append(int(m.group(1)))
        check_patch_file(f, opts, rep, rel)
    if nums and nums != list(range(1, len(nums) + 1)):
        rep.errors.append(f"{label}: patch numbers must be contiguous from 0001, got {nums}")


def read_validator_lists(path: Path) -> tuple[set[str], set[str]]:
    """Read FORBIDDEN_EXTENSIONS / FORBIDDEN_DIR_PARTS from the umbrella
    validator as literal data (ast), without importing or executing it."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ToolError(f"cannot read validator {path}: {exc}") from exc
    found: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("FORBIDDEN_EXTENSIONS", "FORBIDDEN_DIR_PARTS"):
                found[name] = set(ast.literal_eval(node.value))
    if len(found) != 2:
        raise ToolError(f"{path}: FORBIDDEN_EXTENSIONS / FORBIDDEN_DIR_PARTS not found")
    return found["FORBIDDEN_EXTENSIONS"], found["FORBIDDEN_DIR_PARTS"]


def options_from_args(args) -> CheckOptions:
    opts = CheckOptions(allow_flagged=args.allow_flagged, allow_signoff=args.allow_signoff,
                        max_patch_kib=args.max_patch_kib)
    if args.validator:
        ext, dirs = read_validator_lists(args.validator)
        extra = sorted(ext - FORBIDDEN_EXTENSIONS) + sorted(dirs - FORBIDDEN_DIR_PARTS)
        if extra:
            print(f"WARNING: umbrella validator lists entries missing from this tool's copy: {', '.join(extra)}")
        opts.forbidden_ext |= ext
        opts.forbidden_dirs |= dirs
    return opts


def print_report(rep: CheckReport, what: str) -> int:
    for n in rep.notes:
        print(f"note: {n}")
    for w in rep.warnings:
        print(f"WARNING: {w}")
    for e in rep.errors:
        print(f"ERROR: {e}")
    print(f"check: {what}: {rep.patches} patch(es), {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


def cmd_check(args) -> int:
    opts = options_from_args(args)
    rep = CheckReport()
    if args.paths:
        for p in args.paths:
            p = Path(p)
            if p.is_dir():
                check_series_dir(p, opts, rep, p.as_posix())
            elif p.is_file():
                check_patch_file(p, dataclasses.replace(opts, reviews=load_reviews(p.parent, rep, p.parent.as_posix())),
                                 rep)
            else:
                raise ToolError(f"{p}: no such file or directory")
        return print_report(rep, "given paths")
    ups = load_lock(args.root)
    for d in find_series_dirs(args.root, ups, rep):
        check_series_dir(d, opts, rep, f"patches/{d.name}")
    return print_report(rep, "patches/")


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
FORMAT_PATCH_ARGS = [
    "format-patch", "--quiet", "--zero-commit", "--no-signature", "--full-index",
    "--no-numbered", "--subject-prefix=PATCH", "--no-cover-letter", "--no-thread",
    "--no-attach", "--no-notes", "--encode-email-headers", "--filename-max-length=64",
    "--start-number=1", "--stat=72", "--find-renames", "--diff-algorithm=myers",
    "--no-ext-diff", "--no-relative", "--src-prefix=a/", "--dst-prefix=b/",
    # deleted files appear as header + preimage blob ID only, never as '-'
    # lines; 'apply' re-expands them from the verified upstream blob
    "--irreversible-delete",
]


def series_commits(src: Path, up: Upstream, ref: str) -> list[str]:
    if not has_commit(src, up.commit):
        raise ToolError(f"{up.name}: pinned commit {up.commit} not found in {src}")
    tip = git_out(["rev-parse", "--verify", f"{ref}^{{commit}}"], src)
    if git(["merge-base", "--is-ancestor", up.commit, tip], src, check=False).returncode != 0:
        raise ToolError(f"{up.name}: {ref} is not based on the pinned commit {up.commit}")
    if git_out(["rev-list", "--min-parents=2", f"{up.commit}..{tip}"], src):
        raise ToolError(f"{up.name}: {ref} contains merge commits; the series must be linear")
    commits = git_out(["rev-list", "--reverse", "--topo-order", f"{up.commit}..{tip}"], src).split()
    prev = up.commit
    for c in commits:
        parent = git_out(["rev-parse", f"{c}^"], src)
        if parent != prev:
            raise ToolError(f"{up.name}: history between the pin and {ref} is not a single chain")
        prev = c
    return commits


def parse_context_rules(specs: list[str] | None, flagged: int | None) -> list[tuple[str, int, str]]:
    """``--path-context GLOB=N`` rules (first match wins) followed by the
    ``--flagged-context N`` rule for every EXP-004 flagged path."""
    rules = []
    for spec in specs or []:
        glob, sep, n = spec.rpartition("=")
        if not sep or not glob or not n.isdigit() or int(n) < 1:
            raise ToolError(f"--path-context {spec!r}: expected GLOB=N with N >= 1")
        rules.append((glob, int(n), f"--path-context {spec}"))
    if flagged is not None:
        if flagged < 1:
            raise ToolError("--flagged-context must be >= 1 (git am cannot apply zero-context patches)")
        rules.extend((pat, flagged, f"flagged: {why}") for pat, why in FLAGGED_PATHS)
    return rules


def _context_for(paths: list[str], rules: list[tuple[str, int, str]]) -> int | None:
    for glob, n, why in rules:
        if any(_match_any(p, [(glob, why)]) for p in paths):
            return n
    return None


def _split_sections(raw: bytes) -> tuple[bytes, list[bytes]]:
    """Split a format-patch file (exported with --no-signature) into the part
    before the first ``diff --git`` line and one chunk per file section."""
    lines = raw.splitlines(keepends=True)
    starts = [k for k, ln in enumerate(lines) if ln.startswith(b"diff --git ")]
    if not starts:
        return raw, []
    head = b"".join(lines[:starts[0]])
    bounds = starts + [len(lines)]
    return head, [b"".join(lines[bounds[k]:bounds[k + 1]]) for k in range(len(starts))]


def _section_diff(src: Path, commit: str, paths: list[str], unified: int) -> bytes:
    """One commit's diff for ``paths``, with the same diff options as the export."""
    return git(["diff-tree", "-p", "--no-commit-id", "--full-index", "--binary",
                "--find-renames", "--diff-algorithm=myers", "--irreversible-delete",
                "--no-ext-diff", "--no-relative", "--src-prefix=a/", "--dst-prefix=b/",
                f"--unified={unified}", f"{commit}^", commit, "--", *paths],
               src, text=False).stdout


def apply_path_context(patch: Path, commit: str, src: Path, unified: int,
                       rules: list[tuple[str, int, str]]) -> list[str]:
    """Re-generate the file sections of ``patch`` whose path matches a context
    rule with that rule's number of context lines (ADR-0008 item 4: minimal
    context for EXP-004 flagged files). The commit message, the diffstat and
    all other sections are kept byte for byte. As a safety net, each section is
    first re-generated with the export's default context and must reproduce
    the format-patch output exactly. Returns the rewritten paths."""
    if not rules:
        return []
    head, sections = _split_sections(patch.read_bytes())
    changed, out = [], []
    for sec in sections:
        fc = parse_patch(ZERO_FROM.encode() + b"\n\n" + sec).files[0]
        n = _context_for(fc.paths(), rules)
        if n is None or n == unified or fc.kind in ("add", "delete") or fc.binary:
            out.append(sec)   # additions/deletions carry no upstream context lines
            continue
        paths = fc.paths()
        if _section_diff(src, commit, paths, unified) != sec:
            raise ToolError(f"{patch.name}: cannot re-generate the section for {' -> '.join(paths)} "
                            "identically; refusing to change its context")
        out.append(_section_diff(src, commit, paths, n))
        changed.append(f"{' -> '.join(paths)} (context {n})")
    if changed:
        patch.write_bytes(head + b"".join(out))
    return changed


def export_series(src: Path, up: Upstream, ref: str, dest: Path, unified: int,
                  opts: CheckOptions, rules: list[tuple[str, int, str]] | None = None
                  ) -> tuple[list[Path], CheckReport]:
    commits = series_commits(src, up, ref)
    rep = CheckReport()
    opts = dataclasses.replace(opts, reviews=load_reviews(dest, rep, up.patch_series))
    with tempfile.TemporaryDirectory(prefix="sstre-export-") as tmp:
        tmpd = Path(tmp) / up.name
        if commits:
            git([*FORMAT_PATCH_ARGS, f"--unified={unified}", f"--base={up.commit}",
                 "-o", str(tmpd), f"{up.commit}..{commits[-1]}"], src)
        produced = series_files(tmpd)
        if len(produced) != len(commits):
            raise ToolError(f"{up.name}: format-patch wrote {len(produced)} file(s) for {len(commits)} commit(s)")
        for p, c in zip(produced, commits):
            for what in apply_path_context(p, c, src, unified, rules or []):
                rep.notes.append(f"{p.name}: {what}")
            # the patch message must not carry any trailer the commit does not have
            commit_trailers = message_trailers(git_out(["log", "-1", "--format=%B", c], src).split("\n"))
            pp = parse_patch(p.read_bytes())
            for t in message_trailers(pp.message):
                if t not in commit_trailers:
                    rep.errors.append(f"{p.name}: trailer '{t}' is not in commit {c[:12]} (added by tooling?)")
            check_patch_file(p, opts, rep, f"{up.patch_series}/{p.name}")
        if rep.errors:
            return [], rep
        dest.mkdir(parents=True, exist_ok=True)
        for old in series_files(dest):
            old.unlink()
        written = []
        for p in produced:
            target = dest / p.name
            target.write_bytes(p.read_bytes())
            written.append(target)
        return written, rep


def round_trip(cache: Path, up: Upstream, series_dir: Path, src: Path, ref: str,
               keep: Path | None = None) -> dict:
    repo = cache_repo(cache, up)
    if not (repo / "HEAD").is_file() or not has_commit(repo, up.commit):
        raise ToolError(f"{up.name}: pinned commit not cached in {repo}; run 'fetch' first")
    expected = git_out(["rev-parse", f"{ref}^{{tree}}"], src)
    tmp = None
    if keep is None:
        tmp = Path(tempfile.mkdtemp(prefix=f"sstre-verify-{up.name}-", dir=str(cache)))
        out = tmp / "wt"
    else:
        out = keep
    try:
        res = apply_series(repo, up, series_dir, out, force=True)
    finally:
        if tmp is not None:
            git(["worktree", "remove", "--force", str(out)], repo, check=False)
            _rm_tree(tmp)
            git(["worktree", "prune"], repo, check=False)
    res.update({"source_ref": ref, "source_tree": expected, "match": res["tree"] == expected})
    if keep is None:
        res.pop("worktree", None)
    return res


def cmd_export(args) -> int:
    root = args.root
    (up,) = select(load_lock(root), [args.name])
    src = (args.source_repo or root).resolve()
    opts = options_from_args(args)
    rules = parse_context_rules(args.path_context, args.flagged_context)
    written, rep = export_series(src, up, args.from_ref, up.series_dir(root), args.unified, opts, rules)
    rc = print_report(rep, f"export {up.name}")
    if rc:
        print(f"export {up.name}: aborted, {up.patch_series} left unchanged")
        return rc
    for w in written:
        print(f"wrote {w.relative_to(root).as_posix()}")
    print(f"export {up.name}: {len(written)} patch(es) from {args.from_ref} on {up.commit[:12]}")
    if args.verify:
        res = round_trip(args.cache, up, up.series_dir(root), src, args.from_ref)
        print(json.dumps(res))
        if not res["match"]:
            print(f"ERROR: round trip failed: applied tree {res['tree']} != {args.from_ref} tree {res['source_tree']}")
            return 1
        print(f"round trip ok: tree {res['tree']}")
    return 0


def cmd_verify(args) -> int:
    root = args.root
    (up,) = select(load_lock(root), [args.name])
    src = (args.source_repo or root).resolve()
    res = round_trip(args.cache, up, up.series_dir(root), src, args.from_ref, args.keep)
    print(json.dumps(res))
    if not res["match"]:
        print(f"ERROR: applied tree {res['tree']} != {args.from_ref} tree {res['source_tree']}")
        return 1
    print(f"round trip ok: {up.name} tree {res['tree']}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sstre_patches.py", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=TOOL_ROOT,
                    help="SSTRE-Engine checkout holding upstream.lock.json and patches/ (default: %(default)s)")
    ap.add_argument("--cache", type=Path, default=None,
                    help="upstream cache directory (default: $SSTRE_UPSTREAM_CACHE or the user cache dir)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def check_flags(p):
        p.add_argument("--allow-flagged", action="store_true",
                       help="downgrade 'touches an EXP-004 flagged file' to a warning (after review)")
        p.add_argument("--allow-signoff", action="store_true",
                       help="accept Signed-off-by trailers that exist in upstream-authored commits")
        p.add_argument("--max-patch-kib", type=int, default=DEFAULT_MAX_PATCH_KIB,
                       help="maximum size of one patch file (default: %(default)s KiB)")
        p.add_argument("--validator", type=Path,
                       help="umbrella scripts/validate_repo.py; its forbidden lists are added (read as data)")

    p = sub.add_parser("fetch", help="fetch and verify the pinned upstream commits")
    p.add_argument("names", nargs="*", help="upstream names (default: all)")
    p.add_argument("--source", action="append", metavar="NAME=PATH",
                   help="fetch NAME from this local clone instead of its repository URL")
    p.add_argument("--offline", action="store_true",
                   help="never use the network: every upstream needs a cache entry or --source")
    p.add_argument("--depth", type=int, default=1, help="fetch depth (0 = full history; default 1)")
    p.add_argument("--refetch", action="store_true", help="fetch even if the commit is cached")
    p.add_argument("--check-swh", action="store_true",
                   help="also query the Software Heritage API (network) for the pinned revision")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("apply", help="check out the pinned commits and git am the series")
    p.add_argument("names", nargs="*", help="upstream names (default: all)")
    p.add_argument("--out", type=Path, default=None,
                   help="parent directory for the working trees (default: <root>/build/upstream)")
    p.add_argument("--force", action="store_true", help="replace an existing working tree")
    p.add_argument("--expect-tree", help="fail unless the resulting tree hash equals this")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("export", help="format-patch a local branch into patches/<name>/")
    p.add_argument("name")
    p.add_argument("--from", dest="from_ref", required=True, help="local branch or commit (series tip)")
    p.add_argument("--source-repo", type=Path, help="repository holding the branch (default: --root)")
    p.add_argument("--unified", type=int, default=3, help="context lines (default 3)")
    p.add_argument("--path-context", action="append", metavar="GLOB=N",
                   help="use N context lines for files matching GLOB (case-insensitive, matched like "
                        "the check rules); repeatable, first match wins")
    p.add_argument("--flagged-context", type=int, default=1, metavar="N",
                   help="context lines for files flagged by EXP-004 (ADR-0008 item 4; default %(default)s; "
                        "pass the --unified value to disable)")
    p.add_argument("--verify", action="store_true", help="run the round trip after exporting")
    check_flags(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("check", help="enforce the ADR-0008 patch content rules")
    p.add_argument("paths", nargs="*", help="patch files or series directories (default: patches/*)")
    check_flags(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("verify", help="round trip: apply on clean upstream, compare tree with a branch")
    p.add_argument("name")
    p.add_argument("--from", dest="from_ref", required=True, help="local branch the series was exported from")
    p.add_argument("--source-repo", type=Path, help="repository holding the branch (default: --root)")
    p.add_argument("--keep", type=Path, help="keep the applied working tree at this path")
    p.set_defaults(func=cmd_verify)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.root = args.root.resolve()
    args.cache = (args.cache or default_cache()).resolve()
    if getattr(args, "out", None) is None and args.cmd == "apply":
        args.out = args.root / "build" / "upstream"
    if getattr(args, "out", None) is not None:
        args.out = args.out.resolve()
    try:
        return args.func(args)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
