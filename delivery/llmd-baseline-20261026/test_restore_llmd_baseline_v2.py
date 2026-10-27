"""Synthetic CPU tests for restore_llmd_baseline_v2.sh.

A copy of the script is patched with tiny fixture constants; the production
script keeps the real pinned hashes (asserted below) and is never weakened.
No network, Docker or real archive is touched; `docker` is a fake on PATH.
"""

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "restore_llmd_baseline_v2.sh"
REAL_ARCHIVE_SHA = "c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47"
PART_NAMES = [f"llmd-baseline.docker.tar.part-0{i}" for i in range(1, 5)]
FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "docker $*" >> "$FAKE_DOCKER_LOG"
exit 0
"""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class RestoreV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.parts = [f"payload-{i}-".encode() * 7 for i in range(4)]
        self.archive = b"".join(self.parts)
        self.dir = self.tmp / "assets"
        self.dir.mkdir()
        for name, raw in zip(PART_NAMES, self.parts, strict=True):
            (self.dir / name).write_bytes(raw)
        pairs = zip(PART_NAMES, self.parts, strict=True)
        lines = [f"{sha(raw)}  {name}" for name, raw in pairs]
        lines.append(f"{sha(self.archive)}  llmd-baseline.docker.tar")
        (self.dir / "SHA256SUMS").write_text("\n".join(lines) + "\n")
        self.script = self.tmp / "patched.sh"
        self.script.write_text(
            self.patched(sha(self.archive), len(self.archive), len(self.parts[0]))
        )
        self.script.chmod(0o755)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.docker_log = self.tmp / "docker.log"
        fake = self.bin / "docker"
        fake.write_text(FAKE_DOCKER)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def patched(self, archive_sha, archive_bytes, part_bytes):
        text = SCRIPT.read_text()
        self.assertIn(f"ARCHIVE_SHA256='{REAL_ARCHIVE_SHA}'", text)
        self.assertIn("ARCHIVE_BYTES=5923200000", text)
        text = text.replace(
            f"ARCHIVE_SHA256='{REAL_ARCHIVE_SHA}'", f"ARCHIVE_SHA256='{archive_sha}'"
        )
        text = text.replace("ARCHIVE_BYTES=5923200000", f"ARCHIVE_BYTES={archive_bytes}")
        text = text.replace("PART_BYTES=1480800000", f"PART_BYTES={part_bytes}")
        hashes = "\n".join(f"  {sha(raw)}" for raw in self.parts)
        pattern = r"PART_SHA256=\(\n(?:  [0-9a-f]{64}\n){4}\)"
        text, n = re.subn(pattern, f"PART_SHA256=(\n{hashes}\n)", text)
        self.assertEqual(n, 1)
        return text

    def run_script(self, *args, docker=False):
        env = dict(os.environ, FAKE_DOCKER_LOG=str(self.docker_log))
        env["PATH"] = (str(self.bin) + ":" if docker else "") + "/usr/bin:/bin"
        return subprocess.run(
            ["bash", str(self.script), *args],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_production_script_keeps_real_pins_and_rejects_unknown_args(self):
        text = SCRIPT.read_text()
        self.assertIn(REAL_ARCHIVE_SHA, text)
        self.assertEqual(text.count("\r"), 0)
        for args in ([], ["bogus"], ["assemble", "--what"], ["assemble", "--dir"]):
            result = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 64, args)
        names = sorted(p.name for p in self.tmp.iterdir())
        self.assertEqual(names, ["assets", "bin", "patched.sh"])

    def test_assemble_then_second_invocation_refuses_and_verifies(self):
        out = self.dir / "llmd-baseline.docker.tar"
        first = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(out.read_bytes(), self.archive)
        self.assertFalse((self.dir / "llmd-baseline.docker.tar.partial").exists())
        second = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(second.returncode, 73)
        self.assertIn("refusing to clobber", second.stderr)
        self.assertEqual(out.read_bytes(), self.archive)
        verify = self.run_script("verify-archive", "--dir", str(self.dir))
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn("PASS archive", verify.stdout)

    def test_corrupt_or_missing_part_refused_before_any_output(self):
        corrupt = self.dir / PART_NAMES[2]
        corrupt.write_bytes(self.parts[2][:-1] + b"X")
        result = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 65)
        self.assertIn("sha256 mismatch", result.stderr)
        corrupt.unlink()
        result = self.run_script("verify-parts", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 66)
        self.assertIn("missing or non-regular part", result.stderr)
        expected = sorted(PART_NAMES[:2] + PART_NAMES[3:] + ["SHA256SUMS"])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), expected)

    def test_incomplete_or_wrong_sha256sums_refused(self):
        sums = self.dir / "SHA256SUMS"
        sums.write_text("\n".join(sums.read_text().splitlines()[:3]) + "\n")
        result = self.run_script("verify-parts", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 65)
        self.assertIn("SHA256SUMS disagrees", result.stderr)
        sums.unlink()
        self.assertEqual(self.run_script("verify-parts", "--dir", str(self.dir)).returncode, 0)

    def test_refuses_existing_output_partial_and_symlinks(self):
        out = self.dir / "llmd-baseline.docker.tar"
        partial = self.dir / "llmd-baseline.docker.tar.partial"
        out.symlink_to(self.tmp / "nowhere")
        result = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 73)
        self.assertTrue(out.is_symlink())
        out.unlink()
        partial.write_bytes(b"old failure")
        result = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 73)
        self.assertEqual(partial.read_bytes(), b"old failure")
        partial.unlink()
        partial.symlink_to(self.tmp / "dangling")
        result = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 73)
        self.assertTrue(partial.is_symlink())
        self.assertFalse(out.exists())

    def test_failed_full_hash_preserves_partial_and_blocks_docker_load(self):
        self.script.write_text(self.patched("0" * 64, len(self.archive), len(self.parts[0])))
        # Without this the pinned-vs-SHA256SUMS cross-check would fail first.
        (self.dir / "SHA256SUMS").unlink()
        result = self.run_script("assemble", "--dir", str(self.dir))
        self.assertEqual(result.returncode, 65)
        self.assertIn("failed partial preserved", result.stderr)
        failed = [p for p in self.dir.iterdir() if ".partial.failed-" in p.name]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].read_bytes(), self.archive)
        self.assertFalse((self.dir / "llmd-baseline.docker.tar").exists())
        (self.dir / "llmd-baseline.docker.tar").write_bytes(self.archive)
        result = self.run_script("docker-load", "--dir", str(self.dir), docker=True)
        self.assertEqual(result.returncode, 65)
        self.assertIn("archive mismatch", result.stderr)
        self.assertFalse(self.docker_log.exists())

    def test_docker_load_runs_only_after_verified_archive(self):
        out = self.dir / "llmd-baseline.docker.tar"
        out.write_bytes(self.archive)
        result = self.run_script("docker-load", "--dir", str(self.dir), docker=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.docker_log.read_text().splitlines()[0], f"docker load -i {out}")
        out.write_bytes(self.archive[:-1])
        self.docker_log.unlink()
        result = self.run_script("docker-load", "--dir", str(self.dir), docker=True)
        self.assertEqual(result.returncode, 65)
        self.assertFalse(self.docker_log.exists())

    def test_destination_directory_race_preserves_verified_partial(self):
        # Simulate a destination appearing only after assembly/hash verification.
        # Real ln must receive -T so it cannot silently publish inside a directory.
        fake_ln = self.bin / "ln"
        for kind in ("directory", "symlink"):
            with self.subTest(kind=kind):
                out = self.tmp / ("out-" + kind)
                target = self.tmp / ("target-" + kind)
                action = 'mkdir -- "$out"'
                if kind == "symlink":
                    target.mkdir()
                    action = f'/usr/bin/ln -s -- "{target}" "$out"'
                fake_ln.write_text(
                    '#!/usr/bin/env bash\nset -e\nout="${@: -1}"\n'
                    + action
                    + '\nexec /usr/bin/ln "$@"\n'
                )
                fake_ln.chmod(0o755)
                result = self.run_script(
                    "assemble", "--dir", str(self.dir), "--output", str(out), docker=True
                )
                self.assertEqual(result.returncode, 73, result.stderr)
                self.assertEqual(Path(str(out) + ".partial").read_bytes(), self.archive)
                self.assertFalse((out / (out.name + ".partial")).exists())
                self.assertFalse(self.docker_log.exists())


if __name__ == "__main__":
    unittest.main()
