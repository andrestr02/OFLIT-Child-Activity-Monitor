# Privacy

This system is designed around a strict boundary: it records **submitted
content only**, from **two explicitly supported sites**, and nothing else.

## What is recorded

- Google Search queries that were **actually submitted** (read from the
  `/search?q=` results URL).
- ChatGPT prompts that were **actually sent** (explicit Send/Enter gesture).
- Navigation to pages the tab actually loaded (evidence: *visited resource*).
- Applications observed *running* under the child's session (evidence:
  *process running*), from a curated allowlist only.
- Session login/logout times.
- Optionally, coarse Squid network observations (evidence: *network
  observation*), off by default.

## What is NEVER recorded

- Arbitrary keystrokes (there is no keystroke event type anywhere in the code).
- Passwords, credentials, tokens, cookies, session data, payment/card data.
- Unsent drafts — text typed and then deleted or never submitted.
- Clipboard contents, screenshots, screen recordings.
- Browser stored credentials, ChatGPT/session secrets, or decrypted traffic.

## Two-layer sensitive-field defence

1. **In the browser** (`extension/common/redact.js`): password/hidden inputs,
   fields whose name/autocomplete look credential-like, and secret-looking text
   (card-like digit runs, JWT-like strings, API-token prefixes) are dropped
   before anything is sent.
2. **In the agent** (`model.reject_sensitive`): the same checks run again on
   every event. When in doubt, the event is rejected — never redacted-and-kept.

## Evidence honesty

Reports never overstate a signal. A proxy log line is worded "network
observation" / "blocked request observed", browser history as "visited", and
only genuinely submitted content as a "Google Search" / "ChatGPT prompt
submitted". A `network_observation` can never be promoted to a
`direct_user_action` (`model.classify_evidence` enforces this).

## Truncation

Long submitted content is truncated to `MAX_CONTENT_CHARS` (default 500, hard
ceiling 2000) and marked as truncated (`[…]` in reports). Content is otherwise
stored verbatim so the evidence is not silently altered.

## Retention

Stored events are purged after `RETENTION_DAYS` (default **14**). The owner may
change this; there is no unbounded retention by default. Because submitted
prompts can contain personal information, keep retention conservative.

## Data never enters Git

The production database, real logs, `.env` files, and any real child activity
are excluded via `.gitignore`. All test fixtures are synthetic.
