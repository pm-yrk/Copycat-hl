
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

  function findPercentInRow(el) {
    var row = el;
    for (var up = 0; up < 5 && row; up++, row = row.parentElement) {
      var txt = row.textContent || '';
      var m = txt.match(/\b(\d{1,3})%\b/);
      if (m) {
        var n = Math.max(0, Math.min(100, parseInt(m[1], 10)));
        return n;
      }
    }
    return null;
  }

  function fixFooter() {
    var footer = findCard('Market intelligence only.');
    if (footer) footer.classList.add('copycat-v7-footer');
  }

  function fixBars() {
    var exposure = document.querySelector('.copycat-v5-exposure') || findCard('long vs short exposure');
    if (!exposure) return;

    var candidates = Array.prototype.slice.call(exposure.querySelectorAll('*'));
    candidates.forEach(function (el) {
      var r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }

      if (r.width < 80 || r.width > 240 || r.height < 7 || r.height > 22) return;

      var cs = window.getComputedStyle(el);
      var radius = parseFloat(cs.borderRadius || '0');
      var hasChildren = el.children && el.children.length > 0;
      if (!hasChildren || radius < 4) return;

      var pct = findPercentInRow(el);
      if (pct === null) return;

      el.classList.add('copycat-v7-exposure-track');
      var green = 'rgb(44, 235, 170)';
      var red = 'rgb(255, 82, 122)';
      el.style.setProperty('background-image', 'linear-gradient(to right, ' + green + ' 0%, ' + green + ' ' + pct + '%, ' + red + ' ' + pct + '%, ' + red + ' 100%)', 'important');
      el.style.setProperty('background-color', 'transparent', 'important');

      Array.prototype.slice.call(el.children).forEach(function (child) {
        child.style.setProperty('background', 'transparent', 'important');
        child.style.setProperty('opacity', '0', 'important');
      });
    });
  }

  function run() {
    document.documentElement.classList.add('copycat-visual-v7');
    fixFooter();
    fixBars();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();

  setTimeout(run, 300);
  setTimeout(run, 1000);
  setTimeout(run, 2500);

  try {
    new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
