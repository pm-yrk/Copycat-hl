
(function () {
  function hasText(el, label) {
    return (el.textContent || '').toLowerCase().indexOf(label.toLowerCase()) >= 0;
  }

  function nearestCard(el) {
    var n = el;
    while (n && n !== document.body) {
      try {
        var r = n.getBoundingClientRect();
        var cs = window.getComputedStyle(n);
        var looksCard = r.width > 180 && r.height > 100 && (
          (cs.borderRadius && cs.borderRadius !== '0px') ||
          (cs.borderColor && cs.borderColor !== 'rgba(0, 0, 0, 0)') ||
          (n.className || '').toString().toLowerCase().indexOf('card') >= 0
        );
        if (looksCard) return n;
      } catch (e) {}
      n = n.parentElement;
    }
    return el;
  }

  function findCard(label) {
    var nodes = Array.prototype.slice.call(document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span,section,article'));
    for (var i = 0; i < nodes.length; i++) {
      if (!hasText(nodes[i], label)) continue;
      var card = nearestCard(nodes[i]);
      if (!card) continue;
      var r = card.getBoundingClientRect();
      if (r.width > 180 && r.height > 100) return card;
    }
    return null;
  }

  function tag() {
    document.documentElement.classList.add('copycat-visual-v3');

    var portfolio = findCard('portfolio allocation');
    var exposure = findCard('long vs short exposure');
    var signal = findCard('asset signal board');
    var index = findCard('copycat index');
    var pressure = findCard('recent buyer') || findCard('buyer / seller') || findCard('buyer/seller pressure');

    if (portfolio) portfolio.classList.add('copycat-v3-portfolio');
    if (exposure) exposure.classList.add('copycat-v3-exposure');
    if (signal) signal.classList.add('copycat-v3-signal');
    if (index) index.classList.add('copycat-v3-index');
    if (pressure) pressure.classList.add('copycat-v3-pressure');

    [portfolio, exposure, signal, index, pressure].forEach(function (card) {
      if (!card) return;
      card.style.webkitMaskImage = 'none';
      card.style.maskImage = 'none';
      card.style.clipPath = 'none';
      card.style.maxHeight = 'none';
      card.style.overflow = 'visible';
      card.style.opacity = '1';

      Array.prototype.slice.call(card.querySelectorAll('*')).forEach(function (el) {
        el.style.webkitMaskImage = 'none';
        el.style.maskImage = 'none';
        el.style.clipPath = 'none';
      });
    });

    var middle = document.getElementById('copycat-visual-middle-row');
    var bottom = document.getElementById('copycat-visual-bottom-row');
    if (middle) middle.classList.add('copycat-v3-row');
    if (bottom) bottom.classList.add('copycat-v3-row');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tag);
  else tag();

  setTimeout(tag, 300);
  setTimeout(tag, 1000);
  setTimeout(tag, 2500);
  setTimeout(tag, 5000);

  try {
    new MutationObserver(function () { tag(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
