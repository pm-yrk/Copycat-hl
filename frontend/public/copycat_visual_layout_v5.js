
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

  function tagCard(card, cls) {
    if (!card) return;
    card.classList.add('copycat-v5-card', cls);
    card.classList.remove(
      'copycat-v2-portfolio','copycat-v2-exposure','copycat-v2-signal','copycat-v2-index','copycat-v2-pressure',
      'copycat-v3-portfolio','copycat-v3-exposure','copycat-v3-signal','copycat-v3-index','copycat-v3-pressure',
      'copycat-v4-portfolio','copycat-v4-exposure','copycat-v4-signal','copycat-v4-index','copycat-v4-pressure'
    );
    card.style.webkitMaskImage = 'none';
    card.style.maskImage = 'none';
    card.style.clipPath = 'none';
    card.style.position = 'relative';
    card.style.zIndex = '1';
  }

  function tag() {
    document.documentElement.classList.add('copycat-visual-v5');
    document.documentElement.classList.remove('copycat-visual-v2','copycat-visual-v3','copycat-visual-v4');

    tagCard(findCard('portfolio allocation'), 'copycat-v5-portfolio');
    tagCard(findCard('long vs short exposure'), 'copycat-v5-exposure');
    tagCard(findCard('asset signal board'), 'copycat-v5-signal');
    tagCard(findCard('copycat index'), 'copycat-v5-index');
    tagCard(findCard('recent buyer') || findCard('buyer / seller') || findCard('buyer/seller pressure'), 'copycat-v5-pressure');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tag);
  else tag();

  setTimeout(tag, 300);
  setTimeout(tag, 1000);
  setTimeout(tag, 2500);
  try {
    new MutationObserver(function () { tag(); }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
