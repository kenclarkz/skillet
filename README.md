# Skillet — Flask Edition

A digital cookbook for families: recipes with photos, a weekly meal planner, and an automatic shopping list that merges ingredients and skips pantry staples. This is a full rebuild of the original Next.js + Supabase app as a single Python app that runs anywhere — no Node, no external databases.

- **Stack:** Python 3, Flask, SQLite, Flask-Login, Flask-WTF (CSRF), Werkzeug password hashing, Jinja2 templates
- **Deploy target:** [PythonAnywhere](https://www.pythonanywhere.com/) (also runs locally or on any WSGI host)

## Features

- User registration, login, logout, secure session cookies (HttpOnly, SameSite=Lax)
- Personal recipe book per user — recipes are private to their owner
- Add / edit / delete / view recipes with photo uploads
- Ingredients with quantities + units, instructions, tags, prep/cook times, servings
- Horizontal scrollable recipe-card carousel with photos (original Skillet look)
- Weekly meal planner: assign recipes to days of the week
- Automatic grocery list from planned meals: quantities merge across recipes (with unit conversion), pantry staples are flagged
- Responsive design (mobile + desktop) with the original cream / sand / terracotta / olive branding
- CSRF protection on every form; hashed passwords; validated and extension-checked image uploads

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit SECRET_KEY
flask db-init                 # creates instance/skillet.db
flask run                     # http://127.0.0.1:5000
```

Or `python app.py` for the built-in server (fine for local use).

## Environment variables

All optional (sensible defaults are used), but set `SECRET_KEY` in production.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key-change-me` | Session/CSRF signing key — must be a long random string in production |
| `DATABASE_PATH` | `<project>/instance/skillet.db` | Absolute path to the SQLite file |
| `UPLOAD_FOLDER` | `<project>/app/uploads` | Where uploaded photos are stored |
| `MAX_CONTENT_LENGTH` | `5242880` (5 MiB) | Max upload size |
| `PASSWORD_HASH_METHOD` | `pbkdf2:sha256:600000` | Werkzeug password hash method |

## PythonAnywhere deployment

### 1. Create the project

1. Sign up at pythonanywhere.com (free "Hacker" tier is enough for trying it).
2. Upload this project to your home directory, e.g. `/home/YOUR_USERNAME/skillet-flask`
   (the Files tab or `git clone` both work).
3. Open a **Bash console** in the project folder.

### 2. Virtualenv and dependencies

```bash
cd ~/skillet-flask
mkvirtualenv --python=python3.12 skillet
pip install -r requirements.txt
```

(The Web tab's "Virtualenv" field should also say `skillet`.)

### 3. Configure secrets and paths

On the **Web** tab, add **Environment variables**:

- `SECRET_KEY` = a long random string, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`
- (optional) `UPLOAD_FOLDER` = `/home/YOUR_USERNAME/skillet-flask/app/uploads`

### 4. WSGI configuration file

On the **Web** tab, open the **WSGI configuration file** link and make it match
`wsgi.py` in this repo — set `path` to your project folder:

```python
import sys
path = '/home/YOUR_USERNAME/skillet-flask'
if path not in sys.path:
    sys.path.insert(0, path)

from app import create_app
application = create_app()
```

### 5. Initialize the database

In the Bash console (with the virtualenv active):

```bash
cd ~/skillet-flask
flask db-init
```

This creates `instance/skillet.db`. Both `instance/` (database) and `app/uploads/`
(photos) live inside your project folder, so they **persist across reloads and
restarts** — nothing lives in memory or in a container.

### 6. Set permissions and reload

PythonAnywhere serves files as your user, so the folders must be writable:

```bash
chmod -R u+w ~/skillet-flask/instance ~/skillet-flask/app/uploads
```

Back on the **Web** tab, click **Reload**. Visit your app at
`https://YOUR_USERNAME.pythonanywhere.com`.

Custom domains (paid tiers) work with no extra configuration — the app does not
depend on the request host.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Covers: auth flows, password hashing, CSRF enforcement, privacy isolation between
users, recipe CRUD, image upload validation, pantry management, weekly planner
assignment, grocery aggregation/unit merging, and quantity formatting.

## Project layout

```
app.py                     # dev entry point (flask run / python app.py)
wsgi.py                    # PythonAnywhere WSGI entry point
wsgi_example.py            # generic WSGI example
requirements.txt           # runtime dependencies
app/__init__.py            # application factory (create_app)
app/models.py              # SQLAlchemy models (User, Recipe, Ingredient, MealPlan, PlanEntry, PantryItem)
app/extensions.py          # db, login_manager, csrf
app/routes/                # blueprints: main, auth, recipes, plans, grocery
app/lib/ingredients.py     # ingredient line parsing + normalization
app/lib/grocery.py         # unit conversion, merging, quantity formatting
app/templates/             # Jinja2 templates (branding preserved)
app/static/                # CSS/JS with the Skillet palette
app/uploads/               # uploaded photos (persistent, git-ignored)
instance/                  # SQLite database (persistent, git-ignored)
tests/                     # pytest suite
```

## Notes on the migration from the Next.js version

- Supabase, Node.js, and Tailwind build tooling are **not required** to run this app.
- The original Next.js project is left untouched in its own folder; this project is
  self-contained.
- Ingredient parsing, unit conversion, grocery merging, and formatting behave the
  same as the original app (ported from the TypeScript helpers and covered by the
  same test cases).
- Features that depended on public links (QR guest voting, shared cookbooks) are
  not part of this single-user-per-account version; meal planning, pantry, and the
  generated shopping list are all here.

## Security summary

- Passwords hashed with Werkzeug (`pbkdf2:sha256`, 600k iterations) — plaintext never stored
- Flask-Login sessions with HttpOnly cookies and SameSite=Lax
- CSRF tokens validated on every POST (Flask-WTF)
- Per-user query scoping: every recipe/plan/grocery route checks ownership
- Uploads: extension allow-list (png/jpg/jpeg/gif/webp), `secure_filename`, size limit
- No secrets or database files committed (see `.gitignore`)
