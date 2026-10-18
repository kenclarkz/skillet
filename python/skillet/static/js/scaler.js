// Servings scaler for recipe detail pages — mirrors formatQuantity/formatNumber.
(function () {
  var list = document.getElementById('ingredient-list');
  if (!list || !window.SKILLET_INGREDIENTS) return;
  var base = window.SKILLET_BASE_SERVINGS || 4;
  var servings = base;
  var label = document.getElementById('servings-label');

  var FRACTIONS = [
    [1/8, '1/8'], [1/6, '1/6'], [1/5, '1/5'], [1/4, '1/4'],
    [1/3, '1/3'], [3/8, '3/8'], [1/2, '1/2'], [5/8, '5/8'],
    [2/3, '2/3'], [3/4, '3/4'], [5/6, '5/6'], [7/8, '7/8']
  ];

  function formatNumber(n) {
    if (Number.isInteger(n)) return String(n);
    var whole = Math.floor(n);
    var frac = n - whole;
    for (var i = 0; i < FRACTIONS.length; i++) {
      if (Math.abs(frac - FRACTIONS[i][0]) < 0.025) {
        return whole > 0 ? whole + ' ' + FRACTIONS[i][1] : FRACTIONS[i][1];
      }
    }
    return String(Math.round(n * 100) / 100);
  }

  function toNumber(qty) {
    if (!qty) return null;
    var n = parseFloat(String(qty).replace(/,/g, '.'));
    return Number.isFinite(n) ? n : null;
  }

  function formatQuantity(ing, scale) {
    var num = toNumber(ing.qty);
    var unit = ing.unit || '';
    if (num === null) {
      return (ing.qty ? String(ing.qty) : '') + (unit ? ' ' + unit : '');
    }
    var q = formatNumber(num * scale);
    return unit ? q + ' ' + unit : q;
  }

  function render() {
    label.textContent = servings;
    var scale = servings / base;
    list.innerHTML = '';
    window.SKILLET_INGREDIENTS.forEach(function (ing) {
      var row = document.createElement('div');
      row.className = 'ingredient-row';
      var qty = document.createElement('span');
      qty.className = 'ingredient-qty';
      qty.textContent = formatQuantity(ing, scale);
      var name = document.createElement('span');
      name.textContent = ing.name || '';
      if (ing.note) {
        var note = document.createElement('span');
        note.className = 'muted';
        note.textContent = ', ' + ing.note;
        name.appendChild(note);
      }
      row.appendChild(qty);
      row.appendChild(name);
      list.appendChild(row);
    });
  }

  document.getElementById('scale-up').addEventListener('click', function () {
    servings = Math.min(100, servings + 1);
    render();
  });
  document.getElementById('scale-down').addEventListener('click', function () {
    servings = Math.max(1, servings - 1);
    render();
  });
  document.getElementById('scale-reset').addEventListener('click', function () {
    servings = base;
    render();
  });
  render();
})();
