from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Optional
from app.extensions import db
from app.models import Recipe, MealPlan, PlanEntry
from datetime import date, timedelta

bp = Blueprint('plans', __name__)

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

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
    # build grid
    entries = {e.day_of_week: e for e in plan.entries}
    return render_template('plans/view.html', plan=plan, recipes=recipes, days=DAYS, entries=entries)

@bp.route('/plans/<int:plan_id>/assign', methods=['POST'])
@login_required
def assign(plan_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    recipe_id = int(request.form.get('recipe_id'))
    day = int(request.form.get('day_of_week'))
    # remove existing for that slot? keep simple: replace if exists
    PlanEntry.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
    pe = PlanEntry(plan_id=plan.id, recipe_id=recipe_id, day_of_week=day)
    db.session.add(pe)
    db.session.commit()
    flash('Assigned.', 'success')
    return redirect(url_for('plans.view', plan_id=plan.id))

@bp.route('/plans/<int:plan_id>/clear/<int:day>', methods=['POST'])
@login_required
def clear(plan_id, day):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))
    PlanEntry.query.filter_by(plan_id=plan.id, day_of_week=day).delete()
    db.session.commit()
    return redirect(url_for('plans.view', plan_id=plan.id))
