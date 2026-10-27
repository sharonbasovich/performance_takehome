# CPU import receipt — exact measured LLMD baseline archive

Sanitized record of the one actual `docker load` of the verified archive, run on 2026-10-26 on a CPU-only cloud VM by the delivery session. The run was independently reviewed from this evidence; it does not establish GPU inference, provider-registry publication or anonymous `docker pull`, all of which remain **UNVERIFIED**. The genuine Pi attempt failed before producing a patch; **no optimization gain** is claimed.

## Environment (observed)

| item | value |
|---|---|
| Docker client / server | 29.7.2 / 29.7.2 |
| storage driver | `overlayfs`, `driver-type=io.containerd.snapshotter.v1` (containerd image store) |
| free disk before / after | 50,920,910,848 B / 50,920,624,128 B (all 23 layers already present from the public base, so the delta is negligible) |
| GPU | none |
| network for the test run | `--network none` |

## Commands and exit statuses (paths abbreviated to `<workdir>`)

```
bash restore_llmd_baseline_v2.sh docker-load --dir <workdir> --output <workdir>/llmd-baseline.docker.tar
  PASS archive <workdir>/llmd-baseline.docker.tar 5923200000 bytes sha256 c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47
  docker load -i <workdir>/llmd-baseline.docker.tar
  Loaded image ID: sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540
  exit 0   (2026-10-26T10:00:40Z .. 10:01:44Z; helper at commit 2faaeb1c, whose docker-load path is unchanged in v2.1)

docker image inspect sha256:ccd73fc2…
  Id=sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540  RepoTags=[]  RepoDigests=[]
  Descriptor={"mediaType":"application/vnd.oci.image.index.v1+json","digest":"sha256:ccd73fc2…","size":856}
  Arch=amd64 OS=linux Entrypoint=["/llmd/llmd"]
  Cmd=["--io-impl=zio","--batch-size=16","--token-batch-size=1024","--max-context-len=128000","--prefill-chunk-size=256","--page-chunk-size=16","--backend=auto","--gpu-memory-fraction=0.9","--cache-memory-fraction=0.95"]
  Env keys only: PATH SSL_CERT_FILE LLMD_POSTHOG_TOKEN LLMD_USAGE_STATS_ENDPOINT  (values inherited from the public base; withheld)
  RootFS layers=23; Cmd/Entrypoint/Env equal pinned config blob 0c06ab37…: true; rootfs diff_ids equal pinned config and public base 0a2cd01a…: true
  platform manifest 7db01160… and config 0c06ab37… are NOT addressable as image IDs in the containerd store (exit 1 "No such image"); not re-derived from the daemon

docker run --rm --network none --entrypoint /llmd/llmd sha256:ccd73fc2… --help
  exit 0; 27 lines; first line "Usage: llmd --model=<path> [options]"
```

## Raw log hashes (private session logs, not committed)

| file | SHA-256 |
|---|---|
| `15_docker_import.log` (full import/inspect transcript) | `f1cd2728151ca438fed7f612a928994f718895fc659dbb0517d6aaa338a66578` |
| `15b_llmd_help.txt` (`--help` output) | `5113b26064748620b0067eab2ab1c381e589b84c99ad6607ff149d20d1377048` |
| `04_reconstruct.log` (reconstruction + independent re-hash) | `3f6f0dc4bef3007a515a53a59cdbf584f61c20dcbadc0faec4a24a33be8ee982` |
| `11_anon_verify.log` (anonymous release re-download) | `f2fce09d7ddda637c32f0be21fc8140e14727e02a7b25b7407c66a840cac7a2e` |
| `docker_import_check.sh` (driver script) | `d5a759ce62b2ff9e38f900edfaa6946fc488e8f7ce03902609625baf6125e132` |
