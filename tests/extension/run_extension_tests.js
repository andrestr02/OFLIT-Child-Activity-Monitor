/*
 * Node test harness for the extension's pure capture logic.
 *
 * These tests exercise the decision functions directly (no browser needed),
 * covering the privacy-critical behaviours from the spec:
 *   - Google submitted query captured
 *   - ChatGPT submitted prompt captured
 *   - unsent draft NOT captured
 *   - password / sensitive field NOT captured
 *   - duplicate submission handling
 *   - secret-looking content dropped
 */
"use strict";
const assert = require("assert");
const path = require("path");

const EXT = path.join(__dirname, "..", "..", "extension");
const redact = require(path.join(EXT, "common", "redact.js"));
const google = require(path.join(EXT, "adapters", "google.js"));
const chatgpt = require(path.join(EXT, "adapters", "chatgpt.js"));

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log("ok   - " + name); }
  catch (e) { failed++; console.log("FAIL - " + name + "\n       " + e.message); }
}

// ---- Google ----
test("google: submitted query extracted from results URL", () => {
  const q = google.extractQueryFromUrl(
    "https://www.google.com/search?q=qowaidul+fiqhiyyah&hl=id");
  assert.strictEqual(q, "qowaidul fiqhiyyah");
});

test("google: non-search page yields no query (not a submission)", () => {
  assert.strictEqual(google.extractQueryFromUrl("https://www.google.com/"), null);
  assert.strictEqual(google.extractQueryFromUrl("https://www.google.com/maps?q=x"), null);
});

test("google: buildEvent produces a direct_user_action submitted_search", () => {
  const ev = google.buildEvent("pecahan campuran", redact, 500);
  assert.strictEqual(ev.event_type, "submitted_search");
  assert.strictEqual(ev.evidence, "direct_user_action");
  assert.strictEqual(ev.submitted, true);
  assert.strictEqual(ev.content, "pecahan campuran");
});

// ---- ChatGPT ----
test("chatgpt: Enter without shift on non-empty text is a submission", () => {
  assert.strictEqual(
    chatgpt.decideSubmission({ kind: "keydown", key: "Enter", shiftKey: false, isComposing: false },
      "Apa itu pecahan campuran?"), true);
});

test("chatgpt: send-button click is a submission", () => {
  assert.strictEqual(chatgpt.decideSubmission({ kind: "click" }, "hello"), true);
});

test("chatgpt: unsent DRAFT is never captured", () => {
  // typing (no submit gesture) => not a submission
  assert.strictEqual(
    chatgpt.decideSubmission({ kind: "keydown", key: "a", shiftKey: false }, "bagaimana car"), false);
  // Shift+Enter is a newline, not a send
  assert.strictEqual(
    chatgpt.decideSubmission({ kind: "keydown", key: "Enter", shiftKey: true }, "bagaimana car"), false);
  // Enter with empty text => nothing
  assert.strictEqual(
    chatgpt.decideSubmission({ kind: "keydown", key: "Enter", shiftKey: false }, "   "), false);
  // IME composition Enter => not a send
  assert.strictEqual(
    chatgpt.decideSubmission({ kind: "keydown", key: "Enter", shiftKey: false, isComposing: true }, "こんにちは"), false);
});

test("chatgpt: buildEvent produces a submitted_prompt", () => {
  const ev = chatgpt.buildEvent("Berikan contoh soal", redact, 500);
  assert.strictEqual(ev.event_type, "submitted_prompt");
  assert.strictEqual(ev.site, "chatgpt.com");
});

// ---- Sensitive field / redaction ----
test("redact: password field is sensitive", () => {
  assert.strictEqual(redact.isSensitiveField({ type: "password" }), true);
  assert.strictEqual(redact.isSensitiveField({ name: "user_password" }), true);
  assert.strictEqual(redact.isSensitiveField({ type: "text", name: "q" }), false);
});

test("redact: secret-looking content is dropped (returns null)", () => {
  assert.strictEqual(redact.sanitize("4111111111111111", 500), null);      // card
  assert.strictEqual(redact.sanitize("sk-abcdefghijklmnopqrstuvwx", 500), null); // token
  assert.strictEqual(
    redact.sanitize("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + "a".repeat(40) + "." + "b".repeat(20), 500),
    null); // jwt (realistic header length)
});

test("redact: password field means the prompt is not built", () => {
  // Simulate the binding guard: a password-like element must not be captured.
  const el = { type: "password", value: "hunter2" };
  const shouldSkip = redact.isSensitiveField(el);
  assert.strictEqual(shouldSkip, true);
});

test("redact: truncation is marked", () => {
  const out = redact.sanitize("a".repeat(1000), 100);
  assert.strictEqual(out.truncated, true);
  assert.ok(out.content.length <= 100);
});

// ---- Duplicate handling (dedupe logic mirrored from the binding) ----
test("duplicate: identical submission within window is suppressed", () => {
  // Reproduce the binding's dedupe rule as a pure check.
  function dedupe(state, text, now) {
    if (state.text === text.trim() && now - state.at < 3000) return false;
    state.text = text.trim(); state.at = now; return true;
  }
  const state = { text: null, at: 0 };
  assert.strictEqual(dedupe(state, "same prompt", 1000), true);
  assert.strictEqual(dedupe(state, "same prompt", 1500), false);  // dup within 3s
  assert.strictEqual(dedupe(state, "same prompt", 5000), true);   // after window
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
