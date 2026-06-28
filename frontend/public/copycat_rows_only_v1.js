
(function () {
  function cleanText(el) {
    return (el && el.textContent || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function hasText(el, label) {
    return cleanText(el).indexOf(label.toLowerCase()) >= 0;
  }

  function nearestCard(el) {
    var n = el;
    while (n && n !== document.body) {
      try {
        var r = n.getBoundingClientRect();
        var cs = window.getComputedStyle(n);
        var className = (n.className || "").toString().toLowerCase();
        var looksLikeCard =
          r.width > 180 &&
          r.height > 90 &&
          (
            (cs.borderRadius && cs.borderRadius !== "0px") ||
            className.indexOf("card") >= 0 ||
            className.indexOf("panel") >= 0
          );

        if (looksLikeCard) return n;
      } catch (e) {}

      n = n.parentElement;
    }
    return null;
  }

  function findCard(label) {
    var nodes = Array.prototype.slice.call(
      document.querySelectorAll("h1,h2,h3,h4,h5,h6,div,span,section,article,p")
    );

    for (var i = 0; i < nodes.length; i++) {
      if (!hasText(nodes[i], label)) continue;
      var card = nearestCard(nodes[i]);
      if (card) return card;
    }

    return null;
  }

  function createRow(id, className) {
    var row = document.getElementById(id);
    if (!row) {
      row = document.createElement("div");
      row.id = id;
      row.className = "copycat-rows-only-row " + className;
    }
    return row;
  }

  function moveCardsIntoRow(row, cards, insertBeforeNode) {
    var found = cards.filter(Boolean);
    if (!found.length) return;

    if (!row.parentElement) {
      insertBeforeNode.parentElement.insertBefore(row, insertBeforeNode);
    }

    found.forEach(function (card) {
      if (!card) return;
      card.classList.add("copycat-rows-only-card");
      row.appendChild(card);
    });
  }

  function run() {
    document.documentElement.classList.add("copycat-rows-only-v1");

    var portfolio = findCard("portfolio allocation");
    var exposure = findCard("long vs short exposure");
    var signal = findCard("asset signal board");

    var index = findCard("copycat index");
    var pressure =
      findCard("recent buyer / seller pressure") ||
      findCard("recent buyer") ||
      findCard("buyer / seller pressure") ||
      findCard("buyer/seller pressure");

    if (portfolio && exposure && signal) {
      var middleRow = createRow("copycat-rows-only-middle", "copycat-rows-only-middle");
      moveCardsIntoRow(middleRow, [portfolio, exposure, signal], portfolio);
    }

    if (index && pressure) {
      var bottomRow = createRow("copycat-rows-only-bottom", "copycat-rows-only-bottom");
      var middle = document.getElementById("copycat-rows-only-middle");

      if (!bottomRow.parentElement) {
        if (middle && middle.parentElement) {
          middle.parentElement.insertBefore(bottomRow, middle.nextSibling);
        } else {
          index.parentElement.insertBefore(bottomRow, index);
        }
      }

      [index, pressure].forEach(function (card) {
        card.classList.add("copycat-rows-only-card");
        bottomRow.appendChild(card);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }

  setTimeout(run, 300);
  setTimeout(run, 1200);
})();
