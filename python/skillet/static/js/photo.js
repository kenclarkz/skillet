// Photo upload: browser → Flask → local disk (served back via /media/...).
(function () {
  var field = document.getElementById('photo-field');
  if (!field) return;
  var fileInput = document.getElementById('photo_file');
  var pathInput = document.getElementById('photo_path');
  var preview = document.getElementById('photo-preview');
  var previewImg = document.getElementById('photo-preview-img');
  var status = document.getElementById('photo-status');
  var cookbookId = field.getAttribute('data-cookbook');

  // Show an initial image (recipe photo or remote import URL in photo_path).
  var initialUrl = field.getAttribute('data-initial-url');
  var initialPath = field.getAttribute('data-initial-path');
  if (initialUrl) {
    previewImg.src = initialUrl;
    preview.hidden = false;
  } else if (initialPath && /^https?:\/\//.test(initialPath)) {
    previewImg.src = initialPath;
    preview.hidden = false;
  }

  if (!fileInput) return;
  fileInput.addEventListener('change', function () {
    var file = fileInput.files && fileInput.files[0];
    if (!file) return;
    status.textContent = 'Uploading…';
    var body = new FormData();
    body.append('cookbook_id', cookbookId);
    body.append('file', file);
    fetch('/api/photos', {
      method: 'POST',
      headers: { 'X-CSRF-Token': window.SKILLET_CSRF || document.querySelector('input[name="_csrf"]').value },
      body: body
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (r) {
      if (!r.ok) {
        status.textContent = r.data.error || 'Upload failed.';
        return;
      }
      pathInput.value = r.data.path;
      if (r.data.url) {
        previewImg.src = r.data.url;
        preview.hidden = false;
      }
      status.textContent = 'Photo uploaded ✓';
    }).catch(function () {
      status.textContent = 'Upload failed — check your connection and try again.';
    });
  });
})();
