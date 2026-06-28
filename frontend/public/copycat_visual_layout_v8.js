
(function () {
  var GREEN = 'rgb(44, 235, 170)';
  var RED = 'rgb(255, 82, 122)';

  function hasText(el, label) {
    return el && (el.textContent || '').toLowerCase().indexOf(label.toLowerCase()) >= 0;
  }

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

  function findPercentElement(exposure) {
    return Array.prototype.slice.call(exposure.querySelectorAll('*')).filter(function (el) {
      var t = (el.textContent || '').trim();
      return /^\d{1,3}%$/.test(t);
    });
  }

  function climbRow(percentEl, exposure) {
    var n = percentEl;
    var pRect = percentEl.getBoundingClientRect();
    for (var i = 0; i < 7 && n && n !== exposure; i++, n = n.parentElement) {
      var txt = n.textContent || '';
      var r;
      try { r = n.getBoundingClientRect(); } catch (e) { continue; }
      if (r.width > 180 && r.height >= 18 && r.height <= 52 && txt.indexOf('%') >= 0) {
        return n;
      }
    }
    return percentEl.parentElement || percentEl;
  }

  function bestTrack(row, percentEl) {
    var rowRect = row.getBoundingClientRect();
    var pctRect = percentEl.getBoundingClientRect();
    var candidates = Array.prototype.slice.call(row.querySelectorAll('*'));
    var best = null;
    var bestScore = -1;

    candidates.forEach(function (el) {
      var r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }
      if (r.width < 70 || r.width > 260 || r.height < 7 || r.height > 20) return;
      if (r.left <= pctRect.left) return;
      if (r.top < rowRect.top - 3 || r.bottom > rowRect.bottom + 3) return;

      var cs = window.getComputedStyle(el);
      var radius = parseFloat(cs.borderRadius || '0');
      if (radius < 4) return;

      var childCount = el.children ? el.children.length : 0;
      var score = r.width + (childCount ? 100 : 0) - Math.abs(r.top - pctRect.top);
      if (score > bestScore) {
        best = el;
        bestScore = score;
      }
    });

    return best;
  }

  function disableV7Track(el) {
    el.classList.remove('copycat-v7-exposure-track');
  }

  function fixBars() {
    var exposure = document.querySelector('.copycat-v5-exposure') || findCard('long vs short exposure');
    if (!exposure) return;

    findPercentElement(exposure).forEach(function (pctEl) {
      var pct = Math.max(0, Math.min(100, parseInt((pctEl.textContent || '').trim(), 10)));
      var row = climbRow(pctEl, exposure);
      if (!row) return;
      row.classList.add('copycat-v8-exposure-row');

      var track = bestTrack(row, pctEl);
      if (!track) return;

      disableV7Track(track);
      track.classList.add('copycat-v8-exposure-track');

      var gradient = 'linear-gradient(to right, ' + GREEN + ' 0%, ' + GREEN + ' ' + pct + '%, ' + RED + ' ' + pct + '%, ' + RED + ' 100%)';
      track.style.setProperty('background-image', gradient, 'important');
      track.style.setProperty('background-color', 'transparent', 'important');
      track.style.setProperty('width', '104px', 'important');
      track.style.setProperty('min-width', '104px', 'important');
      track.style.setProperty('max-width', '104px', 'important');

      Array.prototype.slice.call(track.children || []).forEach(function (child) {
        child.style.setProperty('background', 'transparent', 'important');
        child.style.setProperty('opacity', '0', 'important');
      });
    });
  }

  function fixFooter() {
    var footer = findCard('Market intelligence only.');
    if (footer) footer.classList.add('copycat-v8-footer');
  }

  function run() {
    document.documentElement.classList.add('copycat-visual-v8');
    fixBars();
    fixFooter();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();

  setTimeout(run, 250);
  setTimeout(run, 900);
  setTimeout(run, 2000);

  try {
    new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
