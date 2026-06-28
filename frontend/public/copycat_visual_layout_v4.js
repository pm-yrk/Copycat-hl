
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

  function firstLargeChart(card) {
    if (!card) return null;
    var charts = Array.prototype.slice.call(card.querySelectorAll('svg,canvas,[class*="recharts-wrapper"],[class*="chart"]'));
    var best = null, bestArea = 0;
    charts.forEach(function (el) {
      try {
        var r = el.getBoundingClientRect();
        var area = r.width * r.height;
        if (area > bestArea && r.width > 60 && r.height > 60) {
          best = el;
          bestArea = area;
        }
      } catch (e) {}
    });
    return best;
  }

  function wrapScroll(card) {
    if (!card || card.querySelector(':scope > .copycat-v4-scroll-inner')) return;
    var children = Array.prototype.slice.call(card.children);
    if (children.length <= 1) return;
    var titleCount = Math.min(1, children.length);
    var wrap = document.createElement('div');
    wrap.className = 'copycat-v4-scroll-inner';
    for (var i = titleCount; i < children.length; i++) {
      wrap.appendChild(children[i]);
    }
    card.appendChild(wrap);
  }

  function setupPortfolio(card) {
    if (!card) return;
    var chart = firstLargeChart(card);
    if (chart && !chart.closest('.copycat-v4-chart-box')) {
      var chartBox = document.createElement('div');
      chartBox.className = 'copycat-v4-chart-box';
      var parent = chart.parentElement;
      parent.insertBefore(chartBox, chart);
      chartBox.appendChild(chart);
    }

    if (!card.querySelector('.copycat-v4-legend-box')) {
      var chartBoxExisting = card.querySelector('.copycat-v4-chart-box');
      var legendBox = document.createElement('div');
      legendBox.className = 'copycat-v4-legend-box';

      var candidates = Array.prototype.slice.call(card.querySelectorAll('div,li,span'));
      candidates.forEach(function (el) {
        if (legendBox.contains(el)) return;
        if (chartBoxExisting && chartBoxExisting.contains(el)) return;
        var t = (el.textContent || '').trim();
        if (!t) return;
        if (t.length > 38) return;
        if (/(long|short|mixed)\\s*\\d+%/i.test(t) || /\\b[A-Z0-9]{2,8}\\b/.test(t)) {
          try {
            var r = el.getBoundingClientRect();
            if (r.width > 20 && r.height > 8 && r.height < 42) {
              legendBox.appendChild(el);
            }
          } catch (e) {}
        }
      });

      if (legendBox.children.length) {
        card.appendChild(legendBox);
      }
    }
  }

  function tag() {
    document.documentElement.classList.add('copycat-visual-v4');

    var portfolio = findCard('portfolio allocation');
    var exposure = findCard('long vs short exposure');
    var signal = findCard('asset signal board');
    var index = findCard('copycat index');
    var pressure = findCard('recent buyer') || findCard('buyer / seller') || findCard('buyer/seller pressure');

    if (portfolio) portfolio.classList.add('copycat-v4-portfolio');
    if (exposure) exposure.classList.add('copycat-v4-exposure');
    if (signal) signal.classList.add('copycat-v4-signal');
    if (index) index.classList.add('copycat-v4-index');
    if (pressure) pressure.classList.add('copycat-v4-pressure');

    [portfolio, exposure, signal, index, pressure].forEach(function (card) {
      if (!card) return;
      card.style.webkitMaskImage = 'none';
      card.style.maskImage = 'none';
      card.style.clipPath = 'none';
      card.style.opacity = '1';
    });

    setupPortfolio(portfolio);
    wrapScroll(exposure);
    wrapScroll(signal);
    wrapScroll(index);
    wrapScroll(pressure);

    var middle = document.getElementById('copycat-visual-middle-row');
    var bottom = document.getElementById('copycat-visual-bottom-row');
    if (middle) middle.classList.add('copycat-v4-row');
    if (bottom) bottom.classList.add('copycat-v4-row');
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
