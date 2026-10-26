# Exact measured LLMD baseline image

This directory preserves the exact metadata and tar structure of a real, verified LLMD image export. The selected image was freshly revalidated on one MI355X using Qwen3.6-27B: all 30 requests matched the complete baseline and passed usage/finish gates. It is a baseline, with no optimization gain claimed. The genuine Pi attempt failed at an upstream response deadline before producing a patch; that remains an unfinished optimization result.

The complete original archive is **5,923,200,000 bytes**, SHA-256 `c759f7c2a7dd3b6a1deb083c0df46c435c0165e237f50d6b7e52097031497b47`. Its selected platform manifest is `sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`; its Docker image-index identity is `sha256:ccd73fc2f663734f222070502bca7928d62cfad1cee733170357e1c3dd957540`. These identify different objects and are intentionally distinguished.

All 23 filesystem blobs are inherited unchanged from the public pinned base `docker.io/zmlai/llmd@sha256:0a2cd01a2e53c78934a8cfef66f8668da7666be4954a5d18b72df089c54ea34f`. Only image configuration and build metadata differ. Model weights are outside the image. Upstream engine/source/license provenance is inherited; this does not label the entire image Apache-2.0 or claim a bit-reproducible Docker rebuild.

`segments/` preserves every other archive byte, including original headers, metadata, padding and suffix. `reconstruction-manifest.json` specifies the complete ordered byte coverage. Its SHA-256 is `da39f7f6ec2fec5bb6ef4c42ed34b62867d69f01bfece904e5ac62e531776b5c`. Fetch each public layer from `docker.io/zmlai/llmd` by the exact digest in the manifest, storing it under its 64-character SHA in a local blob directory, without unpacking it. The offline utility then verifies every input, joins exact bytes and checks the complete original archive hash:

```sh
python reconstruct_exact_archive.py --execute-reviewed \
  --metadata-dir /absolute/path/to/this-directory \
  --blob-dir /absolute/path/to/verified-public-blobs \
  --output /absolute/path/to/llmd-baseline.docker.tar \
  --manifest-sha256 da39f7f6ec2fec5bb6ef4c42ed34b62867d69f01bfece904e5ac62e531776b5c
```

The utility performs no network access, Docker operation or rebuild. It refuses overwrite and only publishes a complete output after its exact original hash matches. `original-receipt.json` records the actual export's full layer/decompression verification; the metadata audit alone did not read all layer bytes. Raw configuration was reviewed: its environment is exactly inherited from the public base, with no user/provider credentials added.

Public release-asset delivery and anonymous verification are pending at this commit. A future release may split the exact archive into files below GitHub's per-file limit; GitHub documents a 2GiB limit per release asset. [GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). Registry publication and anonymous pull remain separate checks; neither is claimed here.
