// Shop panel: POST /api/shop and render honest results.
(function () {
  var panel = document.getElementById('shop-panel');
  if (!panel) return;
  var planId = panel.getAttribute('data-plan');
  var statusEl = document.getElementById('shop-status');
  var resultsEl = document.getElementById('shop-results');
  var runBtn = document.getElementById('shop-run');

  function esc(value) {
    var div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function renderResult(result) {
    resultsEl.hidden = false;
    var tone = result.status === 'created' ? 'badge badge-olive' :
      result.status === 'error' ? 'badge badge-terracotta' : 'badge badge-honey';
    var html = '<div class="spread" style="margin-bottom:0.6rem">' +
      '<span class="' + tone + '">' + esc(result.status) + '</span>' +
      (result.status === 'created' && result.url
        ? '<a class="btn btn-primary btn-sm" href="' + esc(result.url) + '" target="_blank" rel="noopener">Open cart ↗</a>'
        : '') +
      '</div>';
    html += '<p class="small">' + esc(result.message || '') + '</p>';
    html += '<div style="margin-top:0.5rem">';
    (result.items || []).forEach(function (mapped) {
      var product = mapped.product;
      html += '<div class="shop-item">' +
        '<input type="checkbox" aria-label="Select item">' +
        '<div style="flex:1;min-width:0">' +
        '<strong>' + esc(mapped.display || mapped.item.name) + '</strong>' +
        (product
          ? '<div class="small">' + esc(product.title) +
            (product.priceText ? ' — ' + esc(product.priceText) : '') + '</div>' +
            '<div class="confidence">' + Math.round((mapped.confidence || 0) * 100) + '% match</div>' +
            '<a class="small" href="' + esc(product.url) + '" target="_blank" rel="noopener">Open product ↗</a>'
          : '<div class="small muted">' +
            '<a href="' + esc(mapped.searchUrl) + '" target="_blank" rel="noopener">Search for “' + esc(mapped.query) + '” ↗</a>' +
            '</div>') +
        '</div></div>';
    });
    html += '</div>';
    html += '<button class="btn btn-ghost btn-sm" type="button" id="shop-copy" style="margin-top:0.6rem">Copy list</button>';
    resultsEl.innerHTML = html;

    var copyBtn = document.getElementById('shop-copy');
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        var text = (result.items || []).map(function (m) { return '- ' + (m.display || m.item.name); }).join('\n');
        if (navigator.clipboard) navigator.clipboard.writeText(text);
        copyBtn.textContent = 'Copied!';
        setTimeout(function () { copyBtn.textContent = 'Copy list'; }, 2000);
      });
    }
  }

  if (runBtn) {
    runBtn.addEventListener('click', function () {
      var selected = panel.querySelector('.retailer-radio:checked');
      var retailer = selected ? selected.value : 'walmart';
      statusEl.textContent = 'Matching products…';
      statusEl.style.color = '';
      runBtn.disabled = true;
      fetch('/api/shop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': window.SKILLET_CSRF || ''
        },
        body: JSON.stringify({ retailer: retailer, planId: planId })
      }).then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      }).then(function (r) {
        runBtn.disabled = false;
        if (!r.ok) {
          statusEl.textContent = (r.data && r.data.error) || 'Shopping failed.';
          statusEl.style.color = '#a1301f';
          resultsEl.hidden = true;
          return;
        }
        statusEl.textContent = '';
        renderResult(r.data.result);
      }).catch(function () {
        runBtn.disabled = false;
        statusEl.textContent = 'Shopping failed — check your connection.';
        statusEl.style.color = '#a1301f';
      });
    });
  }
})();
