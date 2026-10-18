from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from app.extensions import db
from app.models import MealPlan, PantryItem

bp = Blueprint('grocery', __name__)

class PantryForm(FlaskForm):
    name = StringField('Add staple', validators=[DataRequired()])
    submit = SubmitField('Add')

def norm(s):
    return (s or '').strip().lower()

@bp.route('/grocery')
@login_required
def index():
    pantry = PantryItem.query.filter_by(user_id=current_user.id).order_by(PantryItem.name).all()
    form = PantryForm()
    return render_template('grocery/pantry.html', pantry=pantry, form=form)

@bp.route('/grocery/pantry/add', methods=['POST'])
@login_required
def pantry_add():
    form = PantryForm()
    if form.validate_on_submit():
        n = form.name.data.strip()
        pn = norm(n)
        if pn and not PantryItem.query.filter_by(user_id=current_user.id, normalized_name=pn).first():
            db.session.add(PantryItem(user_id=current_user.id, name=n, normalized_name=pn))
            db.session.commit()
            flash('Added to pantry.', 'success')
    return redirect(url_for('grocery.index'))

@bp.route('/grocery/pantry/<int:item_id>/remove', methods=['POST'])
@login_required
def pantry_remove(item_id):
    item = PantryItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('grocery.index'))
    db.session.delete(item)
    db.session.commit()
    flash('Removed.', 'success')
    return redirect(url_for('grocery.index'))

@bp.route('/grocery/<int:plan_id>')
@login_required
def list(plan_id):
    plan = MealPlan.query.get_or_404(plan_id)
    if plan.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('plans.index'))

    pantry_set = {p.normalized_name for p in current_user.pantry_items}
    source = []
    for entry in plan.entries:
        recipe = entry.recipe
        if not recipe:
            continue
        for ing in recipe.ingredients:
            source.append({
                'name': ing.name or '',
                'qty': ing.qty,
                'unit': ing.unit or '',
                'recipeId': str(recipe.id),
                'recipeTitle': recipe.title,
            })

    from app.lib.grocery import aggregate
    items = aggregate(source, pantry_set)
    return render_template('grocery/list.html', plan=plan, items=items)
