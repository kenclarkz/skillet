"""Data-access and authorization helpers.

Mirrors src/lib/queries.ts and the Supabase RLS policies from
supabase/migrations/20261017000001_init.sql — with SQLite there is no RLS, so
every read/write goes through the explicit permission checks below.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import exists, select

from .db import db
from .errors import AppError
from .ingredients import normalize_ingredient_name, parse_ingredient_line, qty_to_number
from .models import (
    Cookbook,
    CookbookMember,
    GroceryItem,
    GroceryList,
    Invite,
    PantryItem,
    PlanRecipe,
    Recipe,
    User,
    Vote,
    WeeklyPlan,
    new_id,
    utcnow,
)

EDITOR_ROLES = ("owner", "editor")


# --- permissions -----------------------------------------------------------


def get_role(user_id: str | None, cookbook_id: str) -> str | None:
    """cookbook_role() RPC: 'owner' | 'editor' | 'viewer' | None."""
    if not user_id:
        return None
    cookbook = db.session.get(Cookbook, cookbook_id)
    if cookbook is None:
        return None
    if cookbook.owner_id == user_id:
        return "owner"
    member = db.session.get(CookbookMember, {"cookbook_id": cookbook_id, "user_id": user_id})
    return member.role if member else None


def can_edit(role: str | None) -> bool:
    return role in EDITOR_ROLES


def can_view_cookbook(user_id: str | None, cookbook: Cookbook | None) -> bool:
    """can_view_cookbook() policy: owner, member, or signed-in viewer of a public cookbook."""
    if cookbook is None:
        return False
    if user_id and cookbook.owner_id == user_id:
        return True
    if not cookbook.is_private and user_id:
        return True
    if user_id and db.session.get(CookbookMember, {"cookbook_id": cookbook.id, "user_id": user_id}):
        return True
    return False


def require_visible_cookbook(user_id: str | None, cookbook_id: str) -> Cookbook:
    cookbook = db.session.get(Cookbook, cookbook_id)
    if cookbook is None or not can_view_cookbook(user_id, cookbook):
        raise AppError("Cookbook not found.", 404)
    return cookbook


def require_cookbook_role(
    user_id: str | None, cookbook_id: str, roles: Sequence[str] = EDITOR_ROLES
) -> Cookbook:
    cookbook = require_visible_cookbook(user_id, cookbook_id)
    if get_role(user_id, cookbook_id) not in roles:
        raise AppError("You do not have permission to do that.", 403)
    return cookbook


def require_plan(user_id: str | None, plan_id: str, *, editable: bool = False) -> WeeklyPlan:
    plan = db.session.get(WeeklyPlan, plan_id)
    cookbook = db.session.get(Cookbook, plan.cookbook_id) if plan else None
    if plan is None or not can_view_cookbook(user_id, cookbook):
        raise AppError("Plan not found.", 404)
    if editable and not can_edit(get_role(user_id, plan.cookbook_id)):
        raise AppError("You do not have permission to do that.", 403)
    return plan


def require_grocery_list(user_id: str | None, list_id: str, *, editable: bool = False) -> GroceryList:
    grocery_list = db.session.get(GroceryList, list_id)
    if grocery_list is None:
        raise AppError("Grocery list not found.", 404)
    require_plan(user_id, grocery_list.plan_id, editable=editable)
    return grocery_list


# --- reads -----------------------------------------------------------------


def visible_cookbook_ids(user_id: str | None) -> list[str] | None:
    """None means "no visibility"; otherwise the list of visible cookbook ids."""
    if not user_id:
        return []
    rows = db.session.query(Cookbook).all()
    return [c.id for c in rows if can_view_cookbook(user_id, c)]


def list_cookbooks(user_id: str | None) -> list[dict[str, Any]]:
    cookbooks = db.session.query(Cookbook).order_by(Cookbook.created_at.asc()).all()
    counts: dict[str, int] = {}
    for cookbook_id, in db.session.query(Recipe.cookbook_id).distinct():
        counts[cookbook_id] = db.session.query(Recipe).filter(Recipe.cookbook_id == cookbook_id).count()
    role_by_cookbook: dict[str, str] = {}
    if user_id:
        for member in db.session.query(CookbookMember).filter(CookbookMember.user_id == user_id):
            role_by_cookbook[member.cookbook_id] = member.role
    out = []
    for cookbook in cookbooks:
        if not can_view_cookbook(user_id, cookbook):
            continue
        role = "owner" if cookbook.owner_id == user_id else role_by_cookbook.get(cookbook.id, "viewer")
        out.append({**cookbook.to_dict(), "recipe_count": counts.get(cookbook.id, 0), "role": role})
    return out


def editable_cookbooks(user_id: str | None) -> list[dict[str, Any]]:
    return [c for c in list_cookbooks(user_id) if can_edit(c["role"])]


def get_cookbook(user_id: str | None, cookbook_id: str) -> dict[str, Any] | None:
    cookbook = db.session.get(Cookbook, cookbook_id)
    if cookbook is None or not can_view_cookbook(user_id, cookbook):
        return None
    return cookbook.to_dict()


def get_recipes(user_id: str | None, cookbook_id: str) -> list[dict[str, Any]]:
    if not can_view_cookbook(user_id, db.session.get(Cookbook, cookbook_id)):
        return []
    rows = (
        db.session.query(Recipe)
        .filter(Recipe.cookbook_id == cookbook_id)
        .order_by(Recipe.created_at.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


def get_recipe(user_id: str | None, recipe_id: str) -> dict[str, Any] | None:
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None or not can_view_cookbook(user_id, db.session.get(Cookbook, recipe.cookbook_id)):
        return None
    return recipe.to_dict()


def get_plans(user_id: str | None, cookbook_id: str | None = None) -> list[dict[str, Any]]:
    query = db.session.query(WeeklyPlan).order_by(WeeklyPlan.week_start.desc())
    if cookbook_id:
        query = query.filter(WeeklyPlan.cookbook_id == cookbook_id)
    query = query.limit(50)
    visible = set(visible_cookbook_ids(user_id) or [])
    return [p.to_dict() for p in query.all() if p.cookbook_id in visible]


def get_plan(user_id: str | None, plan_id: str) -> dict[str, Any] | None:
    plan = db.session.get(WeeklyPlan, plan_id)
    if plan is None or not can_view_cookbook(user_id, db.session.get(Cookbook, plan.cookbook_id)):
        return None
    return plan.to_dict()


def get_plan_recipes(user_id: str | None, plan_id: str) -> list[dict[str, Any]]:
    if get_plan(user_id, plan_id) is None:
        return []
    rows = (
        db.session.query(PlanRecipe)
        .filter(PlanRecipe.plan_id == plan_id)
        .order_by(PlanRecipe.created_at.asc())
        .all()
    )
    out = []
    for row in rows:
        recipe = db.session.get(Recipe, row.recipe_id)
        out.append(
            {
                "plan_id": row.plan_id,
                "recipe_id": row.recipe_id,
                "selected": bool(row.selected),
                "recipe": recipe.to_dict() if recipe else None,
            }
        )
    return out


def get_votes(user_id: str | None, plan_id: str) -> list[dict[str, Any]]:
    if get_plan(user_id, plan_id) is None:
        return []
    rows = db.session.query(Vote).filter(Vote.plan_id == plan_id).all()
    return [v.to_dict() for v in rows]


def get_members(user_id: str | None, cookbook_id: str) -> list[dict[str, Any]]:
    """RLS mirror: the owner sees all members; members only see themselves."""
    role = get_role(user_id, cookbook_id)
    if not role:
        return []
    query = db.session.query(CookbookMember).filter(CookbookMember.cookbook_id == cookbook_id)
    if role != "owner":
        query = query.filter(CookbookMember.user_id == user_id)
    members = query.order_by(CookbookMember.created_at.asc()).all()
    out = []
    for member in members:
        profile = db.session.get(User, member.user_id)
        out.append({**member.to_dict(), "profile": profile.to_dict() if profile else None})
    return out


def get_invites(user_id: str | None, cookbook_id: str) -> list[dict[str, Any]]:
    if get_role(user_id, cookbook_id) != "owner":
        return []
    rows = (
        db.session.query(Invite)
        .filter(Invite.cookbook_id == cookbook_id)
        .order_by(Invite.created_at.desc())
        .all()
    )
    return [i.to_dict() for i in rows]


def invite_is_active(invite: dict[str, Any], now: datetime | None = None) -> bool:
    if invite.get("revoked_at"):
        return False
    expires_at = invite.get("expires_at")
    if not expires_at:
        return True
    now = now or utcnow()
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    return expires > now


def get_grocery_list_id(user_id: str | None, plan_id: str) -> str | None:
    if get_plan(user_id, plan_id) is None:
        return None
    row = db.session.query(GroceryList).filter(GroceryList.plan_id == plan_id).one_or_none()
    return row.id if row else None


def get_grocery_items(user_id: str | None, list_id: str) -> list[dict[str, Any]]:
    if not list_id:
        return []
    grocery_list = db.session.get(GroceryList, list_id)
    if grocery_list is None or get_plan(user_id, grocery_list.plan_id) is None:
        return []
    rows = (
        db.session.query(GroceryItem)
        .filter(GroceryItem.list_id == list_id)
        .order_by(GroceryItem.in_pantry.asc(), GroceryItem.sort_key.asc())
        .all()
    )
    return [i.to_dict() for i in rows]


def get_pantry(user_id: str | None) -> list[dict[str, Any]]:
    if not user_id:
        return []
    rows = (
        db.session.query(PantryItem)
        .filter(PantryItem.user_id == user_id)
        .order_by(PantryItem.name.asc())
        .all()
    )
    return [p.to_dict() for p in rows]


def get_pantry_names(user_id: str | None) -> set[str]:
    return {row["normalized_name"] for row in get_pantry(user_id)}


def get_profile(user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    return user.to_dict() if user else None


# --- pure helpers (unchanged ports) ----------------------------------------


def int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        n = int(float(str(value).strip().replace(",", ".")))
    except ValueError:
        return None
    return n if n >= 0 else None


def next_monday(today: datetime | date | None = None) -> str:
    """Next Monday strictly after today (never today)."""
    if isinstance(today, datetime):
        today = today.date()
    today = today or utcnow().date()
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


# --- mutations -------------------------------------------------------------


def build_grocery_list(user_id: str, plan_id: str) -> None:
    """Rebuild the grocery list for a plan — port of buildGroceryList action."""
    plan = require_plan(user_id, plan_id, editable=True)
    cookbook_id = plan.cookbook_id

    plan_rows = (
        db.session.query(PlanRecipe).filter(PlanRecipe.plan_id == plan_id).all()
    )

    chosen: list[dict[str, Any]] = []
    for row in plan_rows:
        recipe = db.session.get(Recipe, row.recipe_id)
        if recipe is None:
            continue
        chosen.append(
            {
                "recipe_id": row.recipe_id,
                "selected": bool(row.selected),
                "recipes": recipe.to_dict(),
            }
        )

    selected = [r for r in chosen if r["selected"]]
    if selected:
        chosen = selected
    else:
        sums: dict[str, int] = {}
        for vote in db.session.query(Vote).filter(Vote.plan_id == plan_id):
            sums[vote.recipe_id] = sums.get(vote.recipe_id, 0) + int(vote.value)
        winners = {rid for rid, total in sums.items() if total > 0}
        if winners:
            chosen = [r for r in chosen if r["recipe_id"] in winners]

    source: list[dict[str, Any]] = []
    for row in chosen:
        recipe = row["recipes"] or {}
        for ing in to_ingredients(recipe.get("ingredients")):
            source.append(
                {
                    **ing,
                    "recipeId": recipe.get("id") or row["recipe_id"],
                    "recipeTitle": recipe.get("title") or "Recipe",
                    "scale": 1,
                }
            )

    from .grocery import aggregate_groceries

    pantry = get_pantry_names(user_id)
    aggregated = aggregate_groceries(source, pantry)

    grocery_list = db.session.query(GroceryList).filter(GroceryList.plan_id == plan_id).one_or_none()
    if grocery_list is None:
        grocery_list = GroceryList(plan_id=plan_id, created_by=user_id)
        db.session.add(grocery_list)
        db.session.flush()
    list_id = grocery_list.id

    prior_rows = (
        db.session.query(GroceryItem)
        .filter(GroceryItem.list_id == list_id)
        .all()
    )
    prior = {f"{r.normalized_name}|{r.unit or ''}": r for r in prior_rows}
    for row in prior_rows:
        db.session.delete(row)
    db.session.flush()

    for item in aggregated:
        state = prior.get(f"{item['normalized_name']}|{item.get('unit') or ''}")
        db.session.add(
            GroceryItem(
                list_id=list_id,
                name=item["name"],
                normalized_name=item["normalized_name"],
                qty=item["qty"],
                unit=item.get("unit") or "",
                recipe_ids=item.get("recipe_ids") or [],
                in_pantry=bool(item.get("in_pantry", False)),
                excluded=True if item.get("in_pantry") else bool(state.excluded if state else False),
                checked=bool(state.checked if state else False),
                sort_key=item["name"].lower(),
            )
        )
    db.session.commit()


def select_top_voted(user_id: str, plan_id: str, slots: int = 5) -> None:
    require_plan(user_id, plan_id, editable=True)
    sums: dict[str, int] = {}
    for vote in db.session.query(Vote).filter(Vote.plan_id == plan_id):
        sums[vote.recipe_id] = sums.get(vote.recipe_id, 0) + int(vote.value)
    winners = [rid for rid, total in sorted(sums.items(), key=lambda kv: -kv[1]) if total > 0][:slots]
    rows = db.session.query(PlanRecipe).filter(PlanRecipe.plan_id == plan_id).all()
    for row in rows:
        row.selected = row.recipe_id in winners
    db.session.commit()


# --- guest voting (formerly cast_vote / get_vote_ballot RPCs) --------------


def _active_vote_invite(token: str, cookbook_id: str, plan_id: str | None) -> Invite | None:
    invite = (
        db.session.query(Invite)
        .filter(Invite.token == token, Invite.kind == "vote", Invite.cookbook_id == cookbook_id)
        .one_or_none()
    )
    if invite is None:
        return None
    if plan_id is not None and invite.plan_id not in (None, plan_id):
        return None
    if not invite_is_active(invite.to_dict()):
        return None
    return invite


def _resolve_ballot_plan(invite: Invite) -> WeeklyPlan | None:
    if invite.plan_id:
        return db.session.get(WeeklyPlan, invite.plan_id)
    return (
        db.session.query(WeeklyPlan)
        .filter(WeeklyPlan.cookbook_id == invite.cookbook_id)
        .order_by(WeeklyPlan.week_start.desc())
        .first()
    )


def get_vote_ballot(token: str, voter_key: str | None = None) -> dict[str, Any]:
    """get_vote_ballot() RPC: public ballot for a vote invite token."""
    invite = db.session.query(Invite).filter(Invite.token == token).one_or_none()
    if invite is None or invite.kind != "vote" or not invite_is_active(invite.to_dict()):
        raise AppError("invalid or expired invite", 400)

    cookbook = db.session.get(Cookbook, invite.cookbook_id)
    plan = _resolve_ballot_plan(invite)
    recipes: list[dict[str, Any]] = []
    tallies: dict[str, dict[str, Any]] = {}
    my_votes: dict[str, int] = {}

    if plan is not None:
        for row in db.session.query(PlanRecipe).filter(PlanRecipe.plan_id == plan.id):
            recipe = db.session.get(Recipe, row.recipe_id)
            if recipe is None:
                continue
            recipes.append(
                {
                    "id": recipe.id,
                    "title": recipe.title,
                    "description": recipe.description,
                    "photo_path": recipe.photo_path,
                    "tags": list(recipe.tags or []),
                    "prep_minutes": recipe.prep_minutes,
                    "cook_minutes": recipe.cook_minutes,
                    "servings": recipe.servings,
                }
            )
        recipes.sort(key=lambda r: r["title"])
        for vote in db.session.query(Vote).filter(Vote.plan_id == plan.id):
            tally = tallies.setdefault(vote.recipe_id, {"up": 0, "down": 0, "names": []})
            if vote.value > 0:
                tally["up"] += 1
            elif vote.value < 0:
                tally["down"] += 1
            if vote.voter_name not in tally["names"]:
                tally["names"].append(vote.voter_name)
        for tally in tallies.values():
            tally["names"].sort()
        if voter_key:
            for vote in db.session.query(Vote).filter(
                Vote.plan_id == plan.id, Vote.voter_key == voter_key
            ):
                my_votes[vote.recipe_id] = vote.value

    return {
        "cookbook": {"id": cookbook.id, "name": cookbook.name} if cookbook else None,
        "plan": plan.to_dict() if plan else None,
        "recipes": recipes,
        "tallies": tallies,
        "my_votes": my_votes,
    }


def cast_vote(
    plan_id: str,
    recipe_id: str,
    voter_key: str,
    voter_name: str,
    value: int,
    invite_token: str | None = None,
    user_id: str | None = None,
) -> None:
    """cast_vote() RPC: member or invited-guest vote with upsert semantics."""
    if value not in (-1, 0, 1):
        raise AppError("invalid vote value", 400)

    plan = db.session.get(WeeklyPlan, plan_id)
    if plan is None:
        raise AppError("plan not found", 400)

    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None or recipe.cookbook_id != plan.cookbook_id:
        raise AppError("recipe not in plan cookbook", 400)

    role = get_role(user_id, plan.cookbook_id)
    is_member = role is not None
    invite_ok = bool(
        invite_token
        and _active_vote_invite(invite_token, plan.cookbook_id, plan_id) is not None
    )

    if not is_member and not invite_ok:
        raise AppError("not authorized to vote", 403)

    if voter_key.startswith("user:"):
        if not is_member:
            raise AppError("member vote requires membership", 403)
    elif not invite_ok:
        raise AppError("valid invite required", 403)

    vote = (
        db.session.query(Vote)
        .filter(Vote.plan_id == plan_id, Vote.recipe_id == recipe_id, Vote.voter_key == voter_key)
        .one_or_none()
    )
    if vote is None:
        vote = Vote(plan_id=plan_id, recipe_id=recipe_id, voter_key=voter_key, voter_name=voter_name, value=value)
        db.session.add(vote)
    else:
        vote.value = value
        vote.voter_name = voter_name
        vote.updated_at = utcnow()
    db.session.commit()


def join_cookbook(user_id: str, token: str) -> str:
    """join_cookbook() RPC: join a cookbook with a member invite token."""
    invite = db.session.query(Invite).filter(Invite.token == token).one_or_none()
    if invite is None or invite.kind != "member" or not invite_is_active(invite.to_dict()):
        raise AppError("invalid or expired invite", 400)

    existing = db.session.get(CookbookMember, {"cookbook_id": invite.cookbook_id, "user_id": user_id})
    if existing is None:
        db.session.add(
            CookbookMember(
                cookbook_id=invite.cookbook_id,
                user_id=user_id,
                role=invite.role or "viewer",
            )
        )
        db.session.commit()
    return invite.cookbook_id


# --- misc parsing helpers ---------------------------------------------------


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


def ensure_default_cookbook(user: User) -> Cookbook:
    """Port of the handle_new_user() trigger: every user gets a starter cookbook."""
    cookbook = Cookbook(owner_id=user.id, name=f"{user.display_name or 'Chef'}'s Cookbook", is_private=True)
    db.session.add(cookbook)
    db.session.flush()
    return cookbook
