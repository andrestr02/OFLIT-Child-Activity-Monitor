/*
 * google.js — Google Search adapter.
 *
 * Capture strategy (deliberately NOT a keylogger, NOT a fragile DOM scrape):
 * a Google search query is only recorded once it has actually been SUBMITTED,
 * which we detect from the results-page URL (`/search?q=...`). Landing on the
 * results page is itself proof of submission, and reading the `q` parameter is
 * far more stable than scraping the DOM. We de-duplicate the same query within
 * a page's lifetime so a re-render does not double-report.
 *
 * The pure functions here are unit-tested in Node; the thin browser binding at
 * the bottom only wires them to real page events.
 */
(function (global) {
  "use strict";

  var SEARCH_PATHS = ["/search"];

  /* Extract a submitted query from a results URL, or null. */
  function extractQueryFromUrl(urlString) {
    var url;
    try {
      url = new URL(urlString);
    } catch (e) {
      return null;
    }
    if (!/(^|\.)google\.com$/.test(url.hostname)) return null;
    if (SEARCH_PATHS.indexOf(url.pathname) === -1) return null;
    var q = url.searchParams.get("q");
    if (!q) return null;
    q = q.trim();
    if (!q) return null;
    // Ignore Google's own instant/background param noise: require a real query.
    return q;
  }

  function buildEvent(query, redact, maxChars) {
    var clean = redact.sanitize(query, maxChars);
    if (!clean) return null;
    return {
      schema_version: 1,
      event_type: "submitted_search",
      source: "browser_extension",
      site: "google.com",
      evidence: "direct_user_action",
      submitted: true,
      content: clean.content,
      truncated: clean.truncated,
      timestamp: new Date().toISOString()
    };
  }

  var api = {
    extractQueryFromUrl: extractQueryFromUrl,
    buildEvent: buildEvent
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.OFLITGoogle = api;

  // ---- browser binding (skipped in Node tests) ----
  if (typeof document !== "undefined" && global.OFLITClient) {
    var lastReported = null;
    var maxChars = global.OFLIT_MAX_CHARS || 500;

    function report() {
      var q = extractQueryFromUrl(location.href);
      if (!q || q === lastReported) return;
      var ev = buildEvent(q, global.OFLITRedact, maxChars);
      if (ev) {
        lastReported = q;
        global.OFLITClient.send(ev);
      }
    }

    // Initial results-page load and SPA-style navigations.
    report();
    var lastHref = location.href;
    setInterval(function () {
      if (location.href !== lastHref) {
        lastHref = location.href;
        report();
      }
    }, 1000);
  }
})(typeof window !== "undefined" ? window : globalThis);
