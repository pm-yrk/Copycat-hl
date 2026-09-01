
(function () {
  function formatLocalTime() {
    try {
      return new Intl.DateTimeFormat(undefined, {
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false
      }).format(new Date()).replace(",", "").toUpperCase();
    } catch (e) {
      return new Date().toLocaleString();
    }
  }

  function findMenuButton() {
    var buttons = Array.prototype.slice.call(document.querySelectorAll("button"));
    if (!buttons.length) return null;

    // Prefer the small top-right menu button.
    var best = null;
    var bestScore = -Infinity;

    buttons.forEach(function (button) {
      try {
        var r = button.getBoundingClientRect();
        if (r.width < 18 || r.height < 18) return;

        var score = 0;
        score += r.left;              // further right is better
        score -= r.top * 2;           // higher is better
        if (button.getAttribute("aria-haspopup")) score += 500;
        if (button.getAttribute("aria-expanded") !== null) score += 500;
        if ((button.textContent || "").indexOf("•••") >= 0) score += 300;
        if ((button.textContent || "").indexOf("...") >= 0) score += 300;

        if (score > bestScore) {
          best = button;
          bestScore = score;
        }
      } catch (e) {}
    });

    return best || buttons[buttons.length - 1];
  }

  function ensureClock() {
    // Public redesign pages have their own navigation and must not receive the legacy floating clock.
    // Keep the existing dashboard clock behavior unchanged.
    if (document.querySelector(".public-redesign-root")) {
      var existing = document.getElementById("copycat-local-viewer-time");
      if (existing) existing.remove();
      return;
    }
    var menu = findMenuButton();
    if (!menu || !menu.parentElement) return;

    var clock = document.getElementById("copycat-local-viewer-time");
    if (!clock) {
      clock = document.createElement("span");
      clock.id = "copycat-local-viewer-time";
      clock.className = "copycat-local-viewer-time";
      menu.parentElement.insertBefore(clock, menu);
    }

    clock.textContent = formatLocalTime();
  }

  ensureClock();
  setInterval(ensureClock, 1000);
  setTimeout(ensureClock, 300);
  setTimeout(ensureClock, 1200);
})();
