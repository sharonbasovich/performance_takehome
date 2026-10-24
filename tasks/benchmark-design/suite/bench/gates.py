"""Per-request evidence gates and token-time reconstruction.

Every request is re-derived from its verbatim SSE payloads with the shared strict parser;
the runner's convenience fields (``text``, ``finish_reason``, ``client_tokens``) are only
cross-checked. A request ends up in exactly one population category:

* ``completed``        passed every gate; the only category that feeds latency metrics;
* ``failed``           the server answered but wrongly (HTTP error, invalid text, false
                       usage, protocol error, empty output): scored as a failure (FI = 0);
* ``unfinished``       the stream never reached a verified end ([DONE] + finish_reason):
                       drops, timeouts, missing completion markers;
* ``evidence_invalid`` the *measurement* cannot be trusted (timing not monotonic, record
                       inconsistent with its own payloads, client send lag, schema error).
                       Any such request makes the whole run ``invalid``.
"""

from dataclasses import dataclass, field
from typing import Any

from bench.prompts import check_expected
from bench.tokens import count_tokens, tokenize
from benchmarks.streaming import StreamProtocolError, decode_payload, generated_deltas

FAILED_REASONS = frozenset(
    {
        "http_error",
        "protocol_error",
        "invalid_output",
        "usage_discrepancy",
        "empty_output",
        "unexpected_finish_reason",
    }
)
UNFINISHED_REASONS = frozenset(
    {"missing_done", "missing_finish_reason", "drop", "timeout", "transport_error"}
)
EVIDENCE_REASONS = frozenset(
    {"invalid_timing", "record_mismatch", "client_send_lag", "schema_error", "missing_timestamp"}
)


@dataclass
class Verdict:
    """Gate outcome for one request plus the reconstructed token timeline."""

    request_id: str
    category: str
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    ttft_s: float | None = None
    first_byte_s: float | None = None
    token_times_s: list[float] = field(default_factory=list)
    content_tokens: int = 0
    reasoning_tokens: int = 0
    content_events: int = 0
    usage_completion_tokens: int | None = None
    prompt_tokens: int = 0
    done_received: bool = False
    finish_reason: str | None = None


def _reparse(
    events: list[dict[str, Any]],
) -> tuple[list[tuple[str, str, float]], bool, str | None, dict[str, Any] | None, str | None]:
    """Re-derive (channel, text, t) deltas, [DONE], finish_reason, usage, protocol error."""
    deltas: list[tuple[str, str, float]] = []
    done = False
    finish: str | None = None
    usage: dict[str, Any] | None = None
    for event in events:
        try:
            decoded = decode_payload(str(event["raw"]))
        except StreamProtocolError as exc:
            return deltas, done, finish, usage, f"protocol_error:{exc}"
        if decoded is None:
            done = True
            continue
        if done:
            return deltas, done, finish, usage, "protocol_error:data after [DONE]"
        if isinstance(decoded.get("usage"), dict):
            usage = decoded["usage"]
        try:
            for channel, text in generated_deltas(decoded):
                deltas.append((channel, text, float(event["t"])))
        except StreamProtocolError as exc:
            return deltas, done, finish, usage, f"protocol_error:{exc}"
        choices = decoded.get("choices") or []
        if choices and isinstance(choices[0], dict) and choices[0].get("finish_reason"):
            finish = str(choices[0]["finish_reason"])
    return deltas, done, finish, usage, None


def token_times(deltas: list[tuple[str, float]], send_s: float) -> tuple[list[float], int]:
    """Request-relative arrival time of each content token (delta resolution).

    The full text is tokenized once so tokens that straddle delta boundaries are counted
    once; each token takes the arrival time of the delta holding its last character.
    """
    text = "".join(t for t, _ in deltas)
    if not text:
        return [], 0
    bounds: list[tuple[int, float]] = []
    offset = 0
    for piece, t in deltas:
        offset += len(piece)
        bounds.append((offset, t))
    times: list[float] = []
    pos = 0
    cursor = 0
    for token in tokenize(text):
        pos += len(token)
        while cursor < len(bounds) - 1 and bounds[cursor][0] < pos:
            cursor += 1
        times.append(bounds[cursor][1] - send_s)
    return times, len(times)


def _timing_errors(ts: dict[str, Any], events: list[dict[str, Any]], http_ok: bool) -> list[str]:
    errors: list[str] = []
    for key in ("send", "end"):
        if not isinstance(ts.get(key), int | float):
            errors.append(f"missing_timestamp:{key}")
    if errors:
        return errors
    order = [("send", ts["send"])]
    for key in ("headers", "first_byte"):
        value = ts.get(key)
        if value is None:
            if http_ok and events:
                errors.append(f"missing_timestamp:{key}")
        elif isinstance(value, int | float):
            order.append((key, value))
        else:
            errors.append(f"missing_timestamp:{key}")
    for index, event in enumerate(events):
        if not isinstance(event.get("t"), int | float):
            errors.append(f"missing_timestamp:event[{index}]")
            return errors
        order.append((f"event[{index}]", event["t"]))
    order.append(("end", ts["end"]))
    for (a_name, a), (b_name, b) in zip(order, order[1:], strict=False):
        if b < a:
            errors.append(f"invalid_timing:{b_name}<{a_name}")
            break
    planned = ts.get("planned_send")
    if isinstance(planned, int | float) and ts["send"] < planned - 1e-6:
        errors.append("invalid_timing:send<planned_send")
    return errors


def judge(record: dict[str, Any], plan: dict[str, Any], schema_errors: list[str]) -> Verdict:
    """Apply every gate to one request record."""
    verdict = Verdict(str(record.get("request_id", "?")), "completed")
    reasons = verdict.reasons
    if schema_errors:
        reasons.extend(f"schema_error:{e}" for e in schema_errors[:3])
    ts = record.get("timestamps_mono_s") or {}
    events = record.get("events") or []
    status = record.get("http_status")
    http_ok = status == 200
    timing = _timing_errors(ts, events, http_ok)
    reasons.extend(timing)
    send = ts.get("send") if isinstance(ts.get("send"), int | float) else None
    planned = ts.get("planned_send")
    max_send_lag = plan["client_integrity"]["max_send_lag_s"]
    if send is not None and isinstance(planned, int | float) and send - planned > max_send_lag:
        reasons.append(f"client_send_lag:{send - planned:.3f}s")
    error = record.get("error")
    if status is None and error is None:
        reasons.append("missing_timestamp:http_status")
    elif status is not None and not http_ok:
        reasons.append(f"http_error:{status}")
    if isinstance(error, dict):
        kind = str(error.get("kind"))
        if kind in ("drop", "timeout"):
            reasons.append(kind)
        elif kind == "transport":
            reasons.append("transport_error")
        elif kind == "protocol":
            reasons.append(f"protocol_error:{error.get('message')}")
        elif kind != "http_error":
            reasons.append(f"transport_error:{kind}")
    deltas, done, finish, usage, proto = _reparse(events)
    if proto:
        reasons.append(proto)
    verdict.done_received = done
    verdict.finish_reason = finish
    content = [(t, at) for ch, t, at in deltas if ch == "content"]
    reasoning_text = "".join(t for ch, t, _ in deltas if ch == "reasoning_content")
    content_text = "".join(t for t, _ in content)
    recorded = record.get("text") or {}
    if (
        recorded.get("content", content_text) != content_text
        or record.get("done_received", done) != done
    ):
        reasons.append("record_mismatch:text or [DONE] differs from verbatim payloads")
    verdict.content_events = sum(1 for t, _ in content if t)
    verdict.reasoning_tokens = count_tokens(reasoning_text)
    verdict.prompt_tokens = int((record.get("prompt") or {}).get("approx_prompt_tokens") or 0)
    if send is not None:
        if isinstance(ts.get("first_byte"), int | float):
            verdict.first_byte_s = ts["first_byte"] - send
        verdict.token_times_s, verdict.content_tokens = token_times(content, send)
        first_text = next((at for t, at in content if t), None)
        if first_text is not None:
            verdict.ttft_s = first_text - send
    if http_ok and not error:
        if not done:
            reasons.append("missing_done")
        if finish is None:
            reasons.append("missing_finish_reason")
        expected = (record.get("prompt") or {}).get("expected") or {}
        allowed = expected.get("finish_reasons") or []
        if finish is not None and allowed and finish not in allowed:
            reasons.append(f"unexpected_finish_reason:{finish}")
        if not content_text:
            reasons.append("empty_output")
        reasons.extend(f"invalid_output:{f}" for f in check_expected(content_text, expected))
        if usage and isinstance(usage.get("completion_tokens"), int):
            verdict.usage_completion_tokens = usage["completion_tokens"]
            independent = verdict.content_tokens + verdict.reasoning_tokens
            lo, hi = plan["token_accounting"]["usage_ratio_band"]
            ratio = usage["completion_tokens"] / independent if independent else None
            if ratio is None or not lo <= ratio <= hi:
                reasons.append(
                    f"usage_discrepancy:usage={usage['completion_tokens']} "
                    f"independent={independent}"
                )
        elif usage is None and plan["output_policy"]["stream_options"].get("include_usage"):
            verdict.flags.append("usage_not_reported")
        if verdict.content_tokens and verdict.content_events:
            if verdict.content_tokens / verdict.content_events > 1.5:
                verdict.flags.append("multi_token_deltas")
    keys = {r.split(":", 1)[0] for r in reasons}
    if keys & EVIDENCE_REASONS:
        verdict.category = "evidence_invalid"
    elif keys & UNFINISHED_REASONS:
        verdict.category = "unfinished"
    elif keys & FAILED_REASONS:
        verdict.category = "failed"
    return verdict
