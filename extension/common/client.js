/*
 * client.js — thin content-script -> background bridge.
 *
 * Content scripts never talk to the network directly. They hand a completed
 * event object to the background service worker, which owns the single
 * localhost host permission and posts to the local agent. This keeps network
 * capability out of the page context.
 */
(function (global) {
  "use strict";
  function send(event) {
    try {
      if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: "oflit_event", event: event }, function () {
          // ignore response / lastError — delivery is best-effort from the page
          void (chrome.runtime && chrome.runtime.lastError);
        });
      }
    } catch (e) {
      // Never throw into the host page.
    }
  }
  global.OFLITClient = { send: send };
})(typeof window !== "undefined" ? window : globalThis);
