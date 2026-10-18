// Grocery list interactivity: progress, filters, clipboard, CSV.
(function () {
  var root = document.getElementById('grocery-editor');
  if (!root) return;
  var planId = root.getAttribute('data-plan');
  var items = Array.prototype.slice.call(root.querySelectorAll('[data-item]'));
  var filter = 'all';

  function isChecked(el) { return el.getAttribute('data-checked') === 'true'; }
  function isExcluded(el) { return el.getAttribute('data-excluded') === 'true'; }

  function formatQuantity(item) {
    var qty = item.getAttribute('data-qty');
    var unit = item.getAttribute('data-unit') || '';
    var name = item.getAttribute('data-name') || '';
    if (qty === '' || qty === null) {
      return (unit ? unit + ' ' : '') + name;
    }
    var num = parseFloat(qty);
    var q = Number.isInteger(num) ? String(num) : String(Math.round(num * 100) / 100);
    var needsPlural = num !== 1 && unit && !/s$/.test(unit) &&
      ['lb', 'oz', 'fl oz', 'tbsp', 'tsp'].indexOf(unit) === -1;
    return (q + ' ' + unit + (needsPlural ? 's' : '') + ' ' + name).trim();
  }

  function updateProgress() {
    var active = items.filter(function (el) { return !isExcluded(el); });
    var done = active.filter(isChecked);
    var doneEl = document.getElementById('grocery-done');
    var activeEl = document.getElementById('grocery-active');
    var bar = document.getElementById('grocery-progress');
    if (doneEl) doneEl.textContent = done.length;
    if (activeEl) activeEl.textContent = active.length;
    if (bar) bar.style.width = active.length ? Math.round((done.length / active.length) * 100) + '%' : '0%';
  }

  function applyFilter() {
    items.forEach(function (el) {
      var show = true;
      if (filter === 'todo') show = !isExcluded(el) && !isChecked(el);
      else if (filter === 'done') show = !isExcluded(el) && isChecked(el);
      el.style.display = show ? '' : 'none';
    });
  }

  items.forEach(function (el) {
    var checkbox = el.querySelector('.js-toggle input[type="checkbox"]');
    if (checkbox) {
      checkbox.addEventListener('change', function () {
        var form = checkbox.closest('form');
        if (form) form.submit();
      });
    }
  });

  root.querySelectorAll('.filter-tabs button').forEach(function (button) {
    button.addEventListener('click', function () {
      filter = button.getAttribute('data-filter');
      root.querySelectorAll('.filter-tabs button').forEach(function (b) { b.classList.remove('active'); });
      button.classList.add('active');
      applyFilter();
    });
  });

  var copyBtn = document.getElementById('grocery-copy');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var lines = items
        .filter(function (el) { return !isExcluded(el); })
        .map(function (el) { return '☐ ' + formatQuantity(el); });
      var text = lines.join('\n');
      function flash(label) {
        var original = copyBtn.textContent;
        copyBtn.textContent = label;
        setTimeout(function () { copyBtn.textContent = original; }, 2000);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { flash('Copied!'); });
      } else {
        flash('Copy failed');
      }
    });
  }

  var csvBtn = document.getElementById('grocery-csv');
  if (csvBtn) {
    csvBtn.addEventListener('click', function () {
      function esc(value) { return '"' + String(value).replace(/"/g, '""') + '"'; }
      var rows = [['item', 'quantity', 'unit', 'in pantry']];
      items.forEach(function (el) {
        rows.push([
          el.getAttribute('data-name') || '',
          el.getAttribute('data-qty') || '',
          el.getAttribute('data-unit') || '',
          el.getAttribute('data-excluded') === 'true' && /pantry/i.test(el.textContent) ? 'yes' : 'no'
        ]);
      });
      var csv = rows.map(function (r) { return r.map(esc).join(','); }).join('\r\n');
      var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'skillet-grocery-list.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
    });
  }

  updateProgress();
  applyFilter();
})();
