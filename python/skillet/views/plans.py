"""Week plans, voting ballots, and plan mutations."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from flask import Blueprint, redirect, render_template, request

from .. import auth
from ..db import db
from ..errors import AppError
from ..models import PlanRecipe, WeeklyPlan
from ..queries import (
    build_grocery_list,
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
    require_plan,
    select_top_voted,
)

bp = Blueprint("plans", __name__)


@bp.route("/plans")
@auth.require_user
def plans_list():
    uid = auth.user_id()
    plans = get_plans(uid)
    cookbooks = list_cookbooks(uid)
    names = {c["id"]: c["name"] for c in cookbooks}
    return render_template("plans/list.html", plans=plans, cookbook_names=names)


@bp.route("/plans/create", methods=["POST"])
@auth.require_user
def create_plan():
    from ..queries import require_cookbook_role

    uid = auth.user_id()
    cookbook_id = (request.form.get("cookbook_id") or "").strip()
    week_raw = (request.form.get("week_start") or "").strip() or next_monday()
    title = (request.form.get("title") or "").strip() or None
    if not cookbook_id:
        raise AppError("Choose a cookbook.")
    require_cookbook_role(uid, cookbook_id)
    try:
        week_start = date.fromisoformat(week_raw)
    except ValueError:
        raise AppError("Give the week a valid start date (YYYY-MM-DD).") from None
    plan = (
        db.session.query(WeeklyPlan)
        .filter(WeeklyPlan.cookbook_id == cookbook_id, WeeklyPlan.week_start == week_start)
        .one_or_none()
    )
    if plan is None:
        plan = WeeklyPlan(cookbook_id=cookbook_id, week_start=week_start, title=title, created_by=uid)
        db.session.add(plan)
    else:
        plan.title = title
        plan.created_by = uid
    db.session.commit()
    return redirect(f"/plans/{plan.id}")


@bp.route("/plans/<plan_id>")
@auth.require_user
def plan_detail(plan_id):
    uid = auth.user_id()
    plan = get_plan(uid, plan_id)
    if not plan:
        return render_template("not_found.html"), 404
    cookbook = get_cookbook(uid, plan["cookbook_id"])
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(uid, plan["cookbook_id"])
    editable = role in ("owner", "editor")
    plan_recipes = get_plan_recipes(uid, plan_id)
    votes = get_votes(uid, plan_id)
    all_recipes = get_recipes(uid, plan["cookbook_id"])
    invites = get_invites(uid, plan["cookbook_id"])

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
    uid = auth.user_id()
    plan = db.session.get(WeeklyPlan, plan_id)
    if plan is None:
        return redirect("/plans")
    cookbook_id = request.form.get("cookbook_id") or plan.cookbook_id
    require_plan(uid, plan_id, editable=True)
    db.session.delete(plan)
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook_id}" if cookbook_id else "/plans")


@bp.route("/plans/<plan_id>/status", methods=["POST"])
@auth.require_user
def set_plan_status(plan_id):
    uid = auth.user_id()
    plan = require_plan(uid, plan_id, editable=True)
    status = request.form.get("status") or "open"
    if status not in ("open", "closed"):
        status = "open"
    plan.status = status
    db.session.commit()
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/select-top", methods=["POST"])
@auth.require_user
def select_top(plan_id):
    uid = auth.user_id()
    try:
        slots = int(request.form.get("slots") or 5)
    except ValueError:
        slots = 5
    select_top_voted(uid, plan_id, slots)
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/build-grocery", methods=["POST"])
@auth.require_user
def build_grocery(plan_id):
    build_grocery_list(auth.user_id(), plan_id)
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes", methods=["POST"])
@auth.require_user
def add_recipe_to_plan(plan_id):
    from ..queries import require_cookbook_role

    uid = auth.user_id()
    plan = require_plan(uid, plan_id, editable=True)
    recipe_id = request.form.get("recipe_id") or ""
    if not recipe_id:
        raise AppError("Choose a recipe.")
    require_cookbook_role(uid, plan.cookbook_id)
    existing = db.session.get(PlanRecipe, {"plan_id": plan_id, "recipe_id": recipe_id})
    if existing is None:
        db.session.add(PlanRecipe(plan_id=plan_id, recipe_id=recipe_id, added_by=uid))
    db.session.commit()
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes/<recipe_id>/remove", methods=["POST"])
@auth.require_user
def remove_recipe_from_plan(plan_id, recipe_id):
    uid = auth.user_id()
    require_plan(uid, plan_id, editable=True)
    db.session.query(PlanRecipe).filter(
        PlanRecipe.plan_id == plan_id, PlanRecipe.recipe_id == recipe_id
    ).delete()
    db.session.commit()
    return redirect(f"/plans/{plan_id}")


@bp.route("/plans/<plan_id>/recipes/<recipe_id>/selected", methods=["POST"])
@auth.require_user
def set_recipe_selected(plan_id, recipe_id):
    uid = auth.user_id()
    require_plan(uid, plan_id, editable=True)
    selected = request.form.get("selected") == "true"
    row = db.session.get(PlanRecipe, {"plan_id": plan_id, "recipe_id": recipe_id})
    if row is not None:
        row.selected = selected
        db.session.commit()
    return redirect(f"/plans/{plan_id}")
