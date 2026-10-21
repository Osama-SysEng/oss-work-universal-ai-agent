# Logging — OS_V1

Two logs, with different jobs. Confusing them is how a system ends up with
either no accountability or no signal.

| | The operational log | The audit log |
|---|---|---|
| Purpose | signal: what happened, how fast, what failed | accountability: who did what, and can it be trusted |
| Format | one JSON object per line | one JSON object per line, chained by hash |
| Reader | a human, a dashboard, a log shipper | a reviewer, and the chain verifier |
| Location | stdout, and the collector when one exists | `data-osv1/audit.log` |
| Integrity | none beyond the collector | hash-chained: an edit or a removal is detected |

## The operational log

`osv1/obs_logging.py` writes one JSON object per line:

```json
{"timestamp":"2026-10-21T11:40:00.123+00:00","level":"info","service":"oss-work",
 "env":"development","version":"1.0.0","request_id":"a1b2c3d4e5f6a7b8",
 "event":"action.done","message":"action.done","tool":"file.read","outcome":"completed"}
```

- The timestamp is UTC with milliseconds.
- `request_id` comes from the context, and the API middleware accepts an
  inbound `X-Request-ID` or generates one, then returns it.
- The level comes from `LOG_LEVEL`; `info` in production, `debug` locally.
- The extra fields are structured, never a concatenation of user input, so a
  log line cannot be forged by putting a newline in a request.

## Redaction

Keys that commonly hold credentials — `password`, `token`, `secret`,
`api_key`, `authorization`, `cookie`, and the rest — are replaced with a
marker before the line is written. Request bodies are not logged by default.

## The audit log

Every action and every self-evolution step is recorded with the actor, the
target, the outcome, and a hash of the previous entry:

```json
{"timestamp":"...","event":"action.executed","actor":"local","target":"a.txt",
 "outcome":"completed","request_id":"...","details":{...},"prev":"<hash>","hash":"<hash>"}
```

```bash
oss-v1 audit --verify
```

The verifier recomputes the chain and reports the index of the first broken
entry, so a removed or edited line cannot pass unnoticed.

## Central collection

Central aggregation (Loki, Grafana) needs a container runtime and is **not**
part of the core path. When it is available, the operational log is shipped
to it; the audit log stays local, because a remote copy of the audit trail
belongs to the user, not to a collector. No telemetry leaves the machine by
default, and no usage reporting is built in.
