"""Cookbook list/detail/members pages and related mutations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, redirect, render_template, request

from .. import auth
from ..queries import (
    get_cookbook,
    get_invites,
    get_members,
    get_plans,
    get_recipes,
    get_role,
    invite_is_active,
    list_cookbooks,
)
from ..supabase import SupabaseError

bp = Blueprint("cookbooks", __name__)


@bp.route("/cookbooks")
@auth.require_user
def cookbooks_list():
    client = auth.db()
    uid = auth.user_id()
    items = list_cookbooks(client, uid)
    return render_template("cookbooks/list.html", cookbooks=items)


@bp.route("/cookbooks", methods=["POST"])
@auth.require_user
def create_cookbook():
    client = auth.db()
    uid = auth.user_id()
    name = (request.form.get("name") or "").strip()
    if not name:
        raise SupabaseError("Give the cookbook a name.")
    description = (request.form.get("description") or "").strip() or None
    is_private = request.form.get("is_private") in ("on", "true", "1")
    created = (
        client.table("cookbooks")
        .insert(
            {"owner_id": uid, "name": name, "description": description, "is_private": is_private}
        )
        .select("id")
        .single()
        .execute()
    )
    return redirect(f"/cookbooks/{created['id']}")


@bp.route("/cookbooks/<cookbook_id>")
@auth.require_user
def cookbook_detail(cookbook_id):
    client = auth.db()
    uid = auth.user_id()
    cookbook = get_cookbook(client, cookbook_id)
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(client, cookbook_id)
    recipes = get_recipes(client, cookbook_id)
    plans = get_plans(client, cookbook_id)
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
    client = auth.db()
    name = (request.form.get("name") or "").strip()
    if not name:
        raise SupabaseError("Give the cookbook a name.")
    description = (request.form.get("description") or "").strip() or None
    is_private = request.form.get("is_private") in ("on", "true", "1")
    (
        client.table("cookbooks")
        .update({"name": name, "description": description, "is_private": is_private})
        .eq("id", cookbook_id)
        .execute()
    )
    return redirect(f"/cookbooks/{cookbook_id}")


@bp.route("/cookbooks/<cookbook_id>/delete", methods=["POST"])
@auth.require_user
def delete_cookbook(cookbook_id):
    client = auth.db()
    client.table("cookbooks").delete().eq("id", cookbook_id).execute()
    return redirect("/cookbooks")


@bp.route("/cookbooks/<cookbook_id>/members")
@auth.require_user
def members(cookbook_id):
    client = auth.db()
    cookbook = get_cookbook(client, cookbook_id)
    if not cookbook:
        return render_template("not_found.html"), 404
    role = get_role(client, cookbook_id)
    if not role:
        return render_template("not_found.html"), 404
    member_rows = get_members(client, cookbook_id)
    invites = get_invites(client, cookbook_id)
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
    client = auth.db()
    user_id = request.form.get("user_id") or ""
    role = request.form.get("role") or "viewer"
    if role not in ("viewer", "editor"):
        role = "viewer"
    (
        client.table("cookbook_members")
        .update({"role": role})
        .eq("cookbook_id", cookbook_id)
        .eq("user_id", user_id)
        .execute()
    )
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/cookbooks/<cookbook_id>/members/remove", methods=["POST"])
@auth.require_user
def remove_member(cookbook_id):
    client = auth.db()
    user_id = request.form.get("user_id") or ""
    (
        client.table("cookbook_members")
        .delete()
        .eq("cookbook_id", cookbook_id)
        .eq("user_id", user_id)
        .execute()
    )
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/invites/create", methods=["POST"])
@auth.require_user
def create_invite():
    client = auth.db()
    uid = auth.user_id()
    cookbook_id = request.form.get("cookbook_id") or ""
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
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    (
        client.table("invites")
        .insert(
            {
                "cookbook_id": cookbook_id,
                "kind": kind,
                "role": role if kind == "member" else None,
                "plan_id": plan_id,
                "created_by": uid,
                "expires_at": expires_at,
            }
        )
        .execute()
    )
    if plan_id:
        return redirect(f"/plans/{plan_id}")
    return redirect(f"/cookbooks/{cookbook_id}/members")


@bp.route("/invites/<invite_id>/revoke", methods=["POST"])
@auth.require_user
def revoke_invite(invite_id):
    client = auth.db()
    cookbook_id = request.form.get("cookbook_id") or ""
    (
        client.table("invites")
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", invite_id)
        .execute()
    )
    if cookbook_id:
        return redirect(f"/cookbooks/{cookbook_id}/members")
    return redirect("/cookbooks")
