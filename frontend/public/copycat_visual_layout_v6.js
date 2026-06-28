(function () {
  function hasText(el, label) {
    return (el && (el.textContent || '').toLowerCase().indexOf(label.toLowerCase()) >= 0);
  }

  function nearestCard(el) {
    var n = el;
    while (n && n !== document.body) {
      try {
        var r = n.getBoundingClientRect();
        var cs = window.getComputedStyle(n);
        var looksCard = r.width > 180 && r.height > 70 && (
          (cs.borderRadius && cs.borderRadius !== '0px') ||
          ((n.className || '').toString().toLowerCase().indexOf('card') >= 0)
        );
        if (looksCard) return n;
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
      if (!card) continue;
      var r = card.getBoundingClientRect();
      if (r.width > 180 && r.height > 70) return card;
    }
    return null;
  }

  function tagFooter() {
    var footer = findCard('Market intelligence only.');
    if (footer) footer.classList.add('copycat-v6-footer');
  }

  function tagExposureTracks() {
    var exposure = document.querySelector('.copycat-v5-exposure') || findCard('long vs short exposure');
    if (!exposure) return;

    var seen = 0;
    var nodes = Array.prototype.slice.call(exposure.querySelectorAll('*'));
    nodes.forEach(function (el) {
      if (seen >= 24) return;
      if (!el || el.classList.contains('copycat-v6-exposure-track')) return;
      var r;
      try { r = el.getBoundingClientRect(); } catch (e) { return; }
      if (!r || r.width < 130 || r.height < 8 || r.height > 22) return;

      var childHit = false;
      for (var i = 0; i < el.children.length; i++) {
        var c = el.children[i];
        var cr;
        try { cr = c.getBoundingClientRect(); } catch (e) { continue; }
        if (cr.width > 10 && cr.width <= r.width && cr.height >= 4 && cr.height <= 22) {
          childHit = true;
          break;
        }
      }
      if (!childHit) return;

      var parent = el.parentElement;
      if (parent && parent.classList.contains('copycat-v6-exposure-track')) return;
      el.classList.add('copycat-v6-exposure-track');
      seen++;
    });
  }

  function run() {
    document.documentElement.classList.add('copycat-visual-v6');
    tagFooter();
    tagExposureTracks();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
  setTimeout(run, 350);
  setTimeout(run, 1200);
  setTimeout(run, 2500);
  try {
    new MutationObserver(function () { run(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
