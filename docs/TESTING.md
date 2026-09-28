# Testing

## Run everything

```bash
tests/run_tests.sh
```

This runs the Python agent suite (`unittest`) and the Node extension logic
suite. Both are dependency-free (stdlib Python 3, plain Node). All fixtures are
synthetic; no production Telegram is ever contacted (a fake sender is used).

## Coverage map (spec §20 + Telegram §)

**Unit** — `test_model.py`
- event validation, evidence classification (no promotion)
- sensitive-field rejection: password input, explicit flag, field name,
  JWT-like, card-like, API-token prefix
- unsent draft rejected; empty submitted content rejected
- truncation marked; control chars stripped

**DB / retention** — `test_db.py`
- schema version + idempotent migration
- DB not world-readable
- session open/close idempotent; outbox idempotent on session
- delivery-state transitions; retention purge

**Extension** — `tests/extension/run_extension_tests.js`
- Google submitted query extracted; non-search page yields nothing
- ChatGPT submitted prompt captured; Shift+Enter / typing / empty / IME NOT
- password / sensitive field not captured; secret-looking content dropped
- duplicate submission suppressed within window; truncation marked

**Agent (ingestion)** — `test_ingest.py`
- valid event accepted (202); rejected event (422)
- oversized payload (413); bad JSON (400); wrong path (404)
- token enforcement; refusal to bind a non-loopback host

**Sessions** — `test_sessions.py`
- only monitored graphical user sessions; non-monitored ignored
- stable session id; loginctl failure -> empty (fail open)

**Session pipeline** — `test_daemon_pipeline.py`
- full session -> one report; event without session rejected
- forged username overridden; draft never stored
- idempotent (no duplicate report); Chrome close is not session end
- Telegram retry-then-success; pending report survives restart
- shutdown with active session still produces a report

**Aggregation / report** — `test_aggregate_report.py`
- report wording per evidence level; never "membuka youtube"; truncation marker

**Failure modes / Squid** — `test_squid_and_failure.py`
- Squid window + blocked classification; missing file empty
- missing DB dir created; malformed config -> defaults
- loginctl unavailable doesn't crash; ingest never raises on garbage

## Result

67 tests total (55 agent + 12 extension), all passing.

## Live acceptance (on-device)

See [DEPLOYMENT.md](DEPLOYMENT.md#live-acceptance). Use a synthetic test child
session; never use a real child's private conversation as a fixture.
