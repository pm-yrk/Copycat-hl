(() => {
  const MAX = 820;
  const STYLE_ID = 'copycat-mobile-dom-fix-v2-style';

  function mobile() {
    return window.matchMedia && window.matchMedia(`(max-width: ${MAX}px)`).matches;
  }

  function addStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
@media (max-width: 820px) {
  html, body {
    max-width: 100% !important;
    overflow-x: hidden !important;
  }

  .cc-mobile-force-stack {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) !important;
    grid-auto-flow: row !important;
    gap: 24px !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    overflow: visible !important;
  }

  .cc-mobile-full-card {
    width: calc(100vw - 60px) !important;
    max-width: calc(100vw - 60px) !important;
    min-width: 0 !important;
    grid-column: 1 / -1 !important;
    flex: 0 0 auto !important;
    justify-self: stretch !important;
    overflow: hidden !important;
    transform: none !important;
  }

  .cc-mobile-full-card table {
    table-layout: fixed !important;
    width: 100% !important;
  }

  .cc-mobile-full-card th,
  .cc-mobile-full-card td {
    min-width: 0 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }

  .cc-mobile-allocation-card,
  .cc-mobile-allocation-card * {
    max-width: 100% !important;
  }

  .cc-mobile-allocation-card .cc-donut-layout,
  .cc-mobile-allocation-card [class*="donut"],
  .cc-mobile-allocation-card [class*="legend"] {
    max-width: 100% !important;
  }

  .cc-mobile-index-card {
    height: auto !important;
    min-height: 760px !important;
    max-height: none !important;
    overflow: visible !important;
    padding-bottom: 34px !important;
    margin-bottom: 34px !important;
  }

  .cc-mobile-index-card .cc-index-chart {
    min-height: 250px !important;
    height: 250px !important;
  }

  .cc-mobile-index-card .cc-index-metrics {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    gap: 12px !important;
    width: 100% !important;
    max-width: 100% !important;
    overflow: visible !important;
  }

  .cc-mobile-menu-fixed {
    position: fixed !important;
    top: max(18px, env(safe-area-inset-top)) !important;
    right: 22px !important;
    left: auto !important;
    margin: 0 !important;
    transform: none !important;
    z-index: 9999 !important;
  }

  .cc-mobile-footer-polish {
    padding: 28px 22px !important;
    text-align: center !important;
    overflow: hidden !important;
  }

  .cc-mobile-footer-polish p,
  .cc-mobile-footer-polish div {
    overflow-wrap: anywhere !important;
    line-height: 1.35 !important;
  }

  .cc-mobile-footer-polish a {
    display: inline-block !important;
    margin: 4px 8px !important;
  }
}`;
    document.head.appendChild(style);
  }

  function txt(el) {
    return (el && el.textContent ? el.textContent : '').replace(/\\s+/g, ' ').trim();
  }

  function visible(el) {
    const r = el.getBoundingClientRect();
    return r.width > 40 && r.height > 30;
  }

  function bestCard(regex) {
    const nodes = Array.from(document.querySelectorAll('section, article, div'));
    const matches = nodes
      .filter((el) => regex.test(txt(el)) && visible(el))
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { el, area: r.width * r.height, width: r.width, height: r.height };
      })
      .filter((x) => x.width > 180 && x.height > 110)
      .sort((a, b) => a.area - b.area);
    return matches.length ? matches[0].el : null;
  }

  function addClass(el, cls) {
    if (el && !el.classList.contains(cls)) el.classList.add(cls);
  }

  function forceParents(card) {
    if (!card) return;
    let p = card.parentElement;
    let depth = 0;
    while (p && p !== document.body && depth < 4) {
      const r = p.getBoundingClientRect();
      if (r.width > window.innerWidth * 0.78 || p.scrollWidth > window.innerWidth + 8) {
        addClass(p, 'cc-mobile-force-stack');
      }
      p = p.parentElement;
      depth += 1;
    }
  }

  function makeFull(card, extra) {
    if (!card) return;
    addClass(card, 'cc-mobile-full-card');
    if (extra) addClass(card, extra);
    card.style.width = 'calc(100vw - 60px)';
    card.style.maxWidth = 'calc(100vw - 60px)';
    card.style.minWidth = '0';
    card.style.gridColumn = '1 / -1';
    card.style.transform = 'none';
    forceParents(card);
  }

  function commonParent(cards) {
    const live = cards.filter(Boolean);
    if (live.length < 2) return null;
    const chains = live.map((el) => {
      const out = [];
      let p = el.parentElement;
      while (p && p !== document.body) {
        out.push(p);
        p = p.parentElement;
      }
      return out;
    });
    return chains[0].find((p) => chains.every((chain) => chain.includes(p))) || null;
  }

  function fixMenu() {
    const candidates = Array.from(document.querySelectorAll('button, [role="button"], a'))
      .filter((el) => visible(el))
      .filter((el) => {
        const r = el.getBoundingClientRect();
        const t = txt(el);
        const aria = `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`;
        return r.top < 260 && r.width <= 180 && r.height <= 110 &&
          (/menu|navigation|open/i.test(aria) || /[.•]{2,}|⋯|…/.test(t));
      })
      .sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        return ar.top - br.top || br.left - ar.left;
      });
    const btn = candidates[0];
    if (btn) addClass(btn, 'cc-mobile-menu-fixed');
  }

  function polishFooter() {
    const footer = bestCard(/Market intelligence only/i) || document.querySelector('footer');
    if (footer) addClass(footer, 'cc-mobile-footer-polish');
  }

  function apply() {
    if (!mobile()) return;
    addStyle();

    document.documentElement.style.overflowX = 'hidden';
    document.body.style.overflowX = 'hidden';

    fixMenu();

    const signal = bestCard(/ASSET SIGNAL BOARD/i);
    const allocation = bestCard(/PORTFOLIO ALLOCATION/i);
    const exposure = bestCard(/LONG\\s+.*SHORT\\s+.*EXPOSURE|LONG\\s+.*EXPOSURE/i);
    const index = bestCard(/COPYCAT LIVE STRATEGY INDEX/i);
    const pressure = bestCard(/RECENT BUYER\\s*\\/\\s*SELLER PRESSURE/i);

    [signal, allocation, exposure, index, pressure].forEach((card) => makeFull(card));
    makeFull(allocation, 'cc-mobile-allocation-card');
    makeFull(exposure, 'cc-mobile-exposure-card');
    makeFull(index, 'cc-mobile-index-card');

    const group = commonParent([signal, allocation, exposure]) || commonParent([allocation, exposure]);
    if (group) addClass(group, 'cc-mobile-force-stack');

    if (allocation) allocation.style.order = '20';
    if (exposure) exposure.style.order = '21';

    if (index) {
      const next = index.nextElementSibling;
      if (next) next.style.marginTop = '28px';
    }

    polishFooter();
  }

  const schedule = () => {
    apply();
    window.setTimeout(apply, 250);
    window.setTimeout(apply, 1000);
    window.setTimeout(apply, 2500);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule, { once: true });
  } else {
    schedule();
  }

  window.addEventListener('resize', schedule);
  window.addEventListener('orientationchange', schedule);
})();