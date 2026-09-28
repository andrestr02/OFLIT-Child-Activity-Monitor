"""OFLIT Child Activity Monitor — local agent package.

A privacy-bounded activity monitor for OFLIT child devices. This package
provides the local agent: event ingestion, validation, persistence, session
correlation, reporting, and delivery over the existing OFL IT Lab Monitoring
Telegram transport.

Design invariants (enforced across the package, not just documented):

* This is NOT a keylogger. Only *submitted* content is ever recorded, and
  only from explicitly supported sites. See ``model.py``.
* Sensitive fields (passwords, tokens, cookies, payment data) are rejected
  at ingestion and never persisted. See ``model.reject_sensitive``.
* The agent never trusts the ``username`` claimed by the browser extension;
  it binds every event to the owner of the active graphical child session.
* Monitoring failure must FAIL OPEN with respect to child computer use: the
  agent is never a dependency for login, and never blocks logout.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = 1
