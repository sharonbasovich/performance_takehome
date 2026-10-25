"""Exercise pinned Pi's real CLI/tools/events against deterministic HTTP fixtures.

No local or cloud inference, provider credentials, GPU, or Docker execution.
Linux/Python 3.11+. Supply an independently verified Pi 1.0.0 install and Node >=22.19:
python pi_protocol_smoke.py --node /path/to/node --pi-cli /path/to/pi/dist/bundle/cli.js
The --out directory must be new; otherwise a temporary directory is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from abstract_harness.proposers import PiLaunchConfig, PiProposer, ProposerContext  # noqa: E402

REQUESTS = []


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 2 * 1024 * 1024 or len(REQUESTS) >= 4:
            self.send_error(413, "protocol fixture request bound exceeded")
            return
        body = json.loads(self.rfile.read(length))
        REQUESTS.append({"path": self.path, "body": body})
        has_tool_result = any(m.get("role") == "tool" for m in body["messages"])
        if has_tool_result:
            delta = {"role": "assistant", "content": "Protocol fixture finished."}
            finish = "stop"
        else:
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_fixture_write",
                        "type": "function",
                        "function": {
                            "name": "write",
                            "arguments": json.dumps(
                                {
                                    "path": "Dockerfile",
                                    "content": "FROM scratch\nLABEL fixture=after\n",
                                }
                            ),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for patch in (
            {"delta": delta, "finish_reason": None},
            {"delta": {}, "finish_reason": finish},
        ):
            event = {
                "id": "fixture",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "protocol-fixture",
                "choices": [{"index": 0, **patch}],
            }
            self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
        self.wfile.write(
            (
                "data: "
                + json.dumps(
                    {
                        "id": "fixture",
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": "protocol-fixture",
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                        },
                    }
                )
                + "\n\n"
            ).encode()
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class ActualCliProposer(PiProposer):
    def __init__(self, node, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.node = node

    def build_command(self, prompt_path, session_dir):
        # Launch the supplied Node explicitly; retain all production Pi arguments.
        return [
            str(self.node),
            str(self.config.pi_bin),
            "--offline",
            *super().build_command(prompt_path, session_dir)[1:],
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--pi-cli", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    node, cli = args.node.resolve(strict=True), args.pi_cli.resolve(strict=True)
    work = args.out.resolve() if args.out else Path(tempfile.mkdtemp(prefix="pi-protocol-"))
    if args.out:
        work.mkdir(parents=True, exist_ok=False)
    agent = work / "agent"
    agent.mkdir()
    context_dir = work / "original"
    context_dir.mkdir()
    (context_dir / "Dockerfile").write_text(
        "FROM scratch\nLABEL fixture=before\n", encoding="utf-8"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        models = {
            "providers": {
                "abstract-protocol-fixture": {
                    "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
                    "api": "openai-completions",
                    "apiKey": "non-secret-protocol-fixture",
                    "models": [
                        {
                            "id": "protocol-fixture",
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": 100000,
                            "maxTokens": 1000,
                            "cost": {"input": 2, "output": 8, "cacheRead": 0, "cacheWrite": 0},
                        }
                    ],
                }
            }
        }
        (agent / "models.json").write_text(json.dumps(models), encoding="utf-8")
        os.environ["ABSTRACT_PROTOCOL_FIXTURE_KEY"] = "non-secret-protocol-fixture"
        proposer = ActualCliProposer(
            node,
            PiLaunchConfig(
                pi_bin=cli,
                agent_dir=agent,
                api_key_env="ABSTRACT_PROTOCOL_FIXTURE_KEY",
                model="protocol-fixture",
                provider="abstract-protocol-fixture",
                extra_env={"PI_OFFLINE": "1"},
                timeout_s=45,
            ),
            profile={"stock_tools": ["read", "bash", "edit", "write"]},
        )
        version = subprocess.run(
            [str(node), str(cli), "--version"],
            env=proposer.build_env(),
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.strip()
        if version != "1.0.0":
            raise ValueError(f"Pi must report 1.0.0, got {version!r}")
        node_version = subprocess.run(
            [str(node), "--version"], capture_output=True, text=True, check=True, timeout=15
        ).stdout.strip()
        if tuple(map(int, node_version.lstrip("v").split("."))) < (22, 19, 0):
            raise ValueError("Node >=22.19.0 required")
        context = ProposerContext(
            "Make one change to the label.",
            {},
            [],
            context_dir,
            work,
            "llmd",
            "CPU protocol fixture only",
        )
        proposal = proposer.propose(context)
        if not (
            proposal is not None
            and "-LABEL fixture=before" in proposal.patch
            and "+LABEL fixture=after" in proposal.patch
        ):
            raise RuntimeError("adapter did not recover the expected scratch change")
        if len(REQUESTS) != 2:
            raise RuntimeError(f"expected two fixture requests, got {len(REQUESTS)}")
        if (context_dir / "Dockerfile").read_text() != "FROM scratch\nLABEL fixture=before\n":
            raise RuntimeError("original context was changed")
        transcript = Path(proposal.transcript_path)
        events = [
            json.loads(line)
            for line in transcript.read_text(encoding="utf-8").splitlines()
            if line.startswith("{")
        ]
        tools = {t["function"]["name"] for t in REQUESTS[0]["body"]["tools"]}
        if tools != {"read", "bash", "edit", "write"}:
            raise RuntimeError(f"unexpected stock tools: {tools}")
        if proposal.api_usd is None or abs(proposal.api_usd - 0.00072) >= 1e-9:
            raise RuntimeError(f"unexpected fixture usage arithmetic: {proposal.api_usd}")
        writes = [
            e
            for e in events
            if e.get("type") == "tool_execution_end" and e.get("toolName") == "write"
        ]
        if len(writes) != 1 or writes[0].get("isError") is not False:
            raise RuntimeError("Pi did not report one successful real write tool call")
        result = {
            "status": "PASS",
            "kind": "deterministic HTTP protocol fixture, no inference",
            "pi_version": version,
            "node_version": node_version,
            "http_requests": len(REQUESTS),
            "stock_tools": sorted(tools),
            "event_types": sorted({e["type"] for e in events}),
            "fixture_usage_cost_usd": proposal.api_usd,
            "actual_provider_spend_usd": 0,
            "source_context_unchanged": True,
            "patch": proposal.patch,
            "transcript": str(transcript),
            "transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
        }
        (work / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
