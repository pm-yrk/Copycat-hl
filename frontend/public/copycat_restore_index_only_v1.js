(function () {
  function cleanIndexOnly() {
    const index = document.querySelector(".cc-index-compact-wrapper");
    if (!index) return;

    // Keep the wrapper/card itself untouched, but remove accidental layer tags
    // from children inside the Index card.
    index.querySelectorAll(".copycat-front-layer-v2").forEach((el) => {
      el.classList.remove("copycat-front-layer-v2");
    });

    // If the old metric-row-lift script still runs, remove those classes too.
    index.querySelectorAll(".copycat-index-metric-row-lift, .copycat-index-follow-row-lift").forEach((el) => {
      el.classList.remove("copycat-index-metric-row-lift");
      el.classList.remove("copycat-index-follow-row-lift");
    });
  }

  function run() {
    cleanIndexOnly();
    setTimeout(cleanIndexOnly, 250);
    setTimeout(cleanIndexOnly, 900);
    setTimeout(cleanIndexOnly, 1800);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  window.addEventListener("load", run);
})();