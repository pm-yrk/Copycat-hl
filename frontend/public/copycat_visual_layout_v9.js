
(function () {
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

  function findPercentElements(exposure) {
    return Array.prototype.slice.call(exposure.querySelectorAll('*')).filter(function (el) {
      var t = (el.textContent || '').trim();
      return /^\d{1,3}%$/.test(t);
    });
  }

  function climbRow(percentEl, exposure) {
    var n = percentEl;
    for (var i = 0; i < 7 && n && n !== exposure; i++, n = n.parentElement) {
      var txt = n.textContent || '';
      var r;
      try { r = n.getBoundingClientRect(); } catch (e) { continue; }
      if (r.width > 150 && r.height >= 18 && r.height <= 52 && txt.indexOf('%') >= 0) {
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
      if (r.top < rowRect.top - 4 || r.bottom > rowRect.bottom + 4) return;

      var cs = window.getComputedStyle(el);
      var radius = parseFloat(cs.borderRadius || '0');
      if (radius < 4) return;

      var score = r.width - Math.abs(r.left - pctRect.right);
      if (score > bestScore) {
        best = el;
        bestScore = score;
      }
    });

    return best;
  }

  function markFooterAndTrimPage() {
    var footer = document.querySelector('.copycat-v8-footer, .copycat-v7-footer') || findCard('Market intelligence only.');
    if (!footer) return;
    footer.classList.add('copycat-v9-footer');

    // Remove extra space below footer by forcing the document height to end just after it.
    var footerBottom = footer.getBoundingClientRect().bottom + window.scrollY + 4;
    document.documentElement.style.setProperty('height', footerBottom + 'px', 'important');
    document.documentElement.style.setProperty('min-height', footerBottom + 'px', 'important');
    document.body.style.setProperty('height', footerBottom + 'px', 'important');
    document.body.style.setProperty('min-height', footerBottom + 'px', 'important');
    document.body.style.setProperty('padding-bottom', '0px', 'important');
    document.documentElement.style.setProperty('padding-bottom', '0px', 'important');

    // Also remove bottom margin/padding from likely shell ancestors.
    var p = footer.parentElement;
    var steps = 0;
    while (p && p !== document.body && steps < 4) {
      try {
        p.style.setProperty('padding-bottom', '0px', 'important');
        p.style.setProperty('margin-bottom', '0px', 'important');
      } catch (e) {}
      p = p.parentElement;
      steps++;
    }
  }

  function tightenExposureRows() {
    var exposure = document.querySelector('.copycat-v5-exposure') || findCard('long vs short exposure');
    if (!exposure) return;

    findPercentElements(exposure).forEach(function (pctEl) {
      var row = climbRow(pctEl, exposure);
      if (!row) return;

      row.classList.add('copycat-v9-exposure-row');
      pctEl.classList.add('copycat-v9-exposure-pct');
      try {
        row.style.setProperty('display', 'grid', 'important');
        row.style.setProperty('grid-template-columns', '24px 44px 30px 104px', 'important');
        row.style.setProperty('column-gap', '8px', 'important');
        row.style.setProperty('align-items', 'center', 'important');
        row.style.setProperty('justify-content', 'start', 'important');
      } catch (e) {}

      var track = bestTrack(row, pctEl);
      if (!track) return;
      track.classList.add('copycat-v9-exposure-track');
      try {
        track.style.setProperty('margin-left', '2px', 'important');
      } catch (e) {}
    });
  }

  function run() {
    document.documentElement.classList.add('copycat-visual-v9');
    tightenExposureRows();
    markFooterAndTrimPage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();

  setTimeout(run, 200);
  setTimeout(run, 800);
  setTimeout(run, 1800);
  window.addEventListener('resize', function () { setTimeout(run, 50); });

  try {
    new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
