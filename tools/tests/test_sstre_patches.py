# SPDX-FileCopyrightText: 2026 Handelsonderneming S.D. Broekhoven, trading as ITEagle Europe
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic tests for tools/sstre_patches.py (no network, temporary git repos only).

Run from the SSTRE-Engine root:  python -m unittest discover -s tools/tests -v
Set SSTRE_UMBRELLA_VALIDATOR=<umbrella>/scripts/validate_repo.py to also compare
the forbidden lists with the umbrella validator.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sstre_patches as sp  # noqa: E402

ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
           GIT_AUTHOR_NAME="Test Author", GIT_AUTHOR_EMAIL="author@example.invalid",
           GIT_COMMITTER_NAME="Test Committer", GIT_COMMITTER_EMAIL="committer@example.invalid")


def run_git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    cp = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "init.defaultBranch=main", *args],
                        cwd=repo, env=env, capture_output=True, text=True)
    if cp.returncode != 0:
        raise AssertionError(f"git {args} failed: {cp.stderr}")
    return cp.stdout.strip()


def write(repo: Path, rel: str, data: bytes | str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)


def commit(repo: Path, msg: str, date: str = "2026-01-01T12:00:00+01:00") -> str:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", msg, date=date)
    return run_git(repo, "rev-parse", "HEAD")


def quiet(fn, *a, **kw):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        rc = fn(*a, **kw)
    return rc, buf_out.getvalue() + buf_err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sstre-pt-test-"))
        self.addCleanup(lambda: sp._rm_tree(self.tmp))

    # -- helpers ---------------------------------------------------------
    def make_upstream(self) -> tuple[Path, str]:
        up = self.tmp / "upstream"
        up.mkdir()
        run_git(up, "init", "-q")
        write(up, "README.txt", "upstream readme\n")
        write(up, "src/win.vcxproj", "<Project>\r\n  <A>1</A>\r\n  <B>2</B>\r\n</Project>\r\n")
        write(up, "src/main.c", "int main(void)\n{\n  return 0;\n}\n")
        write(up, "src/old_name.h", "#define X 1\n#define Y 2\n#define Z 3\n")
        write(up, "Sources/Entities/Enemy.es", "enemy\n")
        write(up, "data/blob.bin", b"\x00\x01\x02binary")
        pin = commit(up, "upstream base")
        return up, pin

    def make_engine(self, pin: str, name: str = "eng") -> Path:
        root = self.tmp / "engine"
        (root / "patches" / name).mkdir(parents=True)
        lock = {"schema_version": "0.1", "upstreams": [{
            "name": name, "role": "primary", "repository": "https://github.com/example/eng",
            "commit": pin, "license": "GPL-2.0-only", "swhid": f"swh:1:rev:{pin}",
            "patch_series": f"patches/{name}"}]}
        (root / sp.LOCK_NAME).write_text(json.dumps(lock), encoding="utf-8")
        return root

    def sstre_branch(self, up: Path) -> str:
        run_git(up, "checkout", "-q", "-b", "work")
        write(up, "src/win.vcxproj", "<Project>\r\n  <A>1</A>\r\n  <B>3</B>\r\n</Project>\r\n")
        commit(up, "build: change B\n\nCo-Authored-By: Helper <h@example.invalid>",
               "2026-02-01T10:00:00+01:00")
        write(up, "src/new.c", "// SPDX-License-Identifier: GPL-2.0-only\nint f(void) { return 1; }\n")
        (up / "src/old_name.h").rename(up / "src/new_name.h")
        commit(up, "feat: add f and rename header", "2026-02-02T10:00:00+01:00")
        write(up, "src/main.c", "int main(void)\n{\n  return 1;\n}\n")
        if os.name != "nt":
            os.chmod(up / "src/main.c", 0o755)
        run_git(up, "update-index", "--chmod=+x", "src/main.c")
        commit(up, "fix: exit code, executable bit", "2026-02-03T10:00:00+01:00")
        return "work"

    def main(self, *argv: str) -> tuple[int, str]:
        return quiet(sp.main, list(argv))


# --------------------------------------------------------------------------
class TestCheck(Base):
    def patch(self, body: str, name: str = "0001-x.patch", first: str = sp.ZERO_FROM,
              msg: str = "Subject line\n\nBody.\n", files_only=False) -> Path:
        d = self.tmp / "series"
        d.mkdir(exist_ok=True)
        text = (f"{first}\nFrom: A <a@example.invalid>\nDate: Thu, 1 Jan 2026 12:00:00 +0100\n"
                f"Subject: [PATCH] t\n\n{msg}---\n f | 1 +\n\n{body}")
        (d / name).write_bytes(text.encode())
        return d

    def diff(self, path: str, extra: str = "", hunk: str = "@@ -1 +1 @@\n-a\n+b\n",
             index: str = "index " + "1" * 40 + ".." + "2" * 40 + " 100644\n") -> str:
        return f"diff --git a/{path} b/{path}\n{extra}{index}--- a/{path}\n+++ b/{path}\n{hunk}"

    def check(self, d: Path, **opts) -> sp.CheckReport:
        rep = sp.CheckReport()
        sp.check_series_dir(d, sp.CheckOptions(**opts), rep, "series")
        return rep

    def test_clean_patch_passes(self):
        rep = self.check(self.patch(self.diff("src/main.c")))
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.patches, 1)

    def test_git_binary_patch_rejected(self):
        body = ("diff --git a/x.dat b/x.dat\nindex " + "1" * 40 + ".." + "2" * 40 + " 100644\n"
                "GIT binary patch\nliteral 3\nKcmZ?d00001\n\n")
        rep = self.check(self.patch(body))
        self.assertTrue(any("binary patch" in e for e in rep.errors), rep.errors)

    def test_binary_files_differ_rejected(self):
        body = ("diff --git a/x.dat b/x.dat\nindex " + "1" * 40 + ".." + "2" * 40 + " 100644\n"
                "Binary files a/x.dat and b/x.dat differ\n")
        rep = self.check(self.patch(body))
        self.assertTrue(any("binary patch" in e for e in rep.errors), rep.errors)

    def test_forbidden_extension_rejected(self):
        for path in ("SamTFE/Textures/x.tex", "Levels/a.WLD", "Bin/tool.exe", "Github/shot.png",
                     "models/net.safetensors"):
            with self.subTest(path=path):
                shutil.rmtree(self.tmp / "series", ignore_errors=True)
                rep = self.check(self.patch(self.diff(path)))
                self.assertTrue(any("forbidden extension" in e for e in rep.errors), rep.errors)

    def test_forbidden_paths_rejected(self):
        for path in ("SamTSE/Demos/auto.ini", "Tools.Win32/readme.txt", "OverridenTextures/x.txt",
                     "work/extracted/a.txt", "Images/notes.txt"):
            with self.subTest(path=path):
                shutil.rmtree(self.tmp / "series", ignore_errors=True)
                rep = self.check(self.patch(self.diff(path)))
                self.assertTrue(any("forbidden path" in e or "local-only" in e for e in rep.errors),
                                rep.errors)

    def test_flagged_needs_review(self):
        for path in ("SamTFE/Sources/Entities/Player.es", "Sources/Engine/Sound/DSOUND.H",
                     "SamTSE/Sources/Engine/Sound/dsound.h", "Sources/LWSkaExporter/SDK/lwio.h",
                     "SamTSE/Scripts/Menu/x.lua"):
            with self.subTest(path=path):
                shutil.rmtree(self.tmp / "series", ignore_errors=True)
                d = self.patch(self.diff(path))
                rep = self.check(d)
                self.assertTrue(any("flagged" in e for e in rep.errors), rep.errors)
                rep = self.check(d, allow_flagged=True)
                self.assertEqual(rep.errors, [])
                self.assertTrue(any("flagged" in w for w in rep.warnings))

    def test_entities_mp_not_flagged(self):
        rep = self.check(self.patch(self.diff("SamTSE/Sources/EntitiesMP/Player.es")))
        self.assertEqual(rep.errors, [])

    def test_flagged_delete_always_rejected(self):
        body = ("diff --git a/Sources/Engine/Sound/DSOUND.H b/Sources/Engine/Sound/DSOUND.H\n"
                "deleted file mode 100644\nindex " + "1" * 40 + ".." + "0" * 40 + "\n"
                "--- a/Sources/Engine/Sound/DSOUND.H\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n")
        rep = self.check(self.patch(body), allow_flagged=True)
        self.assertTrue(any("full removed content" in e for e in rep.errors), rep.errors)
        self.assertTrue(any("deleting a flagged file" in e for e in rep.errors), rep.errors)

    def test_full_content_deletion_rejected(self):
        body = ("diff --git a/src/lib.c b/src/lib.c\ndeleted file mode 100644\nindex " + "1" * 40 + ".." + "0" * 40 + "\n"
                "--- a/src/lib.c\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-int a;\n-int b;\n")
        rep = self.check(self.patch(body))
        self.assertTrue(any("full removed content" in e for e in rep.errors), rep.errors)

    def test_content_free_deletion_allowed(self):
        body = ("diff --git a/SamTFE/SE1_10b.gro b/SamTFE/SE1_10b.gro\ndeleted file mode 100644\nindex "
                + "1" * 40 + ".." + "0" * 40 + "\n"
                "diff --git a/Sources/Engine/Sound/DSOUND.H b/Sources/Engine/Sound/DSOUND.H\n"
                "deleted file mode 100644\nindex " + "2" * 40 + ".." + "0" * 40 + "\n")
        rep = self.check(self.patch(body))
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("deleted without content" in w for w in rep.warnings), rep.warnings)
        self.assertTrue(any("flagged file without content" in w for w in rep.warnings), rep.warnings)

    def test_signoff_rejected(self):
        d = self.patch(self.diff("a.c"), msg="Subject\n\nBody.\n\nSigned-off-by: X <x@example.invalid>\n")
        rep = self.check(d)
        self.assertTrue(any("Signed-off-by" in e for e in rep.errors), rep.errors)
        rep = self.check(d, allow_signoff=True)
        self.assertEqual(rep.errors, [])

    def test_size_limit(self):
        big = "@@ -1 +1,4000 @@\n-a\n" + "".join(f"+line {i} xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n" for i in range(4000))
        d = self.patch(self.diff("a.c", hunk=big))
        self.assertTrue(any("KiB limit" in e for e in self.check(d, max_patch_kib=64).errors))
        self.assertEqual(self.check(d, max_patch_kib=1024).errors, [])

    def test_nondeterministic_headers_rejected(self):
        d = self.patch(self.diff("a.c"), first="From 1234567890123456789012345678901234567890 Mon Sep 17 00:00:00 2001")
        self.assertTrue(any("zero-commit" in e for e in self.check(d).errors))
        shutil.rmtree(d)
        d = self.patch(self.diff("a.c") + "-- \n2.55.0\n\n")
        self.assertTrue(any("signature" in e for e in self.check(d).errors))
        shutil.rmtree(d)
        d = self.patch(self.diff("a.c", index="index 1111111..2222222 100644\n"))
        self.assertTrue(any("abbreviated" in e for e in self.check(d).errors))

    def test_names_and_numbering(self):
        d = self.patch(self.diff("a.c"), name="0001-a.patch")
        self.patch(self.diff("b.c"), name="0003-b.patch")
        (d / "notes.txt").write_text("x")
        errs = self.check(d).errors
        self.assertTrue(any("contiguous" in e for e in errs), errs)
        self.assertTrue(any("NNNN-<slug>.patch" in e for e in errs), errs)

    def test_submodule_and_symlink_rejected(self):
        body = ("diff --git a/ext/lib b/ext/lib\nnew file mode 160000\nindex " + "0" * 40 + ".." + "3" * 40 + "\n"
                "--- /dev/null\n+++ b/ext/lib\n@@ -0,0 +1 @@\n+Subproject commit " + "3" * 40 + "\n"
                "diff --git a/link b/link\nnew file mode 120000\nindex " + "0" * 40 + ".." + "4" * 40 + "\n"
                "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+target\n\\ No newline at end of file\n")
        errs = self.check(self.patch(body)).errors
        self.assertTrue(any("submodule" in e for e in errs), errs)
        self.assertTrue(any("symbolic link" in e for e in errs), errs)

    def test_new_file_without_spdx_warns(self):
        body = ("diff --git a/n.c b/n.c\nnew file mode 100644\nindex " + "0" * 40 + ".." + "5" * 40 + "\n"
                "--- /dev/null\n+++ b/n.c\n@@ -0,0 +1 @@\n+int x;\n")
        rep = self.check(self.patch(body))
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("SPDX" in w for w in rep.warnings))

    def test_quoted_path_parsed(self):
        body = ('diff --git "a/dir/caf\\303\\251.tex" "b/dir/caf\\303\\251.tex"\nindex ' + "1" * 40 + ".." + "2" * 40 +
                ' 100644\n--- "a/dir/caf\\303\\251.tex"\n+++ "b/dir/caf\\303\\251.tex"\n@@ -1 +1 @@\n-a\n+b\n')
        errs = self.check(self.patch(body)).errors
        self.assertTrue(any("café.tex" in e and "forbidden extension" in e for e in errs), errs)

    def test_validator_lists_read_as_data(self):
        v = self.tmp / "validate_repo.py"
        v.write_text('import sys\nsys.exit("must not run")\nFORBIDDEN_EXTENSIONS = {".gro", ".new"}\n'
                     'FORBIDDEN_DIR_PARTS = {"extracted"}\n', encoding="utf-8")
        ext, dirs = sp.read_validator_lists(v)
        self.assertEqual(ext, {".gro", ".new"})
        self.assertEqual(dirs, {"extracted"})

    @unittest.skipUnless(os.environ.get("SSTRE_UMBRELLA_VALIDATOR"), "SSTRE_UMBRELLA_VALIDATOR not set")
    def test_copy_matches_umbrella_validator(self):
        ext, dirs = sp.read_validator_lists(Path(os.environ["SSTRE_UMBRELLA_VALIDATOR"]))
        self.assertLessEqual(ext, sp.FORBIDDEN_EXTENSIONS, "update FORBIDDEN_EXTENSIONS from the umbrella")
        self.assertLessEqual(dirs, sp.FORBIDDEN_DIR_PARTS, "update FORBIDDEN_DIR_PARTS from the umbrella")


# --------------------------------------------------------------------------
class TestLock(Base):
    def lock(self, **over) -> Path:
        root = self.tmp / "e"
        root.mkdir(exist_ok=True)
        u = {"name": "eng", "role": "primary", "repository": "https://github.com/example/eng",
             "commit": "a" * 40, "patch_series": "patches/eng"}
        u.update(over)
        (root / sp.LOCK_NAME).write_text(json.dumps({"schema_version": "0.1", "upstreams": [u]}))
        return root

    def test_valid_dependency_role(self):
        ups = sp.load_lock(self.lock(role="dependency", swhid="swh:1:rev:" + "a" * 40))
        self.assertEqual(ups[0].role, "dependency")

    def test_invalid_entries(self):
        for over in ({"commit": "abc123"}, {"role": "fork"}, {"patch_series": "patches/other"},
                     {"swhid": "swh:1:rev:" + "b" * 40}, {"repository": "http://example.com/x"}):
            with self.subTest(over=over):
                with self.assertRaises(sp.ToolError):
                    sp.load_lock(self.lock(**over))


# --------------------------------------------------------------------------
class TestRoundTrip(Base):
    def setUp(self):
        super().setUp()
        self.up, self.pin = self.make_upstream()
        self.root = self.make_engine(self.pin)
        self.cache = self.tmp / "cache"
        self.branch = self.sstre_branch(self.up)

    def fetch(self, *extra):
        return self.main("--root", str(self.root), "--cache", str(self.cache), "fetch", "--offline",
                         "--source", f"eng={self.up}", *extra)

    def test_fetch_offline_and_cache_hit(self):
        rc, out = self.fetch()
        self.assertEqual(rc, 0, out)
        self.assertIn("from local", out)
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "fetch", "--offline")
        self.assertEqual(rc, 0, out)
        self.assertIn("from cache", out)

    def test_fetch_offline_without_source_fails(self):
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "fetch", "--offline")
        self.assertEqual(rc, 2)
        self.assertIn("--offline", out)

    def test_fetch_missing_commit_fails(self):
        other = self.tmp / "other"
        other.mkdir()
        run_git(other, "init", "-q")
        write(other, "x", "x")
        commit(other, "unrelated")
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "fetch", "--offline",
                            "--source", f"eng={other}")
        self.assertEqual(rc, 2)
        self.assertIn("does not contain", out)

    def test_export_apply_round_trip(self):
        self.assertEqual(self.fetch()[0], 0)
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "export", "eng",
                            "--from", self.branch, "--source-repo", str(self.up), "--verify")
        self.assertEqual(rc, 0, out)
        self.assertIn("round trip ok", out)
        files = sorted(p.name for p in (self.root / "patches/eng").iterdir())
        self.assertEqual(len(files), 3)
        self.assertTrue(files[0].startswith("0001-build-change-B"))
        first = (self.root / "patches/eng" / files[0]).read_bytes()
        self.assertTrue(first.startswith(sp.ZERO_FROM.encode()))
        self.assertIn(b"<B>3</B>\r\n", first)                    # CRLF content preserved
        self.assertNotIn(b"Signed-off-by", first)
        # apply into a fresh tree: same tree as the branch, reproducible commit IDs
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "apply",
                            "--out", str(self.tmp / "w1"))
        self.assertEqual(rc, 0, out)
        r1 = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(r1["tree"], run_git(self.up, "rev-parse", f"{self.branch}^{{tree}}"))
        self.assertEqual(r1["patches"], 3)
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "apply",
                            "--out", str(self.tmp / "w2"))
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["head"], r1["head"])
        mode = run_git(Path(r1["worktree"]), "ls-files", "-s", "src/main.c").split()[0]
        self.assertEqual(mode, "100755")
        # existing worktree without --force
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "apply",
                            "--out", str(self.tmp / "w1"))
        self.assertEqual(rc, 2)
        self.assertIn("--force", out)
        rc, _ = self.main("--root", str(self.root), "--cache", str(self.cache), "apply",
                          "--out", str(self.tmp / "w1"), "--force", "--expect-tree", "0" * 40)
        self.assertEqual(rc, 1)

    def test_irreversible_delete_round_trip(self):
        self.assertEqual(self.fetch()[0], 0)
        write(self.up, "src/noeol.txt", "no newline at end")
        commit(self.up, "add file without final newline")
        for rel in ("src/win.vcxproj", "data/blob.bin", "src/noeol.txt", "Sources/Entities/Enemy.es"):
            (self.up / rel).unlink()
        commit(self.up, "remove third-party files")
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "export", "eng",
                            "--from", self.branch, "--source-repo", str(self.up), "--verify")
        self.assertEqual(rc, 0, out)
        self.assertIn("round trip ok", out)
        self.assertIn('"expanded_deletions": 4', out)
        last = sorted((self.root / "patches/eng").iterdir())[-1].read_bytes()
        self.assertIn(b"deleted file mode", last)
        self.assertNotIn(b"<B>3</B>", last)              # deleted content is not reproduced
        self.assertNotIn(b"enemy", last)
        self.assertNotIn(b"GIT binary patch", last)
        # a tampered preimage blob ID must not delete a different file version
        p = sorted((self.root / "patches/eng").iterdir())[-1]
        tampered = last.replace(run_git(self.up, "rev-parse", f"{self.pin}:Sources/Entities/Enemy.es").encode(),
                                b"f" * 40)
        self.assertNotEqual(tampered, last)
        p.write_bytes(tampered)
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "apply",
                            "--out", str(self.tmp / "wt"))
        self.assertEqual(rc, 2)
        self.assertIn("expected blob", out)

    def test_export_is_deterministic(self):
        self.assertEqual(self.fetch()[0], 0)
        args = ["--root", str(self.root), "--cache", str(self.cache), "export", "eng",
                "--from", self.branch, "--source-repo", str(self.up)]
        self.assertEqual(self.main(*args)[0], 0)
        first = {p.name: p.read_bytes() for p in (self.root / "patches/eng").iterdir()}
        self.assertEqual(self.main(*args)[0], 0)
        second = {p.name: p.read_bytes() for p in (self.root / "patches/eng").iterdir()}
        self.assertEqual(first, second)

    def test_round_trip_detects_mismatch(self):
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.main("--root", str(self.root), "--cache", str(self.cache), "export", "eng",
                                   "--from", self.branch, "--source-repo", str(self.up))[0], 0)
        write(self.up, "src/main.c", "changed later\n")
        commit(self.up, "later change")
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "verify", "eng",
                            "--from", self.branch, "--source-repo", str(self.up))
        self.assertEqual(rc, 1, out)

    def test_export_rejects_bad_history(self):
        self.assertEqual(self.fetch()[0], 0)
        # merge commit
        run_git(self.up, "checkout", "-q", "-b", "side", self.pin)
        write(self.up, "side.txt", "s\n")
        commit(self.up, "side")
        run_git(self.up, "checkout", "-q", self.branch)
        run_git(self.up, "merge", "-q", "--no-ff", "-m", "merge", "side")
        rc, out = self.main("--root", str(self.root), "export", "eng", "--from", self.branch,
                            "--source-repo", str(self.up))
        self.assertEqual(rc, 2)
        self.assertIn("merge", out)
        # branch not based on the pin
        run_git(self.up, "checkout", "-q", "--orphan", "orphan")
        write(self.up, "o.txt", "o\n")
        commit(self.up, "orphan")
        rc, out = self.main("--root", str(self.root), "export", "eng", "--from", "orphan",
                            "--source-repo", str(self.up))
        self.assertEqual(rc, 2)
        self.assertIn("not based on the pinned commit", out)

    def test_export_refuses_forbidden_content_and_keeps_series(self):
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.main("--root", str(self.root), "export", "eng", "--from", self.branch,
                                   "--source-repo", str(self.up))[0], 0)
        before = sorted(p.name for p in (self.root / "patches/eng").iterdir())
        write(self.up, "data/blob.bin", b"\x00\x01changed")
        commit(self.up, "binary change")
        rc, out = self.main("--root", str(self.root), "export", "eng", "--from", self.branch,
                            "--source-repo", str(self.up))
        self.assertEqual(rc, 1, out)
        self.assertIn("binary patch", out)
        self.assertEqual(sorted(p.name for p in (self.root / "patches/eng").iterdir()), before)

    def test_export_rejects_signoff_and_flagged(self):
        self.assertEqual(self.fetch()[0], 0)
        write(self.up, "Sources/Entities/Enemy.es", "enemy v2\n")
        commit(self.up, "touch entities\n\nSigned-off-by: Someone <s@example.invalid>")
        rc, out = self.main("--root", str(self.root), "export", "eng", "--from", self.branch,
                            "--source-repo", str(self.up))
        self.assertEqual(rc, 1)
        self.assertIn("Signed-off-by", out)
        self.assertIn("flagged", out)
        rc, out = self.main("--root", str(self.root), "--cache", str(self.cache), "export", "eng",
                            "--from", self.branch, "--source-repo", str(self.up),
                            "--allow-signoff", "--allow-flagged", "--verify")
        self.assertEqual(rc, 0, out)

    def test_check_cli_on_series_and_unknown_dir(self):
        self.assertEqual(self.fetch()[0], 0)
        self.assertEqual(self.main("--root", str(self.root), "export", "eng", "--from", self.branch,
                                   "--source-repo", str(self.up))[0], 0)
        rc, out = self.main("--root", str(self.root), "check")
        self.assertEqual(rc, 0, out)
        self.assertIn("3 patch(es)", out)
        (self.root / "patches" / "stray").mkdir()
        rc, out = self.main("--root", str(self.root), "check")
        self.assertEqual(rc, 1)
        self.assertIn("no upstream with this name", out)


if __name__ == "__main__":
    unittest.main()
