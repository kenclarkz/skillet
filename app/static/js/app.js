// Minimal interactivity: no-op beyond placeholder; kept for future enhancements.
document.addEventListener('DOMContentLoaded', function () {
  // auto-dismiss alerts after 5s
  document.querySelectorAll('.alert').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 5000);
  });
});

// Step builder: add / remove step rows with optional per-step photos.
document.addEventListener('DOMContentLoaded', function () {
  var list = document.getElementById('step-list');
  var addBtn = document.getElementById('add-step');
  if (!list || !addBtn) return;

  function renumber() {
    list.querySelectorAll('.step-number').forEach(function (el, i) {
      el.textContent = i + 1;
    });
  }

  addBtn.addEventListener('click', function () {
    var row = document.createElement('div');
    row.className = 'step-row';
    row.innerHTML =
      '<span class="step-number"></span>' +
      '<div class="step-fields">' +
      '<textarea name="step_text" class="textarea step-text" rows="2" placeholder="What happens in this step"></textarea>' +
      '<div class="step-photo-controls">' +
      '<input type="file" name="step_photo" class="input step-file" accept="image/*">' +
      '<input type="hidden" name="step_id" value="">' +
      '<input type="hidden" name="step_photo_url" value="">' +
      '</div></div>' +
      '<button type="button" class="btn btn-secondary btn-small remove-step" title="Remove this step">&times;</button>';
    list.appendChild(row);
    renumber();
    row.querySelector('.step-text').focus();
  });

  list.addEventListener('click', function (e) {
    var btn = e.target.closest('.remove-step');
    if (!btn) return;
    var rows = list.querySelectorAll('.step-row');
    if (rows.length > 1) {
      btn.closest('.step-row').remove();
    } else {
      var row = btn.closest('.step-row');
      row.querySelector('.step-text').value = '';
      var file = row.querySelector('.step-file');
      if (file) file.value = '';
      var thumb = row.querySelector('.step-thumb');
      if (thumb) thumb.remove();
      var drop = row.querySelector('.step-drop');
      if (drop) drop.remove();
    }
    renumber();
  });
});
