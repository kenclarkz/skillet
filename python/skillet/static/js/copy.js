// Copy-to-clipboard + Web Share helpers for .js-copy / .js-share controls.
(function () {
  function flash(button, label) {
    var original = button.textContent;
    button.textContent = label;
    setTimeout(function () { button.textContent = original; }, 2000);
  }

  function copyText(text, button) {
    function fallback() {
      var area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy'); } catch (e) { /* ignore */ }
      document.body.removeChild(area);
      flash(button, 'Copied!');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { flash(button, 'Copied!'); }, fallback);
    } else {
      fallback();
    }
  }

  document.addEventListener('click', function (event) {
    var copyBtn = event.target.closest('.js-copy');
    if (copyBtn) {
      var card = copyBtn.closest('.copy-input, .card, form, div');
      var input = (card && card.querySelector('.js-copy-input')) ||
        document.querySelector('.js-copy-input');
      if (input) copyText(input.value, copyBtn);
      return;
    }
    var shareBtn = event.target.closest('.js-share');
    if (shareBtn) {
      var url = shareBtn.getAttribute('data-url') ||
        (shareBtn.closest('.copy-input, .card, div') || document).querySelector('.js-copy-input');
      if (url && typeof url === 'object') url = url.value;
      if (!url) return;
      if (navigator.share) {
        navigator.share({ url: url, title: 'Vote on meals' }).catch(function () {
          var input = document.querySelector('.js-copy-input');
          if (input) copyText(url, shareBtn);
        });
      } else {
        var input = document.querySelector('.js-copy-input');
        if (input) copyText(url, shareBtn);
      }
    }
  });
})();
