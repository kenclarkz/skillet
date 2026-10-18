"""Data-access helpers mirroring src/lib/queries.ts (all RLS-enforced)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .ingredients import normalize_ingredient_name, parse_ingredient_line, qty_to_number
from .supabase import SupabaseClient, SupabaseError


def get_role(client: SupabaseClient, cookbook_id: str) -> str | None:
    try:
        return client.rpc("cookbook_role", {"cookbook_id": cookbook_id})
    except SupabaseError:
        return None


def can_edit(role: str | None) -> bool:
    return role in ("owner", "editor")


def list_cookbooks(client: SupabaseClient, user_id: str) -> list[dict[str, Any]]:
    cookbooks = (
        client.table("cookbooks")
        .select("*")
        .order("created_at", ascending=True)
        .execute()
    )
    counts_rows = client.table("recipes").select("cookbook_id").execute()
    counts: dict[str, int] = {}
    for row in counts_rows:
        counts[row["cookbook_id"]] = counts.get(row["cookbook_id"], 0) + 1
    members = (
        client.table("cookbook_members")
        .select("cookbook_id, role")
        .eq("user_id", user_id)
        .execute()
    )
    role_by_cookbook = {m["cookbook_id"]: m["role"] for m in members}
    out = []
    for cookbook in cookbooks:
        role = "owner" if cookbook["owner_id"] == user_id else role_by_cookbook.get(cookbook["id"], "viewer")
        out.append({**cookbook, "recipe_count": counts.get(cookbook["id"], 0), "role": role})
    return out


def editable_cookbooks(client: SupabaseClient, user_id: str) -> list[dict[str, Any]]:
    return [c for c in list_cookbooks(client, user_id) if can_edit(c["role"])]


def get_cookbook(client: SupabaseClient, cookbook_id: str) -> dict[str, Any] | None:
    return client.table("cookbooks").select("*").eq("id", cookbook_id).maybe_single().execute()


def get_recipes(client: SupabaseClient, cookbook_id: str) -> list[dict[str, Any]]:
    return (
        client.table("recipes")
        .select("*")
        .eq("cookbook_id", cookbook_id)
        .order("created_at", ascending=False)
        .execute()
    )


def get_recipe(client: SupabaseClient, recipe_id: str) -> dict[str, Any] | None:
    return client.table("recipes").select("*").eq("id", recipe_id).maybe_single().execute()


def get_plans(client: SupabaseClient, cookbook_id: str | None = None) -> list[dict[str, Any]]:
    query = client.table("weekly_plans").select("*").order("week_start", ascending=False).limit(50)
    if cookbook_id:
        query = query.eq("cookbook_id", cookbook_id)
    return query.execute()


def get_plan(client: SupabaseClient, plan_id: str) -> dict[str, Any] | None:
    return client.table("weekly_plans").select("*").eq("id", plan_id).maybe_single().execute()


def get_plan_recipes(client: SupabaseClient, plan_id: str) -> list[dict[str, Any]]:
    rows = (
        client.table("plan_recipes")
        .select("plan_id, recipe_id, selected, recipes (*)")
        .eq("plan_id", plan_id)
        .execute()
    )
    out = []
    for row in rows:
        recipe = row.get("recipes")
        out.append(
            {
                "plan_id": row["plan_id"],
                "recipe_id": row["recipe_id"],
                "selected": row.get("selected", False),
                "recipe": recipe,
            }
        )
    return out


def get_votes(client: SupabaseClient, plan_id: str) -> list[dict[str, Any]]:
    return client.table("votes").select("*").eq("plan_id", plan_id).execute()


def get_members(client: SupabaseClient, cookbook_id: str) -> list[dict[str, Any]]:
    members = (
        client.table("cookbook_members")
        .select("*")
        .eq("cookbook_id", cookbook_id)
        .order("created_at", ascending=True)
        .execute()
    )
    if not members:
        return []
    user_ids = [m["user_id"] for m in members]
    profiles = client.table("profiles").select("*").in_("id", user_ids).execute()
    by_id = {p["id"]: p for p in profiles}
    return [{**m, "profile": by_id.get(m["user_id"])} for m in members]


def get_invites(client: SupabaseClient, cookbook_id: str) -> list[dict[str, Any]]:
    return (
        client.table("invites")
        .select("*")
        .eq("cookbook_id", cookbook_id)
        .order("created_at", ascending=False)
        .execute()
    )


def invite_is_active(invite: dict[str, Any], now: datetime | None = None) -> bool:
    if invite.get("revoked_at"):
        return False
    expires_at = invite.get("expires_at")
    if not expires_at:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > now


def get_grocery_list_id(client: SupabaseClient, plan_id: str) -> str | None:
    try:
        row = client.table("grocery_lists").select("id").eq("plan_id", plan_id).maybe_single().execute()
    except SupabaseError:
        return None
    return row["id"] if row else None


def get_grocery_items(client: SupabaseClient, list_id: str) -> list[dict[str, Any]]:
    return (
        client.table("grocery_items")
        .select("*")
        .eq("list_id", list_id)
        .order("in_pantry", ascending=True)
        .order("sort_key", ascending=True)
        .execute()
    )


def get_pantry(client: SupabaseClient, user_id: str) -> list[dict[str, Any]]:
    return (
        client.table("pantry_items")
        .select("*")
        .eq("user_id", user_id)
        .order("name", ascending=True)
        .execute()
    )


def get_pantry_names(client: SupabaseClient, user_id: str) -> set[str]:
    return {row["normalized_name"] for row in get_pantry(client, user_id)}


def get_profile(client: SupabaseClient, user_id: str) -> dict[str, Any] | None:
    return client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()


# --- mutations used by views ----------------------------------------------


def int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        n = int(float(str(value).strip().replace(",", ".")))
    except ValueError:
        return None
    return n if n >= 0 else None


def next_monday(today: datetime | None = None) -> str:
    """Next Monday strictly after today (never today)."""
    today = today or datetime.now(timezone.utc).date()
    day = today.isoweekday()  # Mon=1 .. Sun=7
    delta = 7 if day == 1 else ((8 - day) % 7 or 7)
    return (today + timedelta(days=delta)).isoformat()


def to_ingredients(value: Any) -> list[dict[str, Any]]:
    """Accept a list of strings or structured {qty, unit, name, note} dicts."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            parsed = parse_ingredient_line(item)
            if parsed["name"]:
                out.append(parsed)
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            qty = item.get("qty")
            out.append(
                {
                    "qty": None if qty is None else str(qty),
                    "unit": item.get("unit") or None,
                    "name": name,
                    "note": item.get("note") or None,
                }
            )
    return out


def ingredients_to_lines(ingredients: list[dict[str, Any]]) -> list[str]:
    """Serialize structured ingredients back to editable text lines."""
    lines = []
    for ing in ingredients:
        parts = []
        if ing.get("qty"):
            parts.append(str(ing["qty"]))
        if ing.get("unit"):
            parts.append(str(ing["unit"]))
        if ing.get("name"):
            parts.append(str(ing["name"]))
        line = " ".join(parts)
        note = ing.get("note")
        if note:
            if note.startswith("(") and note.endswith(")"):
                line = f"{line} {note}"
            else:
                line = f"{line}, {note}"
        lines.append(line)
    return lines


def build_grocery_list(client: SupabaseClient, plan_id: str, user_id: str) -> None:
    """Rebuild the grocery list for a plan — port of buildGroceryList action."""
    plan = (
        client.table("weekly_plans").select("id, cookbook_id").eq("id", plan_id).maybe_single().execute()
    )
    if not plan:
        raise SupabaseError("Plan not found.")
    cookbook_id = plan["cookbook_id"]

    plan_rows = (
        client.table("plan_recipes")
        .select("recipe_id, selected, recipes (id, title, ingredients, servings)")
        .eq("plan_id", plan_id)
        .execute()
    )

    chosen = [r for r in plan_rows if r.get("selected")]
    if not chosen:
        votes = client.table("votes").select("recipe_id, value").eq("plan_id", plan_id).execute()
        sums: dict[str, int] = {}
        for vote in votes:
            sums[vote["recipe_id"]] = sums.get(vote["recipe_id"], 0) + int(vote["value"])
        winners = sorted([rid for rid, total in sums.items() if total > 0], key=lambda rid: -sums[rid])
        if winners:
            winner_set = set(winners)
            chosen = [r for r in plan_rows if r["recipe_id"] in winner_set]
        else:
            chosen = plan_rows

    source: list[dict[str, Any]] = []
    for row in chosen:
        recipe = row.get("recipes") or {}
        base_servings = recipe.get("servings") or 4
        for ing in to_ingredients(recipe.get("ingredients")):
            source.append(
                {
                    **ing,
                    "recipeId": recipe.get("id") or row["recipe_id"],
                    "recipeTitle": recipe.get("title") or "Recipe",
                    "scale": 1,
                }
            )
            # note: scaling by servings is intentionally not applied — recipes
            # are authored at their own serving size, matching the Next app.

    from .grocery import aggregate_groceries

    pantry = get_pantry_names(client, user_id)
    aggregated = aggregate_groceries(source, pantry)

    existing_id = get_grocery_list_id(client, plan_id)
    if existing_id:
        list_id = existing_id
    else:
        created = (
            client.table("grocery_lists")
            .insert({"plan_id": plan_id, "created_by": user_id})
            .select("id")
            .single()
            .execute()
        )
        list_id = created["id"]

    prior_rows = (
        client.table("grocery_items")
        .select("normalized_name, unit, checked, excluded")
        .eq("list_id", list_id)
        .execute()
    )
    prior = {f"{r['normalized_name']}|{r.get('unit') or ''}": r for r in prior_rows}

    client.table("grocery_items").delete().eq("list_id", list_id).execute()

    rows = []
    for item in aggregated:
        state = prior.get(f"{item['normalized_name']}|{item.get('unit') or ''}") or {}
        rows.append(
            {
                "list_id": list_id,
                "name": item["name"],
                "normalized_name": item["normalized_name"],
                "qty": item["qty"],
                "unit": item.get("unit") or "",
                "recipe_ids": item.get("recipe_ids") or [],
                "in_pantry": item.get("in_pantry", False),
                "excluded": True if item.get("in_pantry") else bool(state.get("excluded", False)),
                "checked": bool(state.get("checked", False)),
                "sort_key": item["name"].lower(),
            }
        )
    if rows:
        # insert in chunks to keep request bodies reasonable
        for start in range(0, len(rows), 200):
            client.table("grocery_items").insert(rows[start:start + 200]).execute()


def select_top_voted(client: SupabaseClient, plan_id: str, slots: int = 5) -> None:
    votes = client.table("votes").select("recipe_id, value").eq("plan_id", plan_id).execute()
    sums: dict[str, int] = {}
    for vote in votes:
        sums[vote["recipe_id"]] = sums.get(vote["recipe_id"], 0) + int(vote["value"])
    winners = [rid for rid, total in sorted(sums.items(), key=lambda kv: -kv[1]) if total > 0][:slots]
    try:
        client.table("plan_recipes").update({"selected": False}).eq("plan_id", plan_id).execute()
    except SupabaseError:
        pass
    if winners:
        (
            client.table("plan_recipes")
            .update({"selected": True})
            .eq("plan_id", plan_id)
            .in_("recipe_id", winners)
            .execute()
        )


def parse_tags(raw: str) -> list[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()][:10]


def parse_instructions(raw: str) -> list[str]:
    import re

    out = []
    for line in (raw or "").split("\n"):
        trimmed = re.sub(r"^\d+[.)]\s*", "", line.strip())
        if trimmed:
            out.append(trimmed)
    return out


def qty_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def numeric_qty(value: Any) -> float | None:
    return qty_to_number(qty_string(value))


def normalize_item_name(name: str) -> str:
    return normalize_ingredient_name(name)
