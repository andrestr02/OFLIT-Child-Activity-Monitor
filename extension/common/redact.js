/*
 * redact.js — the extension-side privacy guard.
 *
 * Pure, dependency-free, and unit-tested (see tests/extension). Loaded both in
 * the browser (attaches to window.OFLITRedact) and in Node (module.exports).
 *
 * These functions are the first line of defence that keeps this monitor from
 * becoming a keylogger or credential stealer: sensitive fields and secret-
 * looking text are dropped in the page, before anything is ever sent to the
 * local agent. The agent applies the same checks again (defence in depth).
 */
(function (global) {
  "use strict";

  var SENSITIVE_NAME = /(pass|pwd|secret|token|otp|2fa|cvv|cvc|card|credit|iban|ssn|auth|session|cookie)/i;
  var SENSITIVE_AUTOCOMPLETE = /(current-password|new-password|cc-|one-time-code)/i;

  // Text that looks like a secret => drop the whole capture (never redact-keep).
  var SECRET_PATTERNS = [
    /\b\d{13,19}\b/,                                              // card-like
    /\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b/, // JWT-like
    /\b(sk|pk|ghp|xox[baprs]|AKIA|EAA)[A-Za-z0-9_-]{16,}\b/,      // token prefixes
    /(?:^|\s)password\s*[:=]/i
  ];

  /* Returns true if an input/element must never be captured. */
  function isSensitiveField(el) {
    if (!el) return false;
    var type = (el.type || "").toLowerCase();
    if (type === "password" || type === "hidden") return true;
    var name = (el.name || "") + " " + (el.id || "");
    if (SENSITIVE_NAME.test(name)) return true;
    var ac = (el.autocomplete || el.getAttribute && el.getAttribute("autocomplete") || "");
    if (SENSITIVE_AUTOCOMPLETE.test(ac)) return true;
    return false;
  }

  function looksSecret(text) {
    if (!text) return false;
    for (var i = 0; i < SECRET_PATTERNS.length; i++) {
      if (SECRET_PATTERNS[i].test(text)) return true;
    }
    return false;
  }

  /*
   * sanitize(text, maxChars) -> { content, truncated } or null if it must be
   * dropped (empty or secret-looking).
   */
  function sanitize(text, maxChars) {
    if (text == null) return null;
    var s = String(text);
    // strip control chars except newline/tab, collapse runs of whitespace
    s = s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
    s = s.replace(/[ \t]+/g, " ").trim();
    if (!s) return null;
    if (looksSecret(s)) return null;
    var truncated = false;
    var cap = maxChars || 500;
    if (s.length > cap) {
      s = s.slice(0, cap).replace(/\s+$/, "");
      truncated = true;
    }
    return { content: s, truncated: truncated };
  }

  var api = {
    isSensitiveField: isSensitiveField,
    looksSecret: looksSecret,
    sanitize: sanitize
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.OFLITRedact = api;
})(typeof window !== "undefined" ? window : globalThis);
