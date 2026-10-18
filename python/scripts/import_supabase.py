"""One-way import from a Supabase project into the local SQLite database.

Reads every public table via PostgREST and users via the GoTrue admin API
(requires the service-role key — auth passwords are NOT exportable, so each
imported user gets a one-time claim link to set their first password).

Usage (from the python/ directory):

    export SUPABASE_URL=https://xxxx.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=eyJ...   # Settings → API → service_role
    python scripts/import_supabase.py [--download-photos] [--dry-run]

The script NEVER deletes local rows: existing rows with the same id are
updated in place, new ids are inserted. Safe to re-run.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillet import create_app  # noqa: E402
from skillet.config import Config  # noqa: E402
from skillet.db import db  # noqa: E402
from skillet.models import (  # noqa: E402
    Cookbook,
    CookbookMember,
    GroceryItem,
    GroceryList,
    Invite,
    PantryItem,
    PasswordResetToken,
    PlanRecipe,
    Recipe,
    User,
    Vote,
    WeeklyPlan,
    new_id,
)

PAGE_SIZE = 1000

# Table import order respects foreign keys.
TABLE_PLAN = [
    ("cookbooks", Cookbook),
    ("cookbook_members", CookbookMember),
    ("weekly_plans", WeeklyPlan),
    ("recipes", Recipe),
    ("plan_recipes", PlanRecipe),
    ("votes", Vote),
    ("invites", Invite),
    ("pantry_items", PantryItem),
    ("grocery_lists", GroceryList),
    ("grocery_items", GroceryItem),
]


def parse_ts(value) -> datetime | None:
    """PostgREST timestamptz → naive UTC datetime (matches utcnow() storage)."""
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def parse_date(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value)[:10]).date()


class SupabaseReader:
    def __init__(self, url: str, anon_key: str, service_role_key: str | None):
        self.base = url.rstrip("/")
        self.session = requests.Session()
        self.service_role_key = service_role_key

    def _headers(self, key: str | None = None) -> dict[str, str]:
        return {"apikey": key or self.service_role_key or "", "Authorization": f"Bearer {key or self.service_role_key}"}

    def rest_headers(self) -> dict[str, str]:
        # PostgREST: anon key is enough (RLS allows selects for authenticated;
        # we use the service role key to bypass RLS entirely for a full export).
        return self._headers()

    def fetch_all(self, table: str) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            headers = {**self.rest_headers(), "Range-Unit": "items", "Prefer": "count=exact"}
            response = self.session.get(
                f"{self.base}/rest/v1/{table}",
                headers=headers,
                params={"select": "*"},
                range=(offset, offset + PAGE_SIZE - 1),
                timeout=60,
            )
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE

    def fetch_auth_users(self) -> list[dict]:
        if not self.service_role_key:
            raise SystemExit(
                "Reading auth users requires SUPABASE_SERVICE_ROLE_KEY "
                "(GoTrue admin API). Export it and re-run."
            )
        users: list[dict] = []
        page = 1
        while True:
            response = self.session.get(
                f"{self.base}/auth/v1/admin/users",
                headers=self._headers(),
                params={"page": page, "per_page": 200},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("users", payload if isinstance(payload, list) else [])
            users.extend(batch)
            if len(batch) < 200:
                return users
            page += 1

    def download_photo(self, photo_path: str) -> bytes | None:
        response = self.session.get(
            f"{self.base}/storage/v1/object/public/recipe-photos/{photo_path}",
            timeout=60,
        )
        if response.status_code != 200:
            return None
        return response.content


def upsert(model, row: dict, defaults: dict | None = None):
    """Insert-or-update by primary key; returns the instance."""
    pk_names = [pk.name for pk in model.__mapper__.primary_key]
    if len(pk_names) == 1:
        pk = row.get(pk_names[0])
        instance = db.session.get(model, pk) if pk else None
    else:
        identity = {name: row.get(name) for name in pk_names}
        if all(identity.values()):
            instance = db.session.get(model, identity)
        else:
            instance = None
    if instance is None:
        instance = model(**{**(defaults or {}), **row})
        db.session.add(instance)
    else:
        for key, value in row.items():
            setattr(instance, key, value)
    return instance


def clean_row(table: str, row: dict) -> dict:
    """Map PostgREST row → model kwargs (drop unknown, coerce types)."""
    if table == "profiles":
        return row
    model = dict(TABLE_PLAN)[table]
    allowed = {c.name for c in model.__table__.columns}
    out = {k: v for k, v in row.items() if k in allowed}
    for col in ("created_at", "updated_at", "expires_at", "revoked_at"):
        if col in out:
            out[col] = parse_ts(out[col])
    if "week_start" in out:
        out["week_start"] = parse_date(out["week_start"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"), help="Supabase project URL")
    parser.add_argument(
        "--service-role-key",
        default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
        help="service_role key (needed to read auth.users and bypass RLS)",
    )
    parser.add_argument("--download-photos", action="store_true", help="copy recipe photos into the local uploads dir")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, but do not write to the database")
    args = parser.parse_args()

    if not args.url:
        raise SystemExit("Missing SUPABASE_URL (env or --url).")
    if not args.service_role_key:
        raise SystemExit("Missing SUPABASE_SERVICE_ROLE_KEY (env or --service-role-key).")

    reader = SupabaseReader(args.url, anon_key=args.service_role_key, service_role_key=args.service_role_key)
    app = create_app()
    cfg: Config = app.config["SKILLET"]

    print(f"Reading {args.url} …")
    auth_users = reader.fetch_auth_users()
    tables = {table: reader.fetch_all(table) for table, _ in TABLE_PLAN}
    profiles = {p["id"]: p for p in reader.fetch_all("profiles")}
    print(
        "Fetched: "
        + ", ".join(f"{len(rows)} {name}" for name, rows in tables.items())
        + f", {len(auth_users)} auth users"
    )

    with app.app_context():
        claim_rows: list[tuple[str, str]] = []  # (email, token)
        imported_users: set[str] = set()

        # --- users (auth.users + profiles) ---
        for auth_user in auth_users:
            uid = auth_user["id"]
            email = (auth_user.get("email") or "").strip().lower()
            if not email:
                continue
            profile = profiles.get(uid, {})
            metadata = auth_user.get("raw_user_meta_data") or {}
            display = (
                (profile.get("display_name") or metadata.get("display_name") or metadata.get("full_name") or "")
                .strip()
                or email.split("@")[0]
            )
            instance = db.session.get(User, uid)
            if instance is None:
                instance = User(
                    id=uid,
                    email=email,
                    password_hash=None,  # Supabase passwords cannot be exported
                    display_name=display[:80],
                    avatar_url=profile.get("avatar_url"),
                    created_at=parse_ts(auth_user.get("created_at")) or parse_ts(profile.get("created_at")),
                )
                db.session.add(instance)
            else:
                instance.email = email
                instance.display_name = display[:80]
                instance.avatar_url = profile.get("avatar_url")
            imported_users.add(uid)
            token = new_id() + new_id()
            db.session.add(
                PasswordResetToken(
                    token=token,
                    user_id=uid,
                    expires_at=datetime.now(timezone.utc).replace(tzinfo=None).replace(year=datetime.now().year + 1),
                )
            )
            claim_rows.append((email, token))

        # --- content tables ---
        for table, _model in TABLE_PLAN:
            for row in tables[table]:
                # Skip orphans whose owner/user never imported.
                if table in ("cookbooks", "pantry_items") and row.get("owner_id" if table == "cookbooks" else "user_id") not in imported_users:
                    if row.get("owner_id" if table == "cookbooks" else "user_id"):
                        # Owner exists as uuid but maybe no auth email — still import
                        # with a placeholder user so content isn't lost.
                        missing = row.get("owner_id" if table == "cookbooks" else "user_id")
                        _ensure_placeholder_user(missing, profiles, claim_rows)
                        imported_users.add(missing)
                if table == "invites" and row.get("created_by") and row["created_by"] not in imported_users:
                    _ensure_placeholder_user(row["created_by"], profiles, claim_rows)
                    imported_users.add(row["created_by"])
                payload = clean_row(table, row)
                upsert(_model, payload)
            db.session.flush()
            print(f"  {table}: {len(tables[table])} rows")

        # --- photos ---
        downloaded = skipped = 0
        if args.download_photos:
            for recipe in tables["recipes"]:
                path = recipe.get("photo_path")
                if not path or path.startswith("http"):
                    continue
                destination = cfg.UPLOAD_DIR / path
                if destination.exists():
                    skipped += 1
                    continue
                content = reader.download_photo(path)
                if content is None:
                    skipped += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                downloaded += 1
                time.sleep(0.05)  # be polite to the storage API
            print(f"Photos: {downloaded} downloaded, {skipped} skipped/missing")

        if args.dry_run:
            db.session.rollback()
            print("\nDry run — nothing written.")
        else:
            db.session.commit()
            print(f"\nImported {len(imported_users)} users, database committed.")
            if claim_rows:
                claims_path = cfg.DATA_DIR / "claim-links.txt"
                with claims_path.open("w") as handle:
                    for email, token in claim_rows:
                        handle.write(f"{email}\t{cfg.APP_URL}/claim/{token}\n")
                print(f"Claim links written to {claims_path}")
                print("Each imported user must open their link once to set a password.")
    return 0


def _ensure_placeholder_user(uid: str, profiles: dict, claim_rows: list) -> None:
    """Create an email-less placeholder user so FKs stay satisfied."""
    if db.session.get(User, uid) is not None:
        return
    profile = profiles.get(uid, {})
    placeholder = User(
        id=uid,
        email=f"{uid[:8]}@import.skillet.invalid",
        password_hash=None,
        display_name=(profile.get("display_name") or "Imported Chef")[:80],
        avatar_url=profile.get("avatar_url"),
    )
    db.session.add(placeholder)
    token = new_id() + new_id()
    db.session.add(
        PasswordResetToken(
            token=token,
            user_id=uid,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None).replace(year=datetime.now().year + 1),
        )
    )
    claim_rows.append((placeholder.email, token))


if __name__ == "__main__":
    raise SystemExit(main())
