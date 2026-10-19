from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Optional
from app.extensions import db
from app.models import Recipe, MealPlan, PlanEntry, PlanCandidate
from datetime import date, timedelta

bp = Blueprint('plans', __name__)

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

MAX_CHOICES_PER_DAY = 3

class PlanForm(FlaskForm):
    week_start = StringField('Week start (YYYY-MM-DD)', validators=[DataRequired()])
    title = StringField('Title', validators=[Optional()])
    submit = SubmitField('Create plan')

@bp.route('/plans')
@login_required
def index():
    plans = MealPlan.query.filter_by(user_id=current_user.id).order_by(MealPlan.week_start.desc()).all()
    return render_template('plans/index.html', plans=plans)

@bp.route('/plans/new', methods=['GET', 'POST'])
@login_required
def new():
    form = PlanForm()
    if form.validate_on_submit():
        try:
            ws = date.fromisoformat(form.week_start.data.strip())
        except Exception:
            flash('Invalid date.', 'danger')
            return redirect(url_for('plans.new'))
        plan = MealPlan(user_id=current_user.id, week_start=ws, title=form.title.data.strip() or None)
        db.session.add(plan)
        db.session.commit()
        flash('Plan created.', 'success')
        return redirect(url_for('plans.view', plan_id=plan.id))
    # default to next monday
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return render_template('plans/new.html', form=form, default=monday.isoformat())

@bp.route('/plans/<int:plan_id>')
@login_required
def view(plan_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    recipes = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.title).all()
    # build grid: official entries and pending choices, grouped by day
    entries = {e.day_of_week: e for e in plan.entries}
    choices = {}
    for c in sorted(plan.candidates, key=lambda c: (c.day_of_week, c.created_at, c.id)):
        choices.setdefault(c.day_of_week, []).append(c)
    return render_template('plans/view.html', plan=plan, recipes=recipes, days=DAYS,
                           entries=entries, choices=choices)

@bp.route('/plans/<int:plan_id>/assign', methods=['POST'])
@login_required
def assign(plan_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    try:
        day = int(request.form.get('day_of_week'))
    except (TypeError, ValueError):
        flash('Invalid day.', 'danger')
        return redirect(url_for('plans.view', plan_id=plan.id))
    if day not in range(7):
        flash('Invalid day.', 'danger')
        return redirect(url_for('plans.view', plan_id=plan.id))

    recipe_ids = request.form.getlist('recipe_ids', type=int)
    if not recipe_ids:
        flash('Pick at least one recipe to put up.', 'danger')
        return redirect(url_for('plans.view', plan_id=plan.id))

    owned = Recipe.query.filter(
        Recipe.id.in_(recipe_ids),
        Recipe.user_id == current_user.id,
    ).all()
    if not owned:
        flash('No valid recipes selected.', 'danger')
        return redirect(url_for('plans.view', plan_id=plan.id))

    existing_ids = {
        c.recipe_id for c in PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=day).all()
    }
    slots = MAX_CHOICES_PER_DAY - len(existing_ids)
    if slots <= 0:
        flash(f'{DAYS[day]} already has {MAX_CHOICES_PER_DAY} choices.', 'warning')
        return redirect(url_for('plans.view', plan_id=plan.id))

    added = 0
    for r in owned:
        if added >= slots:
            break
        if r.id in existing_ids:
            continue
        db.session.add(PlanCandidate(plan_id=plan.id, recipe_id=r.id, day_of_week=day))
        existing_ids.add(r.id)
        added += 1

    if added == 0:
        flash('Those choices are already up for that day.', 'warning')
    else:
        db.session.commit()
        total = len(existing_ids)
        flash(f'Added {added} choice{"s" if added != 1 else ""} for {DAYS[day]} — {total}/{MAX_CHOICES_PER_DAY} up. Cast your vote to make one official.', 'success')
    return redirect(url_for('plans.view', plan_id=plan.id))

@bp.route('/plans/<int:plan_id>/vote/<int:candidate_id>', methods=['POST'])
@login_required
def vote(plan_id, candidate_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    candidate = PlanCandidate.query.get_or_404(candidate_id)
    if candidate.plan_id != plan.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    day = candidate.day_of_week

    if candidate.votes > 0:
        # un-vote: the day goes back to open voting and is no longer official
        candidate.votes = 0
        PlanEntry.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
        db.session.commit()
        flash(f'Vote removed — {DAYS[day]} is open again.', 'info')
        return redirect(url_for('plans.view', plan_id=plan.id))

    # cast the vote: with all votes in, the top choice becomes official
    for c in PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=day).all():
        c.votes = 1 if c.id == candidate.id else 0
    PlanEntry.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
    db.session.add(PlanEntry(plan_id=plan.id, recipe_id=candidate.recipe_id, day_of_week=day))
    db.session.commit()
    title = candidate.recipe.title if candidate.recipe else 'the choice'
    flash(f'{title} is official for {DAYS[day]} — its ingredients are on the grocery list.', 'success')
    return redirect(url_for('plans.view', plan_id=plan.id))

@bp.route('/plans/<int:plan_id>/clear/<int:day>', methods=['POST'])
@login_required
def clear(plan_id, day):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    PlanEntry.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
    PlanCandidate.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
    db.session.commit()
    return redirect(url_for('plans.view', plan_id=plan.id))
