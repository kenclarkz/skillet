# Skillet on PythonAnywhere — step by step

This folder is a complete **Flask** port of Skillet that runs on
[PythonAnywhere](https://www.pythonanywhere.com) (a free account works). It keeps its own
**SQLite database** (SQLAlchemy + Alembic) and local photo storage — no external services
required. The Next.js frontend keeps using Supabase; this app is self-contained and can be
migrated from an existing Supabase project with the bundled import script.

```
python/
  wsgi.py                     # what PythonAnywhere loads
  run.py                      # local dev server (python run.py)
  requirements.txt            # flask, flask-sqlalchemy, flask-migrate, requests, segno
  .env.example                # copy to .env
  migrations/                 # Alembic migrations (auto-applied at boot)
  scripts/
    import_supabase.py        # one-way data import from a Supabase project
    deploy_pythonanywhere.sh  # headless deploy (used by GitHub Actions)
    pa_deploy_task.sh         # the scheduled task that unpacks + installs on PA
  skillet/                    # the Flask app
  tests/                      # pytest suite
```

> **What you need:** a PythonAnywhere account. That's it. (Optionally a Supabase project
> if you're migrating data over.)

---

## 1. Put the code on PythonAnywhere

**A. Upload a zip (easiest)**

1. On your machine, zip the **contents** of this `python/` folder.
2. On PythonAnywhere: **Files → Upload file**, upload the zip into your home directory.
3. Open a **Bash console** and unzip it:
   ```bash
   mkdir -p ~/skillet
   unzip skillet-python.zip -d ~/skillet
   ```

**B. Clone from GitHub**

```bash
cd ~
git clone --depth 1 https://github.com/kenclarkz/skillet.git
mv skillet/python ~/skillet
```

## 2. Create a virtualenv and install packages

In the PythonAnywhere Bash console:

```bash
cd ~/skillet            # the folder that contains requirements.txt
mkvirtualenv --python=3.12 skillet-venv
pip install -r requirements.txt
```

(Any Python 3.10+ works; all dependencies are pure-Python friendly for the free tier.)

## 3. Create the `.env` file

```bash
cd ~/skillet
cp .env.example .env
nano .env               # or use the Files editor
```

Minimum viable config — the database and photo paths default to a persistent
`~/skillet-data/` directory outside the code folder, so you don't need to set them:

```
APP_URL=https://yourusername.pythonanywhere.com
SECRET_KEY=any-long-random-string
```

`APP_URL` matters: invite links and QR codes are built from it. Save the file.

## 4. Create the web app

1. On the PythonAnywhere dashboard: **Web → Add a new web app**.
2. Choose **Manual configuration** (not “Flask” — the preset is picky about layout),
   then the newest Python 3.x.
3. In the **Code** section:
   - **Source code:** `/home/yourusername/skillet`
   - **Working directory:** `/home/yourusername/skillet`
   - **WSGI configuration file:** click the file it generates (something like
     `var/www/yourusername_pythonanywhere_com_wsgi.py`), open it in the editor, and replace
     its contents with:

     ```python
     import sys
     from pathlib import Path

     BASE = Path("/home/yourusername/skillet")
     sys.path.insert(0, str(BASE))

     from wsgi import app as application
     ```

     (Replace `yourusername` with your actual username.)
4. In the **Virtualenv** section, pick `~/skillet-venv` (or wherever you made it in step 2).
5. In the **Static files** section, add one mapping so CSS/JS are served by nginx:
   - **URL:** `/static/`
   - **Directory:** `/home/yourusername/skillet/skillet/static`
6. Click **Reload**. Visit `https://yourusername.pythonanywhere.com` — you should see the
   Skillet landing page. On first boot the SQLite database is created at
   `~/skillet-data/skillet.db` and migrations run automatically.

## 5. Set the final APP_URL and sign up

1. Back in the Files editor, fix `APP_URL` in `~/skillet/.env` to your real URL
   if you haven't already, then press **Reload**.
2. Open the site → **Sign up** with your email + password (6+ characters).
   A default private cookbook is created automatically for every new account.

## 6. Migrating an existing Supabase project (optional)

If you already ran Skillet against Supabase, bring the data across:

```bash
cd ~/skillet
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...    # Settings → API → service_role
python scripts/import_supabase.py --download-photos
```

- Reads every table via PostgREST and users via the GoTrue admin API (read-only).
- **Supabase passwords cannot be exported** — each imported account gets a one-time
  claim link (`~/skillet-data/claim-links.txt`) to set a new password. Send each user
  their link; after claiming, they log in normally.
- Recipe photos are copied into the local uploads directory and served from `/media/...`.
- The script never deletes local rows and is safe to re-run (upsert by id).

## 7. Updating the app later

Push to `main` with the GitHub Actions workflow configured (see below), or manually:

```bash
cd ~/skillet
# pull new code (git) or re-upload files, then:
pip install -r requirements.txt   # only if requirements changed
```

Then press **Reload** on the Web tab. Database migrations re-apply automatically on boot.

## Automated deploys from GitHub Actions

The workflow in `.github/workflows/deploy-pythonanywhere.yml` tests, packages, and deploys
the `python/` folder on every push to `main`. It uses PythonAnywhere's public API (no
console needed): upload tarball → create a one-shot scheduled task → wait for the task's
completion marker → reload the webapp → smoke-check the site.

Set these repository secrets:

| Secret | Value |
|---|---|
| `PA_USERNAME` | your PythonAnywhere username |
| `PA_API_TOKEN` | PythonAnywhere → Account → API token |
| `PA_APP_NAME` | your webapp domain, e.g. `yourusername.pythonanywhere.com` |
| `PA_HOST` | (optional) `eu` if your account is on `eu.pythonanywhere.com` |

The webapp itself must already exist (step 4) — the workflow only uploads code, installs
dependencies into `~/skillet-venv`, and reloads. You can also run a deploy manually with
`workflow_dispatch`, or straight from your machine:

```bash
tar -czf /tmp/skillet.tar.gz -C python .
bash python/scripts/deploy_pythonanywhere.sh /tmp/skillet.tar.gz "$(git rev-parse HEAD)"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| 400 “Invalid or missing CSRF token” | Your browser is blocking cookies. Allow cookies for the pythonanywhere.com domain. |
| “The database is busy — please try again” | Two requests collided on SQLite's write lock; it retries and is usually transient. Check **Web → Error log** if it persists. |
| Login loops back to `/login` | Cookie issue (above). Otherwise check the error log — the password hash may be missing (unclaimed imported account; use the claim link). |
| Photo upload fails | File must be ≤ 5 MB JPEG/PNG/GIF/WebP/AVIF. Check `~/skillet-data/uploads/` is writable. |
| Import says “site did not respond” | Many recipe sites block datacenter IPs. Add the recipe manually, or try a different site. |
| Error pages with no detail | **Web → Error log** and the log files in `var/log/` for the traceback. Also `~/skillet-data/deploy-task.log` for deploy issues. |
| Free-tier site sleeps | First request after idle takes ~30 s (waking the app). Paid accounts don't sleep. |

## Running the tests

```bash
cd python
pip install -r requirements.txt pytest
pytest tests -q
```

The suite covers auth (signup/login/claim flow), recipe CRUD, cookbook authorization
(owner/editor/viewer/stranger), plans + guest voting, grocery aggregation, pantry exclusion,
import parsing, retailer matching, the SSRF guard, and SQLite persistence across restarts.

## Feature parity with the Next.js app

Everything is here: cookbooks + members + invites (QR/copy links), recipes with photo
upload and serving scaling, one-URL import with SSRF-safe fetching, week plans with guest
voting (invite-token ballots — no accounts needed), grocery aggregation with pantry
exclusion and checked-state persistence, and honest Walmart/Instacart adapters that never
fake a cart. Auth is local email/password (werkzeug hashing) in signed HttpOnly session
cookies; RLS policies from the Supabase schema are enforced in explicit Python
permission checks (`skillet/queries.py`).
