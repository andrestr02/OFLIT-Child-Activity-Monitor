# Changelog

All notable changes to OFLIT Child Activity Monitor will be documented here.
This project adheres to a simple semantic-ish versioning scheme.

## [0.1.0] — 2026-09-28 (candidate)

First working end-to-end release candidate. NOT yet pushed/tagged remotely
(owner performs release).

### Added
- Local agent (stdlib-only Python 3): loopback event ingestion
  (`127.0.0.1:8791`), input validation, sensitive-field rejection,
  SQLite persistence with schema versioning + migrations, session correlation
  via systemd-logind, best-effort application observation, optional coarse
  Squid network observation, session aggregation, and a durable report outbox.
- Chrome MV3 managed extension with minimal permissions and per-site adapters
  for Google Search (submitted queries) and ChatGPT (submitted prompts).
  Captures submitted content only; never keystrokes, drafts, passwords, tokens,
  or cookies.
- Final per-session Telegram report over the **existing** OFL IT Lab Monitoring
  transport (no new bot/token), with idempotent one-session-one-report
  delivery and durable retry.
- `child-activity` CLI (status / report / sessions / outbox / flush / purge).
- Hardened systemd unit, idempotent installer/uninstaller, Chrome managed-policy
  template, and full documentation set.
- Test suite: 55 agent unit/integration tests + 12 extension logic tests.

### Privacy / safety
- Evidence-level model (direct user action / visited resource / network
  observation / process running) with honest report wording.
- Conservative default retention (14 days), owner-tunable.
- Fail-open: monitoring failure never blocks child login or logout.
