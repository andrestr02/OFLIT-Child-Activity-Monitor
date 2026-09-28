/*
 * background.js — MV3 service worker.
 *
 * Owns the single localhost host permission. Receives completed events from
 * content scripts and POSTs them to the local OFLIT activity agent on
 * 127.0.0.1. The endpoint and optional token come from managed policy
 * (chrome.storage.managed) so nothing is hard-coded and no secret ships in the
 * source. Delivery is best-effort; failures are swallowed (the agent's own
 * durable store / session model is the source of truth, not the extension).
 */
"use strict";

var DEFAULTS = {
  endpoint: "http://127.0.0.1:8791/event",
  token: "",
  maxChars: 500
};

function getPolicy() {
  return new Promise(function (resolve) {
    try {
      chrome.storage.managed.get(
        ["endpoint", "token", "maxChars"],
        function (items) {
          if (chrome.runtime.lastError || !items) return resolve(DEFAULTS);
          resolve({
            endpoint: items.endpoint || DEFAULTS.endpoint,
            token: items.token || DEFAULTS.token,
            maxChars: items.maxChars || DEFAULTS.maxChars
          });
        }
      );
    } catch (e) {
      resolve(DEFAULTS);
    }
  });
}

async function forward(event) {
  var policy = await getPolicy();
  var headers = { "Content-Type": "application/json" };
  if (policy.token) headers["X-OFLIT-Token"] = policy.token;
  try {
    await fetch(policy.endpoint, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(event),
      // Loopback only; never send cookies/credentials to the agent.
      credentials: "omit",
      cache: "no-store"
    });
  } catch (e) {
    // Agent may be down; that is fine — this is not a dependency for the child.
  }
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (msg && msg.type === "oflit_event" && msg.event) {
    forward(msg.event);
  }
  // synchronous ack; no long-lived channel needed
  if (sendResponse) sendResponse({ ok: true });
  return false;
});
