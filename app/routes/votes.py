import io
import secrets

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   send_file, session, url_for)
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length
import qrcode
from sqlalchemy import func

from app.extensions import db
from app.lib.votes import VALID_HEX, VOTE_COLORS, tally_votes
from app.models import MealPlan, PlanShare, PlanVote, Recipe

bp = Blueprint('votes', __name__)

COLOR_LABELS = dict(VOTE_COLORS)


class GuestVoteForm(FlaskForm):
    voter_name = StringField('Your name', validators=[DataRequired(), Length(max=60)])
    # Rendered as preset-swatch radios in the template; membership checked server-side.
    color = StringField(validators=[DataRequired()])
    submit = SubmitField('Cast vote')


def _owner_plan_or_redirect(plan_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return None
    return plan


@bp.route('/plans/<int:plan_id>/share', methods=['POST'])
@login_required
def enable_share(plan_id):
    plan = _owner_plan_or_redirect(plan_id)
    if plan is None:
        return redirect(url_for('plans.index'))
    share = PlanShare.query.filter_by(plan_id=plan.id).first()
    if share:
        flash('Guest voting is already on.', 'info')
    else:
        share = PlanShare(plan_id=plan.id, token=secrets.token_urlsafe(32))
        db.session.add(share)
        db.session.commit()
        flash('Guest voting is on — scan the QR code or send the link.', 'success')
    return redirect(url_for('plans.view', plan_id=plan.id))


@bp.route('/plans/<int:plan_id>/share/delete', methods=['POST'])
@login_required
def disable_share(plan_id):
    plan = _owner_plan_or_redirect(plan_id)
    if plan is None:
        return redirect(url_for('plans.index'))
    share = PlanShare.query.filter_by(plan_id=plan.id).first()
    if share:
        db.session.delete(share)
    db.session.commit()
    flash('Guest voting turned off — the old link no longer works.', 'success')
    return redirect(url_for('plans.view', plan_id=plan.id))


@bp.route('/vote/qr/<token>.png')
def qr(token):
    share = PlanShare.query.filter_by(token=token).first_or_404()
    vote_url = url_for('votes.guest', token=share.token, _external=True)
    img = qrcode.make(vote_url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png', download_name='weekly-menu-vote.png')


@bp.route('/vote/<token>', methods=['GET', 'POST'])
def guest(token):
    share = PlanShare.query.filter_by(token=token).first()
    plan = share.plan if share else None
    if plan is None:
        abort(404)

    recipes = Recipe.query.filter_by(user_id=plan.user_id).order_by(Recipe.title).all()
    menu_ids = {e.recipe_id for e in plan.entries}
    suggestions = [r for r in recipes if r.id in menu_ids]
    others = [r for r in recipes if r.id not in menu_ids]
    allowed_ids = {r.id for r in recipes}

    form = GuestVoteForm()
    if form.validate_on_submit():
        name = form.voter_name.data.strip()
        color = form.color.data
        pick = (request.form.get('recipe_id') or request.form.get('other_recipe_id') or '').strip()
        try:
            recipe_id = int(pick)
        except ValueError:
            recipe_id = 0
        if color not in VALID_HEX:
            flash('Pick a color.', 'danger')
        elif recipe_id not in allowed_ids:
            flash('Choose one of the recipes to vote for.', 'danger')
        else:
            for old in PlanVote.query.filter(
                    PlanVote.plan_id == plan.id,
                    func.lower(PlanVote.voter_name) == name.lower()).all():
                db.session.delete(old)
            db.session.add(PlanVote(plan_id=plan.id, recipe_id=recipe_id,
                                    voter_name=name, color=color))
            db.session.commit()
            session['voted:' + token] = True
            session['voter:' + token] = {'name': name, 'color': color, 'recipe_id': recipe_id}
            recipe = db.session.get(Recipe, recipe_id)
            title = recipe.title if recipe else 'that recipe'
            flash(f'Vote recorded for "{title}" — you can change it any time.', 'success')
            return redirect(url_for('votes.guest', token=token))

    previous = session.get('voter:' + token)
    show_results = bool(session.get('voted:' + token))
    if previous and request.method == 'GET':
        form.voter_name.data = previous['name']
        form.color.data = previous['color']
    return render_template(
        'votes/ballot.html',
        form=form,
        plan=plan,
        suggestions=suggestions,
        others=others,
        colors=VOTE_COLORS,
        color_labels=COLOR_LABELS,
        previous=previous,
        show_results=show_results,
        tally=tally_votes(plan.id) if show_results else [],
    )
