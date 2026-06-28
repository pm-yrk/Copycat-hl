
(function () {
  var GREEN = 'rgb(44, 235, 170)';
  var RED = 'rgb(255, 82, 122)';

  function text(el) { return (el && el.textContent || '').trim(); }
  function hasText(el, label) { return text(el).toLowerCase().indexOf(label.toLowerCase()) >= 0; }

  function nearestCard(el) {
    var n = el;
    while (n && n !== document.body) {
      try {
        var r = n.getBoundingClientRect();
        var cs = window.getComputedStyle(n);
        if (r.width > 180 && r.height > 70 && (
          (cs.borderRadius && cs.borderRadius !== '0px') ||
          ((n.className || '').toString().toLowerCase().indexOf('card') >= 0)
        )) return n;
      } catch (e) {}
      n = n.parentElement;
    }
    return el;
  }

  function findCard(label) {
    var nodes = Array.prototype.slice.call(document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span,section,article,p'));
    for (var i = 0; i < nodes.length; i++) {
      if (!hasText(nodes[i], label)) continue;
      var card = nearestCard(nodes[i]);
      if (card) return card;
    }
    return null;
  }

  function tagCard(card, cls) {
    if (!card) return;
    card.classList.add('copycat-v10-card', cls);
    card.style.transform = 'none';
    card.style.clipPath = 'none';
    card.style.webkitMaskImage = 'none';
    card.style.maskImage = 'none';
  }

  function addLocalTime() {
    if (document.getElementById('copycat-local-time-v10')) return;
    var menu = document.querySelector('button[aria-haspopup], button[aria-expanded], button');
    var buttons = Array.prototype.slice.call(document.querySelectorAll('button'));
    if (buttons.length) menu = buttons[buttons.length - 1];
    if (!menu || !menu.parentElement) return;

    var node = document.createElement('span');
    node.id = 'copycat-local-time-v10';
    node.className = 'copycat-local-time-v10';
    menu.parentElement.insertBefore(node, menu);

    function tick() {
      var d = new Date();
      node.textContent = new Intl.DateTimeFormat(undefined, {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }).format(d).replace(',', '').toUpperCase();
    }
    tick();
    setInterval(tick, 1000);
  }

  function percentElements(exposure) {
    return Array.prototype.slice.call(exposure.querySelectorAll('*')).filter(function (el) {
      return /^\d{1,3}%$/.test(text(el));
    });
  }

  function climbRow(percentEl, exposure) {
    var n = percentEl;
    for (var i = 0; i < 8 && n && n !== exposure; i++, n = n.parentElement) {
      var t = text(n);
      var r;
      try { r = n.getBoundingClientRect(); } catch (e) { continue; }
      if (r.width > 170 && r.height >= 18 && r.height <= 58 && /\d{1,3}%/.test(t)) return n;
    }
    return percentEl.parentElement || percentEl;
  }

  function findTrack(row, pctEl) {
    var rowRect = row.getBoundingClientRect();
    var pctRect = pctEl.getBoundingClientRect();
    var best = null;
    var bestScore = 999999;

    Array.prototype.slice.call(row.querySelectorAll('*')).forEach(function (el) {
      var r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }
      if (r.width < 60 || r.width > 260 || r.height < 7 || r.height > 22) return;
      if (r.left <= pctRect.left) return;
      if (r.top < rowRect.top - 5 || r.bottom > rowRect.bottom + 5) return;
      var cs = window.getComputedStyle(el);
      if (parseFloat(cs.borderRadius || '0') < 4) return;
      var score = Math.abs(r.left - pctRect.right);
      if (score < bestScore) {
        best = el;
        bestScore = score;
      }
    });
    return best;
  }

  function fixExposureBars(exposure) {
    if (!exposure) return;
    percentElements(exposure).forEach(function (pctEl) {
      var pct = Math.max(0, Math.min(100, parseInt(text(pctEl), 10)));
      var row = climbRow(pctEl, exposure);
      if (!row) return;
      row.classList.add('copycat-v10-exposure-row');
      pctEl.classList.add('copycat-v10-exposure-pct');

      var track = findTrack(row, pctEl);
      if (!track) return;
      track.classList.remove('copycat-v6-exposure-track', 'copycat-v7-exposure-track', 'copycat-v8-exposure-track', 'copycat-v9-exposure-track');
      track.classList.add('copycat-v10-exposure-track');

      var gradient = 'linear-gradient(to right, ' + GREEN + ' 0%, ' + GREEN + ' ' + pct + '%, ' + RED + ' ' + pct + '%, ' + RED + ' 100%)';
      track.style.setProperty('background-image', gradient, 'important');
      track.style.setProperty('background-color', 'transparent', 'important');
      track.style.setProperty('width', '112px', 'important');
      track.style.setProperty('min-width', '112px', 'important');
      track.style.setProperty('max-width', '112px', 'important');

      Array.prototype.slice.call(track.children || []).forEach(function (child) {
        child.style.setProperty('background', 'transparent', 'important');
        child.style.setProperty('opacity', '0', 'important');
      });
    });
  }

  function trimBottom(footer) {
    if (!footer) return;
    footer.classList.add('copycat-v10-footer');
    document.documentElement.style.removeProperty('height');
    document.documentElement.style.removeProperty('min-height');
    document.body.style.removeProperty('height');
    document.body.style.removeProperty('min-height');
    document.documentElement.style.setProperty('padding-bottom', '0px', 'important');
    document.body.style.setProperty('padding-bottom', '0px', 'important');
  }

  function run() {
    document.documentElement.classList.add('copycat-visual-v10');

    var portfolio = findCard('portfolio allocation');
    var exposure = findCard('long vs short exposure');
    var signal = findCard('asset signal board');
    var index = findCard('copycat index');
    var pressure = findCard('recent buyer') || findCard('buyer / seller') || findCard('buyer/seller pressure');
    var footer = findCard('Market intelligence only.');

    tagCard(portfolio, 'copycat-v10-portfolio');
    tagCard(exposure, 'copycat-v10-exposure');
    tagCard(signal, 'copycat-v10-signal');
    tagCard(index, 'copycat-v10-index');
    tagCard(pressure, 'copycat-v10-pressure');

    fixExposureBars(exposure);
    trimBottom(footer);
    addLocalTime();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();

  setTimeout(run, 250);
  setTimeout(run, 1000);
  setTimeout(run, 2500);
  window.addEventListener('resize', function () { setTimeout(run, 80); });

  try {
    new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
