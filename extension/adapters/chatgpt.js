/*
 * chatgpt.js — ChatGPT prompt adapter.
 *
 * Capture strategy: record a prompt ONLY on an explicit submission gesture —
 * an Enter keypress without Shift in the composer, or a click on the send
 * control — and only the text present at that instant. Unsent drafts are never
 * captured (no keystroke logging, no periodic scraping). Sensitive fields are
 * dropped via the shared redactor.
 *
 * The submission-decision logic is pure and unit-tested. Because ChatGPT's DOM
 * changes often, the browser binding uses resilient selector fallbacks and a
 * MutationObserver to re-bind; if selectors break, the adapter simply stops
 * capturing (fail-safe) rather than capturing the wrong thing. See
 * docs/SECURITY.md "browser DOM drift".
 */
(function (global) {
  "use strict";

  /*
   * decideSubmission(evt, text) -> boolean
   *   evt: a normalized event descriptor { kind, key, shiftKey, isComposing }
   *        kind is "keydown" or "click".
   *   text: the current composer text.
   * Returns true only when this gesture is a real prompt submission.
   */
  function decideSubmission(evt, text) {
    if (!text || !text.trim()) return false;         // never capture empty/draft
    if (!evt) return false;
    if (evt.kind === "click") return true;           // send-button click
    if (evt.kind === "keydown") {
      if (evt.isComposing) return false;             // IME composition, not send
      return evt.key === "Enter" && !evt.shiftKey;   // Enter (not Shift+Enter)
    }
    return false;
  }

  function buildEvent(text, redact, maxChars) {
    var clean = redact.sanitize(text, maxChars);
    if (!clean) return null;
    return {
      schema_version: 1,
      event_type: "submitted_prompt",
      source: "browser_extension",
      site: "chatgpt.com",
      evidence: "direct_user_action",
      submitted: true,
      content: clean.content,
      truncated: clean.truncated,
      timestamp: new Date().toISOString()
    };
  }

  var api = { decideSubmission: decideSubmission, buildEvent: buildEvent };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.OFLITChatGPT = api;

  // ---- browser binding (skipped in Node tests) ----
  if (typeof document !== "undefined" && global.OFLITClient) {
    var maxChars = global.OFLIT_MAX_CHARS || 500;
    var lastSent = { text: null, at: 0 };

    // Resilient composer lookup with fallbacks.
    function findComposer() {
      return (
        document.querySelector("#prompt-textarea") ||
        document.querySelector('form textarea') ||
        document.querySelector('[contenteditable="true"][role="textbox"]') ||
        document.querySelector('div[contenteditable="true"]')
      );
    }

    function composerText(el) {
      if (!el) return "";
      if (el.value != null && el.value !== "") return el.value;      // <textarea>
      return el.innerText || el.textContent || "";                    // contenteditable
    }

    function maybeCapture(evt, el) {
      if (!el) return;
      if (global.OFLITRedact.isSensitiveField(el)) return;   // never on password-like
      var text = composerText(el);
      if (!decideSubmission(evt, text)) return;
      // de-dupe identical submission within 3s (guards double-bound handlers)
      var now = Date.now();
      if (lastSent.text === text.trim() && now - lastSent.at < 3000) return;
      var ev = buildEvent(text, global.OFLITRedact, maxChars);
      if (ev) {
        lastSent = { text: text.trim(), at: now };
        global.OFLITClient.send(ev);
      }
    }

    function bind() {
      var el = findComposer();
      if (!el || el.__oflitBound) return;
      el.__oflitBound = true;
      el.addEventListener("keydown", function (e) {
        maybeCapture(
          { kind: "keydown", key: e.key, shiftKey: e.shiftKey, isComposing: e.isComposing },
          el
        );
      }, true);
      // Send-button click (best-effort selectors).
      document.addEventListener("click", function (e) {
        var btn = e.target && e.target.closest &&
          e.target.closest('[data-testid="send-button"], button[aria-label*="Send" i], button[type="submit"]');
        if (btn) maybeCapture({ kind: "click" }, findComposer());
      }, true);
    }

    bind();
    var mo = new MutationObserver(function () { bind(); });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }
})(typeof window !== "undefined" ? window : globalThis);
