# Portable Pi provider setup

The public `PiProposer` launches stock Pi 1.0.0 with `read,bash,edit,write` and the
assignment's isolation flags. Its `--pi-bin` expects an executable, such as
`node_modules/.bin/pi`, with Node >=22.19.0 on PATH. To select an exact Node binary,
use a small executable wrapper:

```sh
#!/bin/sh
exec /opt/node/bin/node /opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js "$@"
```

The wrapper must also support `--version`. `pi_protocol_smoke.py` tests the actual
pinned CLI and production proposer arguments against a local synthetic server;
it does not establish provider availability, billing or model quality.

Place `models.json` and `settings.json` in `<state-dir>/pi-agent-dir` before launch.
For a custom OpenAI-compatible provider, use its documented Pi 1.0 model schema,
an environment-variable `apiKey` reference, and explicit positive input/output/
cache prices in USD per million tokens. Forward only that named client key with
`--api-key-env`; a gateway's upstream provider secret must stay outside Pi.

In the genuine 28 October external proposal run, the successful continuation set
Pi's `maxTokens: 16384`, the outer gateway configuration to 16384, and
`contextWindow: 65536`. A later source audit found that its inner request validator
still clamped output to 8192; the client/configuration values do not establish a
16384 wire limit. An earlier 4096 outer ceiling ended with `stopReason=length`
before files were written. These were deployment settings; the canonical proposer
does not impose 4096. Verify the actual outgoing cap, leave room for tools and
context, and reserve their full possible cost. A larger output ceiling does not
guarantee a usable answer. The documented provider may have different current limits.

The bounded run used this task-local `settings.json`:

```json
{
  "retry": {"enabled": false, "maxRetries": 0, "provider": {"maxRetries": 0}},
  "compaction": {"enabled": false},
  "cacheWarming": "off"
}
```

`PI_OFFLINE=1` freezes Pi startup package/catalog work while permitting requests to
the configured provider. It does not make model requests free or disable all provider
behavior. An external gateway must enforce a shared aggregate budget across all
model/tool turns and retain complete raw responses, terminal usage and failures.
`--provider-response-dir` records the retention location; the harness does not
verify those external bytes. Export them with the complete attempt tree.

The harness refuses output-limit partial responses before recovering artifacts,
while preserving their known charge. Missing terminal usage, HTTP failures with
unknown billing, timeouts and incomplete responses can leave accounting unresolved;
the harness preserves the known subtotal and stops. A 529 response does not prove
zero billing. Do not retry or clear such a hold without separate reconciliation or
an explicit reviewed policy that continues covering its full liability.

For future canonical LLMD runs, explicitly select
`--development-benchmark tasks/harness-design/harness/development-benchmark.llmd.json` and
`--delivery-policy llmd-config-v1`; the generic CLI benchmark default differs.
Pi edits `tasks/harness-design/Dockerfile` in its scratch context, one knob only,
and writes proposal metadata. It should write files early and keep reasoning
concise. If `proposal.patch` is absent, the controller derives a unified diff from
the actual scratch edits. It then applies the ordinary guard/build/control/
measurement/keep-or-revert process; Pi does not choose the keep decision.

The actual external 28 October runner instead requested `candidate.Dockerfile` and
`proposal.json`. Preserve those raw files and disclose a deterministic diff from
the unchanged baseline Dockerfile to that exact candidate before applying normal
validation. Adding `candidate.Dockerfile` to the canonical scratch tree is not the
same as replacing its Dockerfile. An external raw-file turn must not be described
as an execution of the canonical unattended loop. Historical failed/partial turns,
their source identities and clocks remain part of the evidence.
