"""Thin, timeout-bounded wrapper around the Docker CLI (buildx build, run, inspect, kill)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import procs

DEFAULT_PLATFORM = "linux/amd64"


class DockerError(RuntimeError):
    """A Docker operation failed, timed out, or produced unusable output."""


@dataclass(frozen=True)
class BuildResult:
    """Result of a fresh image build. ``digest`` is the OCI manifest/index digest."""

    tag: str
    ok: bool
    timed_out: bool
    duration_s: float
    image_id: str | None
    digest: str | None
    log_path: Path
    error: str | None = None


def docker_available() -> bool:
    """True when a ``docker`` binary is on PATH and the daemon answers."""
    if shutil.which("docker") is None:
        return False
    return procs.run(["docker", "version", "--format", "{{.Server.Version}}"], timeout_s=20).ok


def _docker(args: Sequence[str], timeout_s: float, **kw: Any) -> procs.RunResult:
    return procs.run(["docker", *args], timeout_s=timeout_s, **kw)


def build_image(
    context_dir: Path,
    tag: str,
    *,
    log_path: Path,
    timeout_s: float,
    platform: str = DEFAULT_PLATFORM,
    dockerfile: Path | None = None,
    build_args: Mapping[str, str] | None = None,
    network: str = "default",
    no_cache: bool = False,
) -> BuildResult:
    """Build ``context_dir`` into a fresh local image and resolve its digest.

    Uses ``docker buildx build --load --metadata-file`` so the OCI digest is
    available without pushing to a registry. ``--no-cache`` is off by default:
    layer caching only reuses byte-identical steps, so a patched
    Dockerfile still produces a genuinely new image, and digests are resolved
    from the result, never guessed.
    """
    metadata = log_path.with_suffix(".meta.json")
    args = [
        "buildx",
        "build",
        "--platform",
        platform,
        "--load",
        "--progress",
        "plain",
        "--network",
        network,
        "--metadata-file",
        str(metadata),
        "-t",
        tag,
    ]
    if no_cache:
        args.append("--no-cache")
    if dockerfile is not None:
        args += ["-f", str(dockerfile)]
    for key, value in (build_args or {}).items():
        args += ["--build-arg", f"{key}={value}"]
    args.append(str(context_dir))
    result = _docker(args, timeout_s, log_path=log_path)
    if result.timed_out:
        return BuildResult(
            tag, False, True, result.duration_s, None, None, log_path, "build timed out"
        )
    if not result.ok:
        tail = "\n".join(result.stdout.splitlines()[-15:])
        return BuildResult(
            tag,
            False,
            False,
            result.duration_s,
            None,
            None,
            log_path,
            f"build failed (rc={result.returncode}): {tail}",
        )
    digest = None
    if metadata.exists():
        try:
            digest = json.loads(metadata.read_text(encoding="utf-8")).get("containerimage.digest")
        except json.JSONDecodeError:
            digest = None
    if digest is None:
        digest = resolve_digest(tag)
    image_id = image_config(tag).get("Id")
    if not digest:
        return BuildResult(
            tag,
            False,
            False,
            result.duration_s,
            image_id,
            None,
            log_path,
            "image built but no digest could be resolved",
        )
    return BuildResult(tag, True, False, result.duration_s, image_id, digest, log_path)


def image_config(image: str) -> dict[str, Any]:
    """Return ``docker image inspect`` for ``image`` (flattened to the first entry)."""
    result = _docker(["image", "inspect", image], timeout_s=60)
    if not result.ok:
        raise DockerError(f"image inspect failed for {image}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if not data:
        raise DockerError(f"image inspect returned nothing for {image}")
    return data[0]


def image_exists(image: str) -> bool:
    """True when ``image`` is present locally."""
    return _docker(["image", "inspect", image], timeout_s=60).ok


def image_cmd(image: str) -> list[str]:
    """The image's default ``CMD`` (the tunable runtime-flag surface)."""
    return list(image_config(image).get("Config", {}).get("Cmd") or [])


def image_entrypoint(image: str) -> list[str]:
    """The image's ``ENTRYPOINT``."""
    return list(image_config(image).get("Config", {}).get("Entrypoint") or [])


def resolve_digest(image: str) -> str | None:
    """Resolve the ``sha256:`` repo digest of a local image, if Docker recorded one."""
    try:
        repo_digests = image_config(image).get("RepoDigests") or []
    except DockerError:
        return None
    for ref in repo_digests:
        if "@sha256:" in ref:
            return ref.split("@", 1)[1]
    return None


def retag(source: str, target: str) -> None:
    """``docker tag source target`` (used to pin the last-good image)."""
    result = _docker(["tag", source, target], timeout_s=60)
    if not result.ok:
        raise DockerError(f"docker tag {source} {target} failed: {result.stderr.strip()}")


def remove_image(image: str) -> None:
    """Best-effort ``docker rmi`` (never raises)."""
    _docker(["rmi", "-f", image], timeout_s=120)


def ensure_internal_network(name: str) -> str:
    """Create (if needed) a bridge network with ``--internal`` so containers have no egress.

    The host can still reach the container's address on that network, which is
    how the harness measures the server.
    """
    if _docker(["network", "inspect", name], timeout_s=30).ok:
        return name
    result = _docker(["network", "create", "--internal", name], timeout_s=60)
    if not result.ok and not _docker(["network", "inspect", name], timeout_s=30).ok:
        raise DockerError(f"network create {name} failed: {result.stderr.strip()}")
    return name


def remove_network(name: str) -> None:
    """Best-effort network removal."""
    _docker(["network", "rm", name], timeout_s=60)


def run_detached(command: Sequence[str], *, timeout_s: float = 120) -> str:
    """Run a prepared ``docker run --detach ...`` command; return the container id."""
    result = procs.run(command, timeout_s=timeout_s)
    if not result.ok:
        raise DockerError(f"docker run failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def container_state(name: str) -> dict[str, Any] | None:
    """``State`` block of ``docker inspect`` or ``None`` when the container is gone."""
    result = _docker(["inspect", name], timeout_s=60)
    if not result.ok:
        return None
    data = json.loads(result.stdout)
    return data[0].get("State") if data else None


def container_running(name: str) -> bool:
    """True when the container exists and is running."""
    state = container_state(name)
    return bool(state and state.get("Running"))


def container_ip(name: str, network: str) -> str | None:
    """IP address of ``name`` on ``network`` (None if not attached yet)."""
    result = _docker(["inspect", name], timeout_s=60)
    if not result.ok:
        return None
    data = json.loads(result.stdout)
    if not data:
        return None
    networks = data[0].get("NetworkSettings", {}).get("Networks", {})
    entry = networks.get(network)
    return entry.get("IPAddress") or None if entry else None


def container_logs(name: str, tail: int = 200) -> str:
    """Last ``tail`` lines of the container's combined logs."""
    result = _docker(["logs", "--tail", str(tail), name], timeout_s=60)
    return (result.stdout or "") + (result.stderr or "")


def stop_container(name: str, *, grace_s: int = 10) -> None:
    """Graceful SIGTERM via ``docker stop`` then force removal. Never raises."""
    _docker(["stop", "-t", str(grace_s), name], timeout_s=grace_s + 30)
    _docker(["rm", "-f", name], timeout_s=60)


def kill_containers_with_prefix(prefix: str) -> list[str]:
    """Force-remove every container whose name starts with ``prefix``; returns names removed."""
    result = _docker(["ps", "-a", "--format", "{{.Names}}"], timeout_s=60)
    names = [n for n in result.stdout.split() if n.startswith(prefix)]
    for name in names:
        _docker(["rm", "-f", name], timeout_s=60)
    return names
