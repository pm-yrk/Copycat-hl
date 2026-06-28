
(function () {
  var clockEl = null;
  var scheduled = false;

  function formatLocalDateTime() {
    try {
      return new Intl.DateTimeFormat(navigator.language || undefined, {
        weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
      }).format(new Date());
    } catch (e) { return new Date().toLocaleString(); }
  }

  function scoreTopRight(el) {
    try {
      var r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0 || r.top > 120) return -1;
      return r.left + r.right;
    } catch (e) { return -1; }
  }

  function findMenuButton() {
    var best = null, bestScore = -1;
    Array.prototype.slice.call(document.querySelectorAll('button, a, [role="button"]')).forEach(function (el) {
      var text = (el.textContent || '').trim().toLowerCase();
      var aria = (el.getAttribute('aria-label') || '').toLowerCase();
      var cls = (el.className || '').toString().toLowerCase();
      var ok = text === '...' || text === '•••' || text === '⋯' || text === '…' ||
        text.indexOf('•••') >= 0 || text.indexOf('...') >= 0 ||
        aria.indexOf('menu') >= 0 || aria.indexOf('more') >= 0 ||
        cls.indexOf('menu') >= 0 || cls.indexOf('dropdown') >= 0;
      if (!ok) return;
      var s = scoreTopRight(el);
      if (s > bestScore) { best = el; bestScore = s; }
    });
    return best;
  }

  function ensureClock() {
    var menu = findMenuButton();
    if (!menu || !menu.parentNode) return;
    if (!clockEl) {
      clockEl = document.createElement('span');
      clockEl.className = 'copycat-local-clock';
      clockEl.setAttribute('aria-live', 'polite');
    }
    if (clockEl.parentNode !== menu.parentNode || clockEl.nextSibling !== menu) {
      menu.parentNode.insertBefore(clockEl, menu);
    }
    clockEl.textContent = formatLocalDateTime();
  }

  function hasText(el, label) {
    return (el.textContent || '').toLowerCase().indexOf(label.toLowerCase()) >= 0;
  }
  function cardFor(el) { return el && (el.closest('[class*="card"], article, section') || el); }
  function findCard(label) {
    var nodes = Array.prototype.slice.call(document.querySelectorAll('h1,h2,h3,h4,h5,h6,[class*="title"],[class*="header"],span,div'));
    for (var i = 0; i < nodes.length; i++) {
      if (!hasText(nodes[i], label)) continue;
      var c = cardFor(nodes[i]);
      if (!c) continue;
      var r = c.getBoundingClientRect();
      if (r.width > 120 && r.height > 80) return c;
    }
    return null;
  }
  function ensureRow(id, before, cls) {
    var row = document.getElementById(id);
    if (!row) { row = document.createElement('div'); row.id = id; row.className = cls; }
    if (before && before.parentNode && row.parentNode !== before.parentNode) before.parentNode.insertBefore(row, before);
    return row;
  }
  function arrangeCards() {
    var portfolio = findCard('portfolio allocation');
    var exposure = findCard('long vs short exposure');
    var signal = findCard('asset signal board');
    var index = findCard('copycat index');
    var pressure = findCard('recent buyer') || findCard('buyer / seller') || findCard('buyer/seller pressure');
    if (portfolio) portfolio.classList.add('copycat-card-portfolio');
    if (exposure) exposure.classList.add('copycat-card-exposure');
    if (signal) signal.classList.add('copycat-card-signal');
    if (index) index.classList.add('copycat-card-index');
    if (pressure) pressure.classList.add('copycat-card-pressure');
    if (portfolio && exposure && signal) {
      var mid = ensureRow('copycat-visual-middle-row', portfolio, 'copycat-visual-row copycat-visual-middle-row');
      [portfolio, exposure, signal].forEach(function (c) { if (c && c.parentNode !== mid) mid.appendChild(c); });
    }
    if (index && pressure) {
      var bot = ensureRow('copycat-visual-bottom-row', index, 'copycat-visual-row copycat-visual-bottom-row');
      [index, pressure].forEach(function (c) { if (c && c.parentNode !== bot) bot.appendChild(c); });
    }
  }
  function run() { scheduled = false; ensureClock(); arrangeCards(); }
  function schedule() { if (scheduled) return; scheduled = true; window.requestAnimationFrame(run); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule); else schedule();
  setInterval(ensureClock, 1000);
  setTimeout(schedule, 500); setTimeout(schedule, 1500); setTimeout(schedule, 3500);
  try { new MutationObserver(function () { schedule(); }).observe(document.documentElement, {childList:true, subtree:true}); } catch (e) {}
})();
