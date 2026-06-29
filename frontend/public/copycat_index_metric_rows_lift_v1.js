(function () {
  function norm(text) {
    return (text || "").replace(/\s+/g, " ").trim().toUpperCase();
  }

  function isVisible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function exactText(root, text) {
    const wanted = norm(text);
    const nodes = root.querySelectorAll("*");
    for (const el of nodes) {
      if (norm(el.textContent) === wanted && isVisible(el)) return el;
    }
    return null;
  }

  function ancestorBox(el) {
    let node = el;
    let depth = 0;
    while (node && depth < 8) {
      const r = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      const hasBox =
        r.width >= 70 &&
        r.width <= 260 &&
        r.height >= 40 &&
        r.height <= 130 &&
        (
          style.borderRadius !== "0px" ||
          style.borderTopWidth !== "0px" ||
          style.backgroundColor !== "rgba(0, 0, 0, 0)"
        );

      if (hasBox) return node;
      node = node.parentElement;
      depth += 1;
    }
    return el;
  }

  function commonAncestor(nodes) {
    if (!nodes.length) return null;
    const chains = nodes.map((node) => {
      const chain = [];
      let n = node;
      while (n) {
        chain.push(n);
        n = n.parentElement;
      }
      return chain;
    });

    for (const candidate of chains[0]) {
      if (chains.every((chain) => chain.includes(candidate))) return candidate;
    }
    return null;
  }

  function tagIndexRows() {
    const wrapper = document.querySelector(".cc-index-compact-wrapper");
    if (!wrapper) return;

    const labels = ["COPYCAT", "BTC", "ETH", "S&P 500", "MAX DRAWDOWN"];
    const boxes = labels
      .map((label) => exactText(wrapper, label))
      .filter(Boolean)
      .map(ancestorBox)
      .filter(Boolean);

    if (boxes.length < 3) return;

    let row = commonAncestor(boxes);
    const wrapperRect = wrapper.getBoundingClientRect();

    // Walk up until we find the row holding the metric boxes, not the whole card.
    while (row && row !== wrapper) {
      const r = row.getBoundingClientRect();
      if (r.width >= wrapperRect.width * 0.65 && r.height <= 140) break;
      row = row.parentElement;
    }

    if (!row || row === wrapper) return;

    row.classList.add("copycat-index-metric-row-lift");

    // Move the model weights and explanatory line with the metric row.
    let sibling = row.nextElementSibling;
    let safety = 0;
    while (sibling && safety < 5) {
      sibling.classList.add("copycat-index-follow-row-lift");
      sibling = sibling.nextElementSibling;
      safety += 1;
    }

    const weights = Array.from(wrapper.querySelectorAll("*")).find((el) =>
      norm(el.textContent) === "CURRENT MODEL WEIGHTS"
    );
    if (weights) {
      let parent = weights.parentElement;
      for (let i = 0; parent && i < 4; i += 1) {
        parent.classList.add("copycat-index-follow-row-lift");
        parent = parent.parentElement;
      }
    }

    Array.from(wrapper.querySelectorAll("p")).forEach((p) => {
      if (norm(p.textContent).includes("LIVE MODEL PERFORMANCE")) {
        p.classList.add("copycat-index-follow-row-lift");
      }
    });
  }

  function run() {
    tagIndexRows();
    setTimeout(tagIndexRows, 200);
    setTimeout(tagIndexRows, 800);
    setTimeout(tagIndexRows, 1500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();