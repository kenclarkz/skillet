"""Week plans, voting ballots, and plan mutations."""

from __future__ import annotations

from collections import defaultdict

from flask import Blueprint, redirect, render_template, request

from .. import auth
from ..queries import (
    get_cookbook,
    get_invites,
    get_plan,
    get_plan_recipes,
    get_plans,
    get_recipes,
    get_role,
    get_votes,
    invite_is_active,
    list_cookbooks,
    next_monday,
    select_top_voted,
)
from ..supabase import SupabaseError

bp = Blueprint("plans", __name__)


@bp.route("/plans")
@auth.require_user
def plans_list():
    client = auth.db()
    plans = get_plans(client)
    cookbooks = list_cookbooks(client, auth.user_id())
    names = {c["id"]: c["name"] for c in cookbooks}
    return render_template("plans/list.html", plans=plans, cookbook_names=names)


@bp.route("/plans/create", methods=["POST"])
@auth.require_user
def create_plan():
    client = auth.db()
    uid = auth.user_id()
    cookbook_id = (request.form.get("cookbook_id") or "").strip()
    week_start = (request.form.get("week_start") or "").strip() or next_monday()
    title = (request.form.get("title") or "").strip() or None
    if not cookbook_id:
        raise SupabaseError("Choose a cookbook.")
    created = (
        client.table("weekly_plans")
        .upsert(
            {"cookbook_id": cookbook_id, "week_start": week_start, "title": title, "created_by": uid},
            on_conflict="cookbook_id,week_start",
        )
        .select("id")
        .single()
        .execute()
    )
    return redirect(f"/plans/{created['id']}")


@bp.route("/plans/<plan_id>")
@auth.require_user
def plan_detail(plan_id):
    client = auth.db()
    plan = get_plan(client, plan_id)
    if not plan:
        return render_template("not_found.html"), 404
    cookbook = get_cookbook(client, plan["cookbook_id"])
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(client, plan["cookbook_id"])
    editable = role in ("owner", "editor")
    plan_recipes = get_plan_recipes(client, plan_id)
    votes = get_votes(client, plan_id)
    all_recipes = get_recipes(client, plan["cookbook_id"])
    invites = get_invites(client, plan["cookbook_id"])

    tallies: dict[str, dict] = defaultdict(lambda: {"up": 0, "down": 0, "names": []})
    for vote in votes:
        rid = vote["recipe_id"]
        value = int(vote["value"])
        if value > 0:
            tallies[rid]["up"] += 1
        elif value < 0:
            tallies[rid]["down"] += 1
        tallies[rid]["names"].append(vote.get("voter_name") or "")

    ballot_ids = {pr["recipe_id"] for pr in plan_recipes}
    addable = [r for r in all_recipes if r["id"] not in ballot_ids]

    active_vote_invite = None
    for invite in invites:
        if invite.get("kind") != "vote" or not invite_is_active(invite):
            continue
        if invite.get("plan_id") and invite["plan_id"] != plan_id:
            continue
        active_vote_invite = invite
        break

    ballot = sorted(
        plan_recipes,
        key=lambda pr: -tallies[pr["recipe_id"]]["up"],
    )

    return render_template(
        "plans/detail.html",
        plan=plan,
        cookbook=cookbook,
        role=role,
        editable=editable,
        ballot=ballot,
        tallies=dict(tallies),
        addable=addable,
        active_vote_invite=active_vote_invite,
        selected_count=sum(1 for pr in plan_recipes if pr.get("selected")),
    )


@bp.route("/plans/<plan_id>/delete", methods=["POST"])
@auth.require_user
def delete_plan(plan_id):
    client = auth.db()
    plan = get_plan(client, plan_id)
    cookbook_id = (request.form.get("cookbook_id") or (plan or {}).get("cookbook_id") or "")
    client.table("weekly_plans").delete().eq("id", plan_id).execute()
    return redirect(f"/cookbooks/{cookbook_id}" if cookbook_id else "/plans")


@bp.route("/plans/<plan_id>/status", methods=["POST"])
@auth.require_user
def set_plan_status(plan_id):
    client = auth.db()
    status = request.form.get("status") or "open"
    if status not in ("open", "closed"):
        status = "open"
    client.table("weekly_plans").update({"status": status}).eq("id", plan_id).execute()
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/select-top", methods=["POST"])
@auth.require_user
def select_top(plan_id):
    client = auth.db()
    try:
        slots = int(request.form.get("slots") or 5)
    except ValueError:
        slots = 5
    select_top_voted(client, plan_id, slots)
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/build-grocery", methods=["POST"])
@auth.require_user
def build_grocery(plan_id):
    from ..queries import build_grocery_list

    client = auth.db()
    build_grocery_list(client, plan_id, auth.user_id())
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes", methods=["POST"])
@auth.require_user
def add_recipe_to_plan(plan_id):
    client = auth.db()
    uid = auth.user_id()
    recipe_id = request.form.get("recipe_id") or ""
    if not recipe_id:
        raise SupabaseError("Choose a recipe.")
    (
        client.table("plan_recipes")
        .upsert({"plan_id": plan_id, "recipe_id": recipe_id, "added_by": uid}, on_conflict="plan_id,recipe_id")
        .execute()
    )
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes/<recipe_id>/remove", methods=["POST"])
@auth.require_user
def remove_recipe_from_plan(plan_id, recipe_id):
    client = auth.db()
    (
        client.table("plan_recipes")
        .delete()
        .eq("plan_id", plan_id)
        .eq("recipe_id", recipe_id)
        .execute()
    )
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes/<recipe_id>/selected", methods=["POST"])
@auth.require_user
def set_recipe_selected(plan_id, recipe_id):
    client = auth.db()
    selected = request.form.get("selected") == "true"
    (
        client.table("plan_recipes")
        .update({"selected": selected})
        .eq("plan_id", plan_id)
        .eq("recipe_id", recipe_id)
        .execute()
    )
    return redirect(f"/plans/{plan_id}")
