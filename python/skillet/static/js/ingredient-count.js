// Live "N ingredients parsed" counter on recipe forms.
(function () {
  var textarea = document.getElementById('ingredients_text');
  var counter = document.getElementById('ingredient-count');
  if (!textarea || !counter) return;
  function update() {
    var count = textarea.value.split('\n').filter(function (line) { return line.trim(); }).length;
    counter.textContent = count ? count + ' ingredient' + (count === 1 ? '' : 's') + ' — edit any line freely.' : '';
  }
  textarea.addEventListener('input', update);
  update();
})();
