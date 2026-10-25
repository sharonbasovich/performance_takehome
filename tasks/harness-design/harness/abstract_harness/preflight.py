"""Read-only Linux host inspection. No installs, pulls, inference, or provider calls."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
GIB = 1024**3
MAX_JSON = 8 * 1024 * 1024
BDF = re.compile(r"(?:[0-9a-f]{4}:)?[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", re.I)


def load_json(path: Path) -> Any:
    if path.stat().st_size > MAX_JSON:
        raise ValueError("JSON input exceeds 8 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command(
    args: list[str], timeout: float = 20, extra_env: dict[str, str] | None = None
) -> tuple[bool, str]:
    """Bound time/output without retaining stderr or inherited credentials in reports."""
    # These are explicitly supplied local system programs, not a shell command.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}}
    env.update({"PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0"})
    env.update(extra_env or {})
    from .procs import kill_process_group

    with tempfile.TemporaryFile() as output:
        proc = None
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + timeout
                while proc.poll() is None:
                    if time.monotonic() > deadline or output.tell() > MAX_JSON:
                        raise subprocess.TimeoutExpired(args, timeout)
                    time.sleep(0.05)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, 9)
                proc.wait(timeout=5)
                return False, "command exceeded time/output limit"
            if output.tell() > MAX_JSON:
                return False, "command output exceeds 8 MiB"
            output.seek(0)
            return proc.returncode == 0, output.read(MAX_JSON).decode("utf-8", "replace")
        except OSError:
            return False, "command unavailable or inaccessible"
        finally:
            if proc is not None:
                kill_process_group(proc, grace_s=0.2)


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, status: str, detail: str, action: str = "", **evidence: Any) -> None:
        self.checks.append(
            {
                "check": name,
                "status": status,
                "detail": detail,
                "next_action": action,
                "evidence": evidence,
            }
        )

    def guarded(self, name: str, action: str, check: Any) -> None:
        try:
            check()
        except (OSError, ValueError, KeyError, TypeError, tarfile.TarError):
            # Exception text can contain private configuration values. Keep it out.
            self.add(name, "FAIL", "Input inaccessible, malformed, or inconsistent", action)

    def result(self) -> dict[str, Any]:
        statuses = [c["status"] for c in self.checks]
        return {
            "schema_version": 1,
            "kind": "offline_host_inspection_not_inference_certification",
            "status": "FAIL"
            if "FAIL" in statuses
            else "MISSING"
            if "MISSING" in statuses
            else "PASS",
            "checks": self.checks,
            "limitations": [
                "PASS certifies only these observations, not GPU inference or final image quality.",
                "No provider credentials or registry authentication are used.",
                "Single-device visibility does not prove exclusive tenancy or an approved lease.",
                "Trusted checksum inputs must come from the pinned snapshot source.",
                "Pi top-level artifact verification does not freeze its transitive dependencies.",
            ],
        }


def normalize_bdf(value: str) -> str:
    match = BDF.fullmatch(value.strip())
    if not match:
        raise ValueError("invalid PCI BDF")
    value = match.group().lower()
    return "0000:" + value if value.count(":") == 1 else value


def gpu_records(data: Any) -> list[dict[str, str]]:
    """Accept ROCm-SMI card maps and AMD-SMI per-GPU nested JSON records."""
    records: list[dict[str, str]] = []

    def flatten(node: Any, out: dict[str, str]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (str, int, float)):
                    out[str(key).lower().replace("_", " ")] = str(value)
                else:
                    flatten(value, out)

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, dict):
            flat: dict[str, str] = {}
            flatten(node, flat)
            # A record must have both a model name and a PCI address. Never infer
            # MI355X from a device node, aggregate text, or an unrelated GPU.
            names = [
                v for k, v in flat.items() if k in {"market name", "card series", "card model"}
            ]
            buses = [v for k, v in flat.items() if k in {"bdf", "pci bus", "pci bus id"}]
            children = [v for v in node.values() if isinstance(v, (dict, list))]
            nested_record = False
            for child in children:
                child_flat: dict[str, str] = {}
                flatten(child, child_flat)
                nested_record = nested_record or (
                    any(k in child_flat for k in ("market name", "card series", "card model"))
                    and any(k in child_flat for k in ("bdf", "pci bus", "pci bus id"))
                )
            if (
                names
                and buses
                and not nested_record
                and not any(
                    isinstance(v, list)
                    or isinstance(v, dict)
                    and any(str(k).startswith("card") for k in v)
                    for v in children
                )
            ):
                records.append({"name": names[0], "bdf": normalize_bdf(buses[0])})
            else:
                for value in children:
                    visit(value)

    # card0/card1 must remain distinct, even when both identify the same SKU.
    if isinstance(data, dict) and any(re.fullmatch(r"card\d+", str(k)) for k in data):
        for key, value in data.items():
            if re.fullmatch(r"card\d+", str(key)):
                visit(value)
    else:
        visit(data)
    return records


def check_gpu(report: Report, render: str) -> None:
    if not re.fullmatch(r"/dev/dri/renderD\d+", render):
        raise ValueError("invalid render device")
    amd = []
    for path in Path("/sys/class/drm").glob("renderD*/device/vendor"):
        if path.read_text().strip().lower() == "0x1002":
            amd.append(path.parent.parent.name)
    if len(amd) != 1 or amd[0] != Path(render).name:
        report.add(
            "gpu_assignment",
            "FAIL",
            "Exactly one assigned AMD render device must be visible",
            "Use an isolated one-MI355X allocation; verify the assigned render device",
            visible_amd=amd,
        )
        return
    for device in (Path("/dev/kfd"), Path(render)):
        if not stat.S_ISCHR(device.stat().st_mode) or not os.access(device, os.R_OK | os.W_OK):
            raise ValueError("GPU device not accessible")
    sysdev = Path("/sys/class/drm") / Path(render).name / "device"
    bus = normalize_bdf(sysdev.resolve().name)
    memory = int((sysdev / "mem_info_vram_total").read_text().strip())
    records = []
    for args in (
        ["rocm-smi", "--showproductname", "--showbus", "--showmeminfo", "vram", "--json"],
        ["amd-smi", "static", "--asic", "--bus", "--vram", "--json"],
    ):
        ok, raw = command(args)
        if ok:
            try:
                records = gpu_records(json.loads(raw))
            except (ValueError, TypeError):
                continue
            if records:
                break
    selected = [r for r in records if r["bdf"] == bus]
    if len(selected) != 1:
        report.add(
            "gpu_identity",
            "MISSING",
            "SMI has not established MI355X identity for the selected PCI device",
            "Install/use read-only rocm-smi or amd-smi and verify its PCI BDF/model output",
            pci_bdf=bus,
        )
        return
    if not re.search(r"\bMI355X\b", selected[0]["name"], re.I):
        report.add(
            "gpu_identity",
            "FAIL",
            "Selected physical GPU is not MI355X",
            "Use MI355X for exact target evidence; other GPUs are development stand-ins",
            **selected[0],
        )
        return
    report.add(
        "gpu_identity",
        "PASS" if memory >= 256 * GIB else "FAIL",
        "SMI model identity correlated with sysfs render device and VRAM",
        "Verify full MI355X memory assignment if VRAM is below 256 GiB",
        **selected[0],
        vram_bytes=memory,
    )
    ok, raw = command(["rocminfo"])
    report.add(
        "rocm_driver",
        "PASS" if ok and re.search(r"\bgfx950\b", raw) else "MISSING",
        "Read-only ROCm agent enumeration must expose gfx950",
        "Make rocminfo available and verify the assigned MI355X driver/permissions",
    )


def check_capacity(report: Report, disk: Path, min_free: float) -> None:
    cpus = len(os.sched_getaffinity(0))
    memory = (
        int(re.search(r"^MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)[1]) * 1024
    )
    limit = Path("/sys/fs/cgroup/memory.max")
    if limit.exists() and limit.read_text().strip() != "max":
        memory = min(memory, int(limit.read_text().strip()))
    quota = Path("/sys/fs/cgroup/cpu.max")
    cpu_capacity = float(cpus)
    if quota.exists():
        count, period = quota.read_text().split()
        if count != "max":
            cpu_capacity = min(cpu_capacity, int(count) / int(period))
    free = shutil.disk_usage(disk).free
    report.add(
        "cpu_ram",
        "PASS" if cpu_capacity >= 24 and memory >= 144 * GIB else "FAIL",
        "Planning capacity: 16 serving cores/128 GiB plus 8 client cores/16 GiB",
        "Use 24 available cores/144 GiB RAM or document approved separate client capacity",
        cpu_capacity=cpu_capacity,
        effective_memory_bytes=memory,
    )
    report.add(
        "disk",
        "PASS" if free >= min_free * GIB else "FAIL",
        "Working-filesystem free space; threshold is a candidate planning estimate",
        "Free/allocate storage or revise the explicit --min-free-gib plan",
        free_bytes=free,
        min_free_gib=min_free,
    )
    shm = shutil.disk_usage("/dev/shm").total
    report.add(
        "shm",
        "PASS",
        "Container --shm-size=16g is separate from host /dev/shm capacity",
        host_shm_bytes=shm,
        required_container_shm_bytes=16 * GIB,
    )


def check_docker(report: Report, lock: dict[str, Any]) -> None:
    # Never inspect a remote daemon while reporting local GPU inventory.
    host = os.environ.get("DOCKER_HOST", "")
    context = os.environ.get("DOCKER_CONTEXT", "")
    if host or context and context != "default":
        report.add(
            "docker",
            "FAIL",
            "Remote/overridden Docker endpoint is not accepted",
            "Unset DOCKER_HOST/DOCKER_CONTEXT and use the assigned host's local default daemon",
        )
        return
    ok, endpoint = command(
        ["docker", "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"]
    )
    if not ok or not endpoint.strip('"\n').startswith("unix://"):
        report.add(
            "docker",
            "MISSING",
            "Local Unix Docker endpoint not established",
            "Configure a local Docker daemon/context; this command never changes it",
        )
        return
    ok, raw = command(["docker", "info", "--format", "{{json .}}"])
    if not ok:
        report.add(
            "docker",
            "MISSING",
            "Local Docker daemon is inaccessible",
            "Grant approved Docker access and retry",
        )
        return
    data = json.loads(raw)
    architecture = data.get("Architecture")
    report.add(
        "docker",
        "PASS" if data.get("OSType") == "linux" and architecture in {"x86_64", "amd64"} else "FAIL",
        "Local Docker daemon platform inspected",
        "Use Linux/amd64 Docker",
        version=data.get("ServerVersion"),
    )
    root = Path(data["DockerRootDir"])
    free = shutil.disk_usage(root).free
    report.add(
        "docker_storage",
        "PASS" if free >= 80 * GIB else "FAIL",
        "Docker filesystem needs working room for large unpacked LLMD layers/builds",
        "Allow at least 80 GiB free on Docker's filesystem (planning estimate)",
        free_bytes=free,
    )
    ok, raw = command(["docker", "buildx", "version"])
    report.add(
        "buildx",
        "PASS" if ok and re.search(r"\bv\d+\.\d+", raw) else "MISSING",
        "Buildx executable availability checked; no builder is started",
        "Install/enable Docker Buildx on the host",
    )
    ok, raw = command(["docker", "image", "inspect", lock["image"]])
    if not ok:
        report.add(
            "pinned_image",
            "MISSING",
            "Pinned baseline image is not cached locally",
            "When ready, explicitly pull the exact baseline/lock.json image before rerunning",
        )
        return
    image = json.loads(raw)[0]
    correct = (
        image.get("Architecture") == "amd64"
        and image.get("Os") == "linux"
        and image["Config"].get("Entrypoint") == [lock["entrypoint"]]
    )
    report.add(
        "pinned_image",
        "PASS" if correct else "FAIL",
        "Cached image platform/entrypoint inspected by pinned reference",
        "Use the exact protected baseline image and preserved entrypoint",
        config_id=image.get("Id"),
    )


def model_inventory(
    directory: Path, model: dict[str, str], manifest_path: Path | None, hash_files: bool
) -> dict[str, Any]:
    """Validate real files, pinned bookkeeping, index completeness, and trusted hashes."""
    if directory.is_symlink():
        raise ValueError("model directory must not be a symlink")
    marker = load_json(directory / ".abstract-model.json")
    if marker.get("status") != "complete" or any(
        marker.get(k) != model[k] for k in ("repository", "revision")
    ):
        raise ValueError("snapshot marker does not match protected model pin")
    paths = [p for p in directory.rglob("*") if ".cache" not in p.relative_to(directory).parts]
    if any(p.is_symlink() for p in paths) or any(
        p.name.endswith((".incomplete", ".lock")) for p in paths
    ):
        raise ValueError(
            "model must be complete materialized files, not symlinks/partial downloads"
        )
    config = load_json(directory / "config.json")
    if not isinstance(config, dict) or not config:
        raise ValueError("empty model config")
    if (
        not (directory / "tokenizer.json").is_file()
        or not (directory / "tokenizer_config.json").is_file()
    ):
        raise ValueError("tokenizer files missing")
    expected = {"config.json", "tokenizer.json", "tokenizer_config.json"}
    index = directory / "model.safetensors.index.json"
    if index.exists():
        weight_map = load_json(index)["weight_map"]
        if not isinstance(weight_map, dict) or not weight_map:
            raise ValueError("weight index missing")
        expected.add(index.name)
        expected.update(weight_map.values())
    else:
        expected.add("model.safetensors")
    for name in expected:
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name:
            raise ValueError("weight index escapes model directory")
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("model file missing/empty")
        if path.suffix == ".safetensors":
            with path.open("rb") as fh:
                size = int.from_bytes(fh.read(8), "little")
                if not 2 <= size <= MAX_JSON or size + 8 >= path.stat().st_size:
                    raise ValueError("truncated or invalid safetensors header")
                header = json.loads(fh.read(size))
                tensors = [v for k, v in header.items() if k != "__metadata__"]
                offsets = sorted(v["data_offsets"] for v in tensors)
                end = 0
                for start, stop in offsets:
                    if start != end or stop <= start:
                        raise ValueError("safetensors offsets incomplete/overlapping")
                    end = stop
                if not tensors or end != path.stat().st_size - size - 8:
                    raise ValueError("safetensors data truncated or trailing")
    result = {
        "required_files": len(expected),
        "repository": model["repository"],
        "revision": model["revision"],
    }
    if manifest_path is None:
        return {**result, "verified_hashes": False, "reason": "trusted manifest not supplied"}
    manifest = load_json(manifest_path)
    if any(manifest.get(k) != model[k] for k in ("repository", "revision")):
        raise ValueError("manifest model/revision mismatch")
    files = manifest["files"]
    if not isinstance(files, dict) or not expected <= files.keys():
        raise ValueError("manifest does not cover all required model files")
    for name, record in files.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name:
            raise ValueError("unsafe manifest path")
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record["size"]:
            raise ValueError("file missing or size mismatch")
        if "sha256" in record:
            if not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
                raise ValueError("invalid trusted sha256")
            if hash_files and digest(path) != record["sha256"]:
                raise ValueError("file hash mismatch")
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", record["git_blob_sha1"]):
                raise ValueError("invalid trusted Git blob id")
            if hash_files:
                h = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
                with path.open("rb") as fh:
                    for block in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != record["git_blob_sha1"]:
                    raise ValueError("Git blob hash mismatch")
    return {
        **result,
        "verified_hashes": hash_files,
        "total_snapshot_bytes": sum(record["size"] for record in files.values()),
        "reason": "full hashes checked"
        if hash_files
        else "sizes only; pass --hash-model for full integrity",
    }


def check_pi(report: Report, args: argparse.Namespace, profile: dict[str, Any]) -> None:
    if not all((args.node, args.node_sha256, args.pi_dir, args.pi_tarball)):
        report.add(
            "pi_artifact",
            "MISSING",
            "Verified Node binary and Pi archive/install are required",
            "Supply --node, trusted --node-sha256, --pi-dir and --pi-tarball; no install occurs",
        )
        return
    if not re.fullmatch(r"[0-9a-f]{64}", args.node_sha256) or digest(args.node) != args.node_sha256:
        raise ValueError("Node binary hash mismatch")
    actual = "sha512-" + base64.b64encode(bytes.fromhex(digest(args.pi_tarball, "sha512"))).decode()
    if actual != profile["pi"]["artifact_integrity"]:
        raise ValueError("Pi archive integrity mismatch")
    if args.pi_dir.is_symlink():
        raise ValueError("Pi package directory must be materialized")
    package = load_json(args.pi_dir / "package.json")
    if (
        package.get("name") != profile["pi"]["package"]
        or package.get("version") != profile["pi"]["version"]
    ):
        raise ValueError("Pi package/version mismatch")
    count = 0
    with tarfile.open(args.pi_tarball, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or path.parts[0] != "package"
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("unsafe Pi archive entry")
            if not member.isfile():
                continue
            target = args.pi_dir.joinpath(*path.parts[1:])
            if (
                target.is_symlink()
                or not target.is_file()
                or target.stat().st_size != member.size
                or any(p.is_symlink() for p in target.parents if p.is_relative_to(args.pi_dir))
            ):
                raise ValueError("Pi installed file mismatch")
            h = hashlib.sha256()
            with archive.extractfile(member) as fh:
                for block in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(block)
            if digest(target) != h.hexdigest():
                raise ValueError("Pi installed bytes differ from pinned artifact")
            count += 1
    if not count:
        raise ValueError("empty Pi package")
    ok, node_version = command([str(args.node), "--version"])
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", node_version)
    if not ok or not match or tuple(map(int, match.groups())) < (22, 19, 0):
        raise ValueError("unsupported Node version")
    # Version only; no Pi startup/model/tool invocation or provider environment.
    with tempfile.TemporaryDirectory(prefix="pi-preflight-version-") as agent:
        ok, version = command(
            [str(args.node), str(args.pi_dir / "dist/bundle/cli.js"), "--version"],
            extra_env={"PI_CODING_AGENT_DIR": agent},
        )
    report.add(
        "pi_artifact",
        "PASS" if ok and version.strip() == "1.0.0" else "FAIL",
        "Node trusted hash and top-level installed Pi files match pinned archive; CLI version only",
        "Resolve Node/Pi versions and separately freeze transitive dependencies",
        files_verified=count,
        node_version=node_version.strip(),
    )


def registry_readiness(directory: Path, registry: str) -> tuple[bool, str]:
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9.:-]*/[a-z0-9._/-]+", registry)
        or ".." in registry
        or "//" in registry
    ):
        raise ValueError(
            "expected host/namespace/repository without credentials, URL, tag, or digest"
        )
    host = registry.split("/", 1)[0]
    data = load_json(directory / "config.json")
    # Deliberately inspect only presence/type. Never return values, auth strings,
    # identities, helper names, or exception text from the credential file.
    auths = data.get("auths", {})
    helper = data.get("credHelpers", {})
    configured = False
    for key in (host, "https://" + host, "https://" + host + "/v1/"):
        record = auths.get(key, {})
        configured = configured or bool(record.get("auth") or record.get("identitytoken"))
        helper_name = helper.get(key) or data.get("credsStore")
        if helper_name:
            configured = configured or bool(shutil.which("docker-credential-" + helper_name))
    return (
        configured,
        "Local credential configuration present; push scope/access not tested"
        if configured
        else "No local credential configuration found for destination",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("smoke", "target"), default="target")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model-manifest", type=Path)
    parser.add_argument(
        "--hash-model",
        action="store_true",
        help="stream all trusted manifest file hashes; may take minutes",
    )
    parser.add_argument("--render-device", default="/dev/dri/renderD128")
    parser.add_argument("--disk-path", type=Path, default=Path.cwd())
    parser.add_argument("--min-free-gib", type=float, default=180)
    parser.add_argument("--node", type=Path)
    parser.add_argument("--node-sha256")
    parser.add_argument("--pi-dir", type=Path)
    parser.add_argument("--pi-tarball", type=Path)
    parser.add_argument(
        "--registry", help="OCI destination host/namespace/repository, no credential or URL"
    )
    parser.add_argument("--docker-config", type=Path, default=Path.home() / ".docker")
    args = parser.parse_args(argv)
    args.model_manifest = (
        args.model_manifest
        or ROOT / "tasks/harness-design/harness/model-pins" / f"{args.model}.json"
    )
    if args.min_free_gib <= 0 or not args.min_free_gib < float("inf"):
        parser.error("--min-free-gib must be finite and positive")
    report = Report()
    lock = load_json(ROOT / "baseline/lock.json")
    profiles = load_json(ROOT / "agent-harness/profiles.json")
    compatible = platform.system() == "Linux" and platform.machine() in {
        "x86_64",
        "amd64",
    }
    report.add(
        "platform",
        "PASS" if compatible else "FAIL",
        "Requires Linux/amd64",
        "Run on the assigned Linux MI355X host",
    )
    if compatible:
        report.add(
            "python",
            "PASS" if sys.version_info >= (3, 11) else "FAIL",
            "Host inspection and harness require Python 3.11+",
            "Use Python 3.11 or later",
            version=platform.python_version(),
        )
        for tool in ("uv", "git", "patch"):
            ok, _ = command([tool, "--version"])
            report.add(
                tool,
                "PASS" if ok else "MISSING",
                "Required host executable inspected",
                f"Make {tool} available before reproducing the harness",
            )
        report.guarded(
            "gpu",
            "Inspect assigned device permissions/sysfs/SMI output",
            lambda: check_gpu(report, args.render_device),
        )
        report.guarded(
            "capacity",
            "Inspect CPU/memory/storage permissions",
            lambda: check_capacity(report, args.disk_path, args.min_free_gib),
        )
        report.guarded(
            "docker",
            "Inspect local Docker daemon access/configuration",
            lambda: check_docker(report, lock),
        )
    if args.model_dir is None:
        report.add(
            "model",
            "MISSING",
            "No model directory supplied",
            "Prepare the pinned snapshot as real files, then supply --model-dir",
        )
    else:

        def model_check() -> None:
            evidence = model_inventory(
                args.model_dir, lock["models"][args.model], args.model_manifest, args.hash_model
            )
            report.add(
                "model",
                "PASS" if evidence["verified_hashes"] else "MISSING",
                "Snapshot structure checked; revision marker alone is not integrity proof",
                "Supply a trusted pinned file manifest and --hash-model for full verification",
                **evidence,
            )

        report.guarded(
            "model",
            "Replace incomplete/mismatched files from the pinned snapshot; do not mix revisions",
            model_check,
        )
    report.guarded(
        "pi_artifact",
        "Use independently verified Node and the protected Pi package artifact",
        lambda: check_pi(report, args, profiles),
    )
    if args.registry:

        def registry_check() -> None:
            configured, detail = registry_readiness(args.docker_config, args.registry)
            report.add(
                "registry",
                "PASS" if configured else "MISSING",
                detail,
                "Configure registry auth separately; verify push permission during publication",
            )

        report.guarded(
            "registry",
            "Supply a valid registry destination and inspect local config securely",
            registry_check,
        )
    else:
        report.add(
            "registry",
            "MISSING",
            "No final image destination supplied",
            "Choose an organizer-accessible OCI repository and supply --registry",
        )
    result = report.result()
    result["protected_input_sha256"] = {
        "baseline_lock": digest(ROOT / "baseline/lock.json"),
        "agent_profiles": digest(ROOT / "agent-harness/profiles.json"),
        "model_manifest": digest(args.model_manifest) if args.model_manifest.is_file() else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1
