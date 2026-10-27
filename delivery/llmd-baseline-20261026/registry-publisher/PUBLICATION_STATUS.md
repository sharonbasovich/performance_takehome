# Baseline image publication status

The exact selected linux/amd64 platform is published at:

`ghcr.io/sharonbasovich/performance_takehome-task2-llmd@sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d`

[Publisher run](https://github.com/sharonbasovich/performance_takehome/actions/runs/40596159814)
passed the source-bound approval gate, upload and authenticated manifest/tag
read-back. The [package page](https://github.com/sharonbasovich/performance_takehome/pkgs/container/performance_takehome-task2-llmd)
was observed Public. No visibility change was necessary.

The platform has 23 inherited layers totaling 5,923,157,643 compressed bytes and
config `0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f`.
The original two-child archive index remains provenance; only the selected
platform is published. Use the digest above; the convenience tag is mutable.

Anonymous local verification read and hash-verified the manifest, config and 22
layers, then failed while downloading the largest 5.7 GB layer. That attempt is
incomplete and retained. The subsequent free
[hosted-runner verification](https://github.com/sharonbasovich/performance_takehome/actions/runs/40598808475)
downloaded and hash-verified all 25 objects: manifest, config and all 23 layers,
totaling **5,923,167,710 bytes**, in 194.331 seconds. Its 17,990-byte artifact ZIP
matches GitHub SHA256 `12187d5658d94c42e0239975f565b5ab8857ee2847cbb946f49d28aae4c8389c`.
The raw receipt SHA256 is `7f1e2e706b6da96c18ecb333c33dd608337ca086455199b48662582273ac2e94`.
Every object has its complete byte count/hash, exit code and retained stderr.

An actual separate **Docker 29.7.1** pull with an empty client configuration passed,
followed by exact config/rootfs/repository-digest inspection and CPU `--help` with
network disabled. No login, GPU device or model mount was used. The uniquely owned
test container was confirmed absent. Docker reused the already cached 23 inherited
layers; the independent full-byte download above establishes body access. This is
not a fresh-daemon unpack or GPU inference claim. Its receipt SHA256 is
`496059f4504a2959f4ce80c49979a101ab8687ce958fa18558090f6d212f2da1`.

This remains the measured baseline fallback. No successful genuine Pi patch,
optimization speedup or recovered historical fresh 30-trace report is claimed.
The original public archive and reproducible build instructions remain available
in the parent delivery packet.
