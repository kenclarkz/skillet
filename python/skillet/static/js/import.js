// Import form: fetch /api/import, then fill the editable recipe draft form.
(function () {
  var form = document.getElementById('import-form');
  if (!form) return;
  var statusEl = document.getElementById('import-status');
  var result = document.getElementById('import-result');
  var emptyNote = document.getElementById('import-empty-note');
  var methodNote = document.getElementById('import-method-note');
  var submit = document.getElementById('import-submit');

  function ingredientLines(ingredients) {
    return (ingredients || []).map(function (ing) {
      var parts = [];
      if (ing.qty) parts.push(String(ing.qty));
      if (ing.unit) parts.push(ing.unit);
      if (ing.name) parts.push(ing.name);
      var line = parts.join(' ');
      if (ing.note) {
        if (/^\(.*\)$/.test(ing.note)) line = line + ' ' + ing.note;
        else line = line + ', ' + ing.note;
      }
      return line;
    }).join('\n');
  }

  function fillDraft(draft) {
    function set(id, value) {
      var el = document.getElementById(id);
      if (el) el.value = value == null ? '' : String(value);
    }
    set('title', draft.title);
    set('description', draft.description || '');
    set('ingredients_text', ingredientLines(draft.ingredients));
    set('instructions_text', (draft.instructions || []).join('\n'));
    set('tags', (draft.tags || []).join(', '));
    set('prep_minutes', draft.prep_minutes == null ? '' : draft.prep_minutes);
    set('cook_minutes', draft.cook_minutes == null ? '' : draft.cook_minutes);
    set('servings', draft.servings || 4);
    set('source_url', draft.source_url || '');
    var photoPath = draft.photo_url || '';
    var pathInput = document.getElementById('photo_path');
    if (pathInput) pathInput.value = photoPath;
    var preview = document.getElementById('photo-preview');
    var previewImg = document.getElementById('photo-preview-img');
    if (preview && previewImg) {
      if (photoPath) {
        previewImg.src = photoPath;
        preview.hidden = false;
      } else {
        preview.hidden = true;
        previewImg.removeAttribute('src');
      }
    }
    result.hidden = false;
    if (emptyNote) emptyNote.hidden = true;
    if (methodNote) {
      methodNote.hidden = false;
      methodNote.textContent = 'Imported via ' + draft.method + ' — review everything before saving.';
    }
    document.getElementById('title').focus();
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var url = document.getElementById('import-url').value.trim();
    statusEl.textContent = 'Fetching the recipe…';
    statusEl.style.color = '';
    submit.disabled = true;
    fetch('/api/import', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': window.SKILLET_CSRF || (document.querySelector('input[name="_csrf"]') || {}).value || ''
      },
      body: JSON.stringify({ url: url })
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try {
          data = JSON.parse(text);
        } catch (parseErr) {
          data = null;
        }
        return { ok: res.ok, status: res.status, data: data };
      });
    }).then(function (r) {
      submit.disabled = false;
      if (r.data && r.data.draft && (r.ok || r.status === 422)) {
        fillDraft(r.data.draft);
        statusEl.textContent = r.ok ? 'Recipe found — check the draft below.' : (r.data.error || 'Partial match — review carefully.');
        statusEl.style.color = r.ok ? '' : '#8a6212';
      } else if (r.status === 401) {
        statusEl.textContent = 'Please sign in again to import recipes.';
        statusEl.style.color = '#a1301f';
      } else if (r.data && r.data.error) {
        statusEl.textContent = r.data.error;
        statusEl.style.color = '#a1301f';
      } else if (r.status >= 500) {
        statusEl.textContent = 'The importer hit an unexpected error. Please try again in a moment.';
        statusEl.style.color = '#a1301f';
      } else {
        statusEl.textContent = 'Import failed — check your connection and try again.';
        statusEl.style.color = '#a1301f';
      }
    }).catch(function () {
      submit.disabled = false;
      statusEl.textContent = 'Import failed — check your connection and try again.';
      statusEl.style.color = '#a1301f';
    });
  });
})();
