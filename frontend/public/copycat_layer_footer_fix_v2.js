/* COPYCAT_DASHBOARD_ONLY_SCRIPT_SCOPE_V1
   This helper is dashboard-only so it cannot affect the landing page, API page,
   or the top-right menu on first load. */
(function () {
  if (!/^\/dashboard(?:\/|$)/.test(window.location.pathname)) {
    return;
  }

(function () {
  function norm(text) {
    return (text || "").replace(/\s+/g, " ").trim().toUpperCase();
  }

  function isCardLike(el) {
    if (!el || el === document.body || el === document.documentElement) return false;

    const r = el.getBoundingClientRect();
    if (r.width < 170 || r.height < 45) return false;
    if (r.width > window.innerWidth * 0.98 && r.height > window.innerHeight * 0.75) return false;

    const style = window.getComputedStyle(el);
    const radius = parseFloat(style.borderTopLeftRadius || "0");
    const border = parseFloat(style.borderTopWidth || "0") + parseFloat(style.borderRightWidth || "0");
    const bg = style.backgroundColor || "";

    const hasShape =
      radius >= 8 ||
      border > 0 ||
      bg.includes("rgb");

    const text = norm(el.textContent);
    const hasDashboardText =
      text.includes("COPYCAT-RANKED WALLETS") ||
      text.includes("TRACKED ACCOUNT VALUE") ||
      text.includes("OPEN POSITION VALUE") ||
      text.includes("ASSETS WITH SIGNALS") ||
      text.includes("PORTFOLIO ALLOCATION") ||
      text.includes("LONG VS SHORT EXPOSURE") ||
      text.includes("ASSET SIGNAL BOARD") ||
      text.includes("COPYCAT LIVE STRATEGY INDEX") ||
      text.includes("RECENT BUYER / SELLER PRESSURE") ||
      text.includes("MOST RECENT ORDERS") ||
      text.includes("AT A GLANCE") ||
      text.includes("MARKET INTELLIGENCE ONLY");

    return hasShape && hasDashboardText;
  }

  function smallestCardAncestor(el) {
    let node = el;
    let best = null;

    for (let depth = 0; node && depth < 12; depth += 1) {
      if (isCardLike(node)) best = node;
      node = node.parentElement;
    }

    return best;
  }

  function tagCards() {
    const texts = [
      "COPYCAT-RANKED WALLETS",
      "TRACKED ACCOUNT VALUE",
      "OPEN POSITION VALUE",
      "ASSETS WITH SIGNALS",
      "PORTFOLIO ALLOCATION",
      "LONG VS SHORT EXPOSURE",
      "ASSET SIGNAL BOARD",
      "COPYCAT LIVE STRATEGY INDEX",
      "RECENT BUYER / SELLER PRESSURE",
      "MOST RECENT ORDERS",
      "AT A GLANCE",
      "MARKET INTELLIGENCE ONLY"
    ];

    const nodes = Array.from(document.querySelectorAll("body *"));
    const cards = new Set();

    for (const node of nodes) {
      const nodeText = norm(node.textContent);
      if (!nodeText) continue;

      for (const text of texts) {
        if (!nodeText.includes(text)) continue;
        const card = smallestCardAncestor(node);
        if (card) cards.add(card);
      }
    }

    for (const card of cards) {
      card.classList.add("copycat-front-layer-v2");
      if (norm(card.textContent).includes("MARKET INTELLIGENCE ONLY")) {
        card.classList.add("copycat-footer-compact-v2");
      }
    }
  }

  function run() {
    tagCards();
    setTimeout(tagCards, 200);
    setTimeout(tagCards, 800);
    setTimeout(tagCards, 1500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  window.addEventListener("load", run);
})();

})();
