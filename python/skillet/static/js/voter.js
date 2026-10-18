// Guest voter: loads the ballot via the server API and casts votes.
(function () {
  var root = document.getElementById('voter');
  if (!root) return;
  var token = root.getAttribute('data-token');
  var statusEl = document.getElementById('ballot-status');
  var recipesEl = document.getElementById('ballot-recipes');
  var headerEl = document.getElementById('ballot-cookbook');
  var nameInput = document.getElementById('voter-name');

  var KEY_STORAGE = 'skillet_guest_key';
  var NAME_STORAGE = 'skillet_guest_name';

  function voterKey() {
    var key = null;
    try { key = localStorage.getItem(KEY_STORAGE); } catch (e) { /* private mode */ }
    if (!key) {
      if (window.crypto && crypto.randomUUID) key = 'guest:' + crypto.randomUUID();
      else key = 'guest:' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      try { localStorage.setItem(KEY_STORAGE, key); } catch (e) { /* ignore */ }
    }
    return key;
  }

  function savedName() {
    try { return localStorage.getItem(NAME_STORAGE) || ''; } catch (e) { return ''; }
  }

  var initialName = savedName();
  if (initialName) nameInput.value = initialName;

  nameInput.addEventListener('blur', function () {
    try { localStorage.setItem(NAME_STORAGE, nameInput.value.trim()); } catch (e) { /* ignore */ }
  });

  function esc(value) {
    var div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function photoUrl(recipe) {
    if (recipe.photo_url && /^https?:\/\//.test(recipe.photo_url)) return recipe.photo_url;
    if (!recipe.photo_path) return null;
    if (/^https?:\/\//.test(recipe.photo_path)) return recipe.photo_path;
    var base = (window.SKILLET_MEDIA_BASE || '/media').replace(/\/$/, '');
    return base + '/' + recipe.photo_path.replace(/^\//, '');
  }

  function renderBallot(ballot) {
    recipesEl.innerHTML = '';
    if (!ballot || !ballot.plan) {
      statusEl.textContent = 'This voting link is no longer valid.';
      return;
    }
    statusEl.textContent = '';
    headerEl.hidden = false;
    document.getElementById('ballot-cookbook-name').textContent = (ballot.cookbook && ballot.cookbook.name) || 'Vote';
    var planTitle = (ballot.plan.title || ('Week of ' + ballot.plan.week_start));
    document.getElementById('ballot-plan-title').textContent = planTitle +
      (ballot.plan.status === 'closed' ? ' — voting closed' : '');

    var recipes = ballot.recipes || [];
    if (!recipes.length) {
      recipesEl.innerHTML = '<div class="empty-state"><h3>Nothing to vote on yet</h3>' +
        '<p class="muted">Check back when the menu is up.</p></div>';
      return;
    }

    var myVotes = ballot.my_votes || {};
    var tallies = ballot.tallies || {};
    recipes.sort(function (a, b) {
      return ((tallies[b.id] || {}).up || 0) - ((tallies[a.id] || {}).up || 0);
    });

    recipes.forEach(function (recipe) {
      var tally = tallies[recipe.id] || { up: 0, down: 0, names: [] };
      var mine = myVotes[recipe.id] || 0;
      var photo = photoUrl(recipe);
      var card = document.createElement('div');
      card.className = 'card card-pad';
      card.innerHTML =
        '<div class="vote-card">' +
        '<div class="thumb" style="background:var(--sand);display:flex;align-items:center;justify-content:center">' +
        (photo ? '<img src="' + esc(photo) + '" alt="">' : '🍽️') +
        '</div>' +
        '<div style="flex:1;min-width:0">' +
        '<strong>' + esc(recipe.title) + '</strong>' +
        '<div class="voter-names">👍 ' + tally.up + ' · 👎 ' + tally.down +
        (tally.names && tally.names.length
          ? ' — ' + esc(tally.names.slice(0, 5).join(', ')) +
            (tally.names.length > 5 ? ' +' + (tally.names.length - 5) + ' more' : '')
          : '') +
        '</div>' +
        '<div class="vote-buttons" style="margin-top:0.4rem">' +
        '<button class="vote-btn ' + (mine > 0 ? 'on-up' : '') + '" data-value="1" title="Vote up">👍</button>' +
        '<button class="vote-btn ' + (mine < 0 ? 'on-down' : '') + '" data-value="-1" title="Vote down">👎</button>' +
        '</div></div></div>';

      card.querySelectorAll('.vote-btn').forEach(function (button) {
        button.addEventListener('click', function () {
          var name = nameInput.value.trim();
          if (!name) {
            statusEl.textContent = 'Add your name before voting.';
            nameInput.focus();
            return;
          }
          try { localStorage.setItem(NAME_STORAGE, name); } catch (e) { /* ignore */ }
          var requested = parseInt(button.getAttribute('data-value'), 10);
          var current = myVotes[recipe.id] || 0;
          var value = current === requested ? 0 : requested;
          statusEl.textContent = 'Saving…';
          fetch('/api/vote/cast', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRF-Token': window.SKILLET_CSRF || ''
            },
            body: JSON.stringify({
              plan_id: ballot.plan.id,
              recipe_id: recipe.id,
              voter_key: voterKey(),
              voter_name: name,
              value: value,
              invite_token: token
            })
          }).then(function (res) {
            return res.json().then(function (data) { return { ok: res.ok, data: data }; });
          }).then(function (r) {
            if (!r.ok) {
              statusEl.textContent = (r.data && r.data.error) || 'Could not save your vote.';
              return;
            }
            loadBallot();
          }).catch(function () {
            statusEl.textContent = 'Could not save your vote — try again.';
          });
        });
      });
      recipesEl.appendChild(card);
    });
  }

  function loadBallot() {
    fetch('/api/vote/ballot?token=' + encodeURIComponent(token) +
          '&voter_key=' + encodeURIComponent(voterKey()))
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (r) {
        if (!r.ok) {
          statusEl.textContent = (r.data && r.data.error) || 'This voting link is no longer valid.';
          return;
        }
        renderBallot(r.data.ballot);
      })
      .catch(function () {
        statusEl.textContent = 'Could not load the ballot — check your connection.';
      });
  }

  loadBallot();
})();
