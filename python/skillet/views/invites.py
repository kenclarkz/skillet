"""Member invites and public guest voting (invite + ballot + cast vote)."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from .. import auth
from ..supabase import SupabaseError

bp = Blueprint("invites", __name__)

GUEST_KEY_MAX = 80
VOTER_NAME_MAX = 60


@bp.route("/invite/<token>")
@auth.require_user
def accept_invite(token):
    client = auth.db()
    try:
        cookbook_id = client.rpc("join_cookbook", {"p_invite_token": token})
    except SupabaseError:
        return render_template("invite/invalid.html")
    if not cookbook_id or not isinstance(cookbook_id, str):
        return render_template("invite/invalid.html")
    return render_template("invite/accepted.html", cookbook_id=cookbook_id)


@bp.route("/vote/<token>")
def vote_page(token):
    return render_template("vote.html", token=token)


@bp.route("/api/vote/ballot")
def vote_ballot():
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"error": "Missing invite token."}), 400
    voter_key = (request.args.get("voter_key") or "").strip() or None
    client = auth.anon_db()
    try:
        ballot = client.rpc(
            "get_vote_ballot",
            {"p_invite_token": token, "p_voter_key": voter_key},
            auth=False,
        )
    except SupabaseError as exc:
        return jsonify({"error": exc.message}), 400
    return jsonify({"ballot": ballot or {}})


@bp.route("/api/vote/cast", methods=["POST"])
def vote_cast():
    data = request.get_json(silent=True) or {}
    plan_id = data.get("plan_id")
    recipe_id = data.get("recipe_id")
    voter_key = (data.get("voter_key") or "").strip()
    voter_name = (data.get("voter_name") or "").strip()
    token = (data.get("invite_token") or "").strip()
    try:
        value = int(data.get("value"))
    except (TypeError, ValueError):
        value = 0
    if value not in (-1, 0, 1):
        return jsonify({"error": "invalid vote value"}), 400
    if not plan_id or not recipe_id:
        return jsonify({"error": "Missing plan or recipe."}), 400
    if not voter_key or len(voter_key) > GUEST_KEY_MAX:
        return jsonify({"error": "Invalid voter key."}), 400
    if not voter_name or len(voter_name) > VOTER_NAME_MAX:
        return jsonify({"error": "Add your name before voting."}), 400
    client = auth.anon_db()
    try:
        client.rpc(
            "cast_vote",
            {
                "p_plan_id": plan_id,
                "p_recipe_id": recipe_id,
                "p_voter_key": voter_key,
                "p_voter_name": voter_name,
                "p_value": value,
                "p_invite_token": token or None,
            },
            auth=False,
        )
    except SupabaseError as exc:
        return jsonify({"error": exc.message}), 400
    return jsonify({"ok": True})


@bp.route("/api/qr")
def api_qr():
    """Small SVG QR generator used by invite/vote pages (also embedded server-side)."""
    from ..qr import qr_svg

    value = (request.args.get("value") or "").strip()
    size = min(400, max(64, int(request.args.get("size") or 160)))
    if not value:
        return jsonify({"error": "Missing value."}), 400
    return qr_svg(value, size), 200, {"Content-Type": "image/svg+xml"}
