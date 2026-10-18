"""Cookbook list/detail/members pages and related mutations."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, g, redirect, render_template, request

from .. import auth
from ..db import db
from ..errors import AppError
from ..models import Cookbook, CookbookMember, Invite, utcnow
from ..queries import (
    get_cookbook,
    get_invites,
    get_members,
    get_plans,
    get_recipes,
    get_role,
    invite_is_active,
    list_cookbooks,
    require_cookbook_role,
    require_visible_cookbook,
)

bp = Blueprint("cookbooks", __name__)


@bp.route("/cookbooks")
@auth.require_user
def cookbooks_list():
    uid = auth.user_id()
    items = list_cookbooks(uid)
    return render_template("cookbooks/list.html", cookbooks=items)


@bp.route("/cookbooks", methods=["POST"])
@auth.require_user
def create_cookbook():
    uid = auth.user_id()
    name = (request.form.get("name") or "").strip()
    if not name:
        raise AppError("Give the cookbook a name.")
    description = (request.form.get("description") or "").strip() or None
    is_private = request.form.get("is_private") in ("on", "true", "1")
    cookbook = Cookbook(owner_id=uid, name=name[:120], description=description, is_private=is_private)
    db.session.add(cookbook)
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook.id}")


@bp.route("/cookbooks/<cookbook_id>")
@auth.require_user
def cookbook_detail(cookbook_id):
    uid = auth.user_id()
    cookbook = get_cookbook(uid, cookbook_id)
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(uid, cookbook_id)
    recipes = get_recipes(uid, cookbook_id)
    plans = get_plans(uid, cookbook_id)
    this_week = next((p for p in plans if p.get("status") == "open"), plans[0] if plans else None)
    return render_template(
        "cookbooks/detail.html",
        cookbook=cookbook,
        role=role,
        editable=role in ("owner", "editor"),
        recipes=recipes,
        plans=plans,
        this_week=this_week,
        is_owner=role == "owner",
    )


@bp.route("/cookbooks/<cookbook_id>/update", methods=["POST"])
@auth.require_user
def update_cookbook(cookbook_id):
    uid = auth.user_id()
    cookbook = require_cookbook_role(uid, cookbook_id, roles=("owner",))
    name = (request.form.get("name") or "").strip()
    if not name:
        raise AppError("Give the cookbook a name.")
    cookbook.name = name[:120]
    cookbook.description = (request.form.get("description") or "").strip() or None
    cookbook.is_private = request.form.get("is_private") in ("on", "true", "1")
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook_id}")


@bp.route("/cookbooks/<cookbook_id>/delete", methods=["POST"])
@auth.require_user
def delete_cookbook(cookbook_id):
    uid = auth.user_id()
    require_cookbook_role(uid, cookbook_id, roles=("owner",))
    db.session.query(Cookbook).filter(Cookbook.id == cookbook_id).delete()
    db.session.commit()
    return redirect("/cookbooks")


@bp.route("/cookbooks/<cookbook_id>/members")
@auth.require_user
def members(cookbook_id):
    uid = auth.user_id()
    cookbook = get_cookbook(uid, cookbook_id)
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(uid, cookbook_id)
    if not role:
        return render_template("not_found.html"), 404
    member_rows = get_members(uid, cookbook_id)
    invites = get_invites(uid, cookbook_id)
    active_invites = [i for i in invites if invite_is_active(i)]
    return render_template(
        "cookbooks/members.html",
        cookbook=cookbook,
        role=role,
        is_owner=role == "owner",
        members=member_rows,
        invites=invites,
        active_invites=active_invites,
    )


@bp.route("/cookbooks/<cookbook_id>/members/update-role", methods=["POST"])
@auth.require_user
def update_member_role(cookbook_id):
    uid = auth.user_id()
    require_cookbook_role(uid, cookbook_id, roles=("owner",))
    user_id = request.form.get("user_id") or ""
    role = request.form.get("role") or "viewer"
    if role not in ("viewer", "editor"):
        role = "viewer"
    member = db.session.get(CookbookMember, {"cookbook_id": cookbook_id, "user_id": user_id})
    if member is None:
        raise AppError("Member not found.", 404)
    member.role = role
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/cookbooks/<cookbook_id>/members/remove", methods=["POST"])
@auth.require_user
def remove_member(cookbook_id):
    uid = auth.user_id()
    target = request.form.get("user_id") or ""
    role = get_role(uid, cookbook_id)
    if role != "owner" and target != uid:
        raise AppError("You do not have permission to do that.", 403)
    db.session.query(CookbookMember).filter(
        CookbookMember.cookbook_id == cookbook_id, CookbookMember.user_id == target
    ).delete()
    db.session.commit()
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/invites/create", methods=["POST"])
@auth.require_user
def create_invite():
    uid = auth.user_id()
    cookbook_id = request.form.get("cookbook_id") or ""
    require_cookbook_role(uid, cookbook_id, roles=("owner",))
    kind = request.form.get("kind") or "member"
    if kind not in ("member", "vote"):
        kind = "member"
    role = request.form.get("role") or "viewer"
    if role not in ("viewer", "editor"):
        role = "viewer"
    plan_id = request.form.get("plan_id") or None
    if kind == "member":
        plan_id = None
    try:
        days = int(request.form.get("expires_days") or 0)
    except ValueError:
        days = 0
    expires_at = None
    if days > 0:
        expires_at = utcnow() + timedelta(days=days)
    invite = Invite(
        cookbook_id=cookbook_id,
        kind=kind,
        role=role if kind == "member" else None,
        plan_id=plan_id,
        created_by=uid,
        expires_at=expires_at,
    )
    db.session.add(invite)
    db.session.commit()
    if plan_id:
        return redirect(f"/plans/{plan_id}")
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/invites/<invite_id>/revoke", methods=["POST"])
@auth.require_user
def revoke_invite(invite_id):
    uid = auth.user_id()
    invite = db.session.get(Invite, invite_id)
    if invite is None:
        raise AppError("Invite not found.", 404)
    require_cookbook_role(uid, invite.cookbook_id, roles=("owner",))
    invite.revoked_at = utcnow()
    db.session.commit()
    cookbook_id = request.form.get("cookbook_id") or ""
    if cookbook_id:
        return redirect(f"/cookbooks/{cookbook_id}/members")
    return redirect("/cookbooks")
