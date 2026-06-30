(function () {
  function isTopRightButton(el) {
    if (!el || el.tagName !== "BUTTON") return false;
    const r = el.getBoundingClientRect();
    return r.width > 20 && r.height > 20 && r.right > window.innerWidth - 140 && r.top < 90;
  }

  function tagMenuButton() {
    const buttons = Array.from(document.querySelectorAll("button"));
    for (const btn of buttons) {
      if (!isTopRightButton(btn)) continue;
      btn.classList.add("copycat-menu-layer-hotfix");

      let parent = btn.parentElement;
      for (let i = 0; parent && i < 5; i += 1) {
        parent.classList.add("copycat-menu-layer-hotfix");
        parent = parent.parentElement;
      }
    }
  }

  function run() {
    tagMenuButton();
    setTimeout(tagMenuButton, 250);
    setTimeout(tagMenuButton, 900);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  window.addEventListener("load", run);
})();