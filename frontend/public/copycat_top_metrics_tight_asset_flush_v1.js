(function () {
  const METRIC_TITLES = [
    'COPYCAT-RANKED WALLETS',
    'TRACKED ACCOUNT VALUE',
    'OPEN POSITION VALUE',
    'ASSETS WITH SIGNALS'
  ];

  function norm(s) {
    return (s || '').replace(/\s+/g, ' ').trim().toUpperCase();
  }

  function findExactTextElement(text) {
    const wanted = norm(text);
    const nodes = document.querySelectorAll('body *');
    for (const el of nodes) {
      if (norm(el.textContent) === wanted) return el;
    }
    return null;
  }

  function findCardAncestor(start, minWidth, minHeight) {
    let el = start;
    let depth = 0;
    while (el && depth < 10) {
      const r = el.getBoundingClientRect();
      if (r.width >= minWidth && r.height >= minHeight) return el;
      el = el.parentElement;
      depth += 1;
    }
    return null;
  }

  function tagMetricCards() {
    METRIC_TITLES.forEach((title) => {
      const titleEl = findExactTextElement(title);
      if (!titleEl) return;
      const card = findCardAncestor(titleEl, 220, 70);
      if (!card) return;
      card.classList.add('copycat-top-metric-tight');

      const descendants = Array.from(card.querySelectorAll('*'));
      const main = descendants
        .filter((el) => /[$\d]/.test(el.textContent || ''))
        .map((el) => ({ el, size: parseFloat(getComputedStyle(el).fontSize || '0') }))
        .filter((x) => x.size >= 24)
        .sort((a, b) => b.size - a.size)[0];
      if (main) main.el.classList.add('copycat-top-metric-value');

      descendants.forEach((el) => {
        const size = parseFloat(getComputedStyle(el).fontSize || '0');
        if (size >= 10 && size <= 16 && el !== (main && main.el)) {
          const t = (el.textContent || '').trim();
          if (t && t.length <= 60) el.classList.add('copycat-top-metric-support');
        }
      });
    });
  }

  function flushAssetBoard() {
    const titleEl = findExactTextElement('ASSET SIGNAL BOARD');
    if (!titleEl) return;
    const card = findCardAncestor(titleEl, 300, 120);
    if (card) card.classList.add('copycat-asset-board-flush');
  }

  function apply() {
    tagMetricCards();
    flushAssetBoard();
  }

  window.addEventListener('load', apply);
  document.addEventListener('DOMContentLoaded', function () {
    apply();
    setTimeout(apply, 200);
    setTimeout(apply, 800);
    setTimeout(apply, 1500);
  });
})();
