# Skillet on PythonAnywhere — step by step

This folder is a complete **Flask** port of Skillet that runs on
[PythonAnywhere](https://www.pythonanywhere.com) (a free account works). It talks to the
**same Supabase project** as the Next.js app — database, auth, photos, and vote RPCs are
all unchanged. Only the web server is Python instead of Node.

```
python/
  wsgi.py            # what PythonAnywhere loads
  run.py             # local dev server (python run.py)
  requirements.txt   # flask, requests, segno
  .env.example       # copy to .env
  skillet/           # the Flask app (views, templates, logic ports)
  tests/             # pytest suite for the pure logic (optional)
```

> **What you need:** a Supabase project (free tier is fine) + a PythonAnywhere account.
> PythonAnywhere hosts the *app*; Supabase provides the database, login, and photo storage.

---

## 1. Create the Supabase project (once)

1. Sign up at https://supabase.com and click **New project**.
2. Pick a name/password/region and wait for the project to be ready.
3. Open **SQL Editor**, paste the entire contents of
   `supabase/migrations/20261017000001_init.sql` (from this repo), and press **Run**.
   This creates all tables, row-level-security policies, the vote RPCs, and the
   `recipe-photos` storage bucket.
4. In **Authentication → Providers → Email**, you can leave “Confirm email” **off** for the
   smoothest start (signups work immediately). If you turn it on, confirmation links still
   work — the app finishes sign-in on `/auth/callback`.
5. In **Settings → API**, copy:
   - **Project URL** → goes in `SUPABASE_URL`
   - **anon / public key** → goes in `SUPABASE_ANON_KEY`

## 2. Put the code on PythonAnywhere

PythonAnywhere has no Node — that's why this Flask port exists. Get the `python/` folder
onto your account using either path:

**A. Upload a zip (easiest)**

1. On your machine, zip the **contents** of this `python/` folder.
2. On PythonAnywhere: **Files → Upload file**, upload the zip into your home directory
   (`/home/yourusername/`).
3. Open a **Bash console** and unzip it:
   ```bash
   mkdir -p skillet
   unzip skillet-python.zip -d skillet
   cd skillet
   ```

**B. Clone from GitHub**

```bash
cd ~
git clone https://github.com/kenclarkz/skillet.git
cd skillet/python
```

## 3. Create a virtualenv and install packages

In the PythonAnywhere Bash console:

```bash
cd ~/skillet            # the folder that contains requirements.txt
mkvirtualenv --python=3.12 skillet-venv
pip install -r requirements.txt
```

(Any Python 3.10+ works. `flask`, `requests`, and `segno` are the only dependencies —
all pure-Python friendly for the free tier.)

## 4. Create the `.env` file

```bash
cd ~/skillet
cp .env.example .env
nano .env               # or use the Files editor
```

Fill it in:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOi...
APP_URL=https://yourusername.pythonanywhere.com
SECRET_KEY=any-long-random-string
```

`APP_URL` matters: invite links and QR codes are built from it. Use your real
PythonAnywhere URL once you know it (step 6). Save the file.

## 5. Create the web app

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
4. In the **Virtualenv** section, pick `~/skillet-venv` (or wherever you made it in step 3).
5. In the **Static files** section, add one mapping so CSS/JS are served by their nginx:
   - **URL:** `/static/`
   - **Directory:** `/home/yourusername/skillet/skillet/static`
6. Click **Reload**. Visit `https://yourusername.pythonanywhere.com` — you should see the
   Skillet landing page.

## 6. Set the final APP_URL and sign up

1. Back in the Files editor, fix `APP_URL` in `~/skillet/.env` to your real URL
   (`https://yourusername.pythonanywhere.com`) if you haven't already.
2. Click **Reload** again.
3. Open the site → **Sign up** with your email + password (6+ characters).
   With email confirmation disabled in Supabase you're signed in immediately; a default
   cookbook is created automatically by a database trigger.
4. Add a recipe (manually or with **Import**), start a vote week from your cookbook,
   share the QR/vote link, and build the grocery list.

## 7. Updating the app later

```bash
cd ~/skillet
# pull new code (git) or re-upload files, then:
pip install -r requirements.txt   # only if requirements changed
```

Then press **Reload** on the Web tab. Static files don't need a reload.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| “Skillet needs a Supabase connection” | `SUPABASE_URL` / `SUPABASE_ANON_KEY` missing or unreadable in `~/skillet/.env`. Check the path matches your layout. |
| 400 “Invalid or missing CSRF token” | Your browser is blocking cookies. Allow cookies for the pythonanywhere.com domain. |
| Login loops back to `/login` | Same cookie issue, or the Supabase URL/key pair is wrong. Check **Authentication → Users** has your account. |
| Photo upload fails | Confirm the `recipe-photos` bucket exists (the migration creates it) and the file is ≤ 5 MB JPEG/PNG/GIF/WebP/AVIF. |
| Import says “site did not respond” | Many recipe sites block datacenter IPs. Add the recipe manually, or try a different site. |
| Error pages with no detail | Browser → **Web → Error log** and the **log** files in `var/log/` for the traceback. |
| Free-tier site sleeps | First request after idle takes ~30 s (waking the app). Paid accounts don't sleep. |

## Running the tests (optional, on your machine or console)

```bash
cd python
pip install -r requirements.txt pytest
pytest tests -q
```

The tests cover ingredient parsing, unit conversion, grocery aggregation, HTML import
parsing, retailer matching, and the SSRF guard — the same behaviors as the Node test suite.

## Feature parity with the Next.js app

Everything is here: cookbooks + members + invites (QR/copy links), recipes with photo
upload and serving scaling, one-URL import with SSRF-safe fetching, week plans with
guest voting (SECURITY DEFINER RPCs, no service role), grocery aggregation with pantry
exclusion and checked-state persistence, and honest Walmart/Instacart adapters that never
fake a cart. Auth is email/password via Supabase GoTrue; sessions live in HttpOnly
cookies; every database call uses the signed-in user's JWT so row-level security is
enforced exactly as before.
