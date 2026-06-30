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

  function findFooterCard() {
    const target = "MARKET INTELLIGENCE ONLY.";
    const nodes = document.querySelectorAll("body *");

    for (const el of nodes) {
      if (norm(el.textContent) === target) {
        let node = el;
        let best = null;

        for (let depth = 0; node && depth < 12; depth += 1) {
          const r = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          const hasCardShape =
            r.width > window.innerWidth * 0.55 &&
            r.height >= 50 &&
            (
              style.borderRadius !== "0px" ||
              style.borderTopWidth !== "0px" ||
              style.backgroundColor !== "rgba(0, 0, 0, 0)"
            );

          if (hasCardShape) best = node;
          node = node.parentElement;
        }

        if (best) return best;
      }
    }

    return null;
  }

  function apply() {
    const card = findFooterCard();
    if (card) card.classList.add("copycat-disclaimer-footer-compact");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }

  window.addEventListener("load", function () {
    apply();
    setTimeout(apply, 250);
    setTimeout(apply, 1000);
  });
})();

})();
