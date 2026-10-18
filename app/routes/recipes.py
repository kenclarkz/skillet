from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, SubmitField,
                     FileField, HiddenField, URLField)
from wtforms.validators import DataRequired, Length, Optional, NumberRange, URL
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from app.extensions import db
from app.models import Recipe, Ingredient
from app.lib.ingredients import parse_ingredient_text
from app.lib.importer import (ImportBlocked, ImportFailed, download_image,
                              fetch_html, parse_recipe_html)

bp = Blueprint('recipes', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def store_uploaded_photo(file_storage):
    """Save an uploaded file to the media folder and return its stored name."""
    if not file_storage or not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    name = f"{datetime.utcnow().timestamp():.0f}_{filename}"
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], name))
    return name


def fetch_remote_photo(url):
    """Download an imported recipe photo into the media folder."""
    if not url or not url.startswith(('http://', 'https://')):
        return None
    try:
        ext, blob = download_image(url)
    except (ImportBlocked, ImportFailed):
        return None
    name = f"{datetime.utcnow().timestamp():.0f}_imported.{ext}"
    with open(os.path.join(current_app.config['UPLOAD_FOLDER'], name), 'wb') as fh:
        fh.write(blob)
    return name

class RecipeForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    prep_minutes = IntegerField('Prep minutes', validators=[Optional(), NumberRange(min=0)])
    cook_minutes = IntegerField('Cook minutes', validators=[Optional(), NumberRange(min=0)])
    servings = IntegerField('Servings', validators=[DataRequired(), NumberRange(min=1, max=100)])
    source_url = StringField('Source URL', validators=[Optional(), Length(max=500)])
    tags = StringField('Tags (comma separated)', validators=[Optional(), Length(max=200)])
    ingredients = TextAreaField('Ingredients (one per line)', validators=[DataRequired()])
    instructions = TextAreaField('Instructions (one per line)', validators=[DataRequired()])
    photo = FileField('Photo', validators=[Optional()])
    photo_url = HiddenField('Photo URL')
    submit = SubmitField('Save')


class ImportForm(FlaskForm):
    url = URLField('Recipe URL', validators=[DataRequired(), URL(require_tld=False), Length(max=2000)])
    submit = SubmitField('Fetch recipe')

@bp.route('/recipes')
@login_required
def index():
    recipes = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.created_at.desc()).all()
    return render_template('recipes/index.html', recipes=recipes)

@bp.route('/recipes/new', methods=['GET', 'POST'])
@login_required
def new():
    form = RecipeForm()
    if form.validate_on_submit():
        recipe = Recipe(
            user_id=current_user.id,
            title=form.title.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            prep_minutes=form.prep_minutes.data,
            cook_minutes=form.cook_minutes.data,
            servings=form.servings.data or 4,
            source_url=form.source_url.data.strip() if form.source_url.data else None,
            tags=form.tags.data.strip() if form.tags.data else '',
            instructions='\n'.join(line.strip() for line in form.instructions.data.splitlines() if line.strip())
        )
        # photo: uploaded file wins, else download the imported one
        recipe.photo_path = store_uploaded_photo(form.photo.data)
        if not recipe.photo_path and form.photo_url.data:
            recipe.photo_path = fetch_remote_photo(form.photo_url.data)
        db.session.add(recipe)
        db.session.flush()
        for line in parse_ingredient_text(form.ingredients.data):
            db.session.add(Ingredient(recipe_id=recipe.id, name=line['name'],
                                      qty=line['qty'], unit=line['unit'], note=line['note']))
        db.session.commit()
        flash('Recipe created.', 'success')
        return redirect(url_for('recipes.view', recipe_id=recipe.id))
    return render_template('recipes/new.html', form=form, edit=False)

@bp.route('/recipes/<int:recipe_id>')
@login_required
def view(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('recipes.index'))
    instr = [line for line in (recipe.instructions or '').splitlines() if line.strip()]
    return render_template('recipes/view.html', recipe=recipe, instructions=instr)

@bp.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('recipes.index'))
    form = RecipeForm(obj=recipe)
    if not form.is_submitted():
        form.ingredients.data = '\n'.join(
            f"{(i.qty + ' ' if i.qty else '')}{(i.unit + ' ' if i.unit else '')}{i.name}"
            for i in recipe.ingredients
        )
    if form.validate_on_submit():
        recipe.title = form.title.data.strip()
        recipe.description = form.description.data.strip() if form.description.data else None
        recipe.prep_minutes = form.prep_minutes.data
        recipe.cook_minutes = form.cook_minutes.data
        recipe.servings = form.servings.data or 4
        recipe.source_url = form.source_url.data.strip() if form.source_url.data else None
        recipe.tags = form.tags.data.strip() if form.tags.data else ''
        recipe.instructions = '\n'.join(line.strip() for line in form.instructions.data.splitlines() if line.strip())
        uploaded = store_uploaded_photo(form.photo.data)
        if uploaded:
            recipe.photo_path = uploaded
        elif form.photo_url.data:
            downloaded = fetch_remote_photo(form.photo_url.data)
            if downloaded:
                recipe.photo_path = downloaded
        recipe.updated_at = datetime.utcnow()
        Ingredient.query.filter_by(recipe_id=recipe.id).delete()
        for line in parse_ingredient_text(form.ingredients.data):
            db.session.add(Ingredient(recipe_id=recipe.id, name=line['name'],
                                      qty=line['qty'], unit=line['unit'], note=line['note']))
        db.session.commit()
        flash('Recipe updated.', 'success')
        return redirect(url_for('recipes.view', recipe_id=recipe.id))
    return render_template('recipes/edit.html', form=form, edit=True, recipe=recipe)

@bp.route('/recipes/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('Not authorized.', 'danger')
        return redirect(url_for('recipes.index'))
    db.session.delete(recipe)
    db.session.commit()
    flash('Recipe deleted.', 'success')
    return redirect(url_for('recipes.index'))


@bp.route('/recipes/import', methods=['GET', 'POST'])
@login_required
def import_url():
    form = ImportForm()
    if form.is_submitted():
        # Tolerate pasted URLs: surrounding spaces/quotes and a missing scheme.
        raw = (form.url.data or '').strip().strip('\'"“”‘’')
        if raw and '://' not in raw:
            raw = 'https://' + raw
        form.url.data = raw
    if form.validate_on_submit():
        try:
            final_url, html = fetch_html(form.url.data)
            draft = parse_recipe_html(html, final_url)
        except ImportBlocked as exc:
            flash(str(exc), 'danger')
            return render_template('recipes/import.html', form=form)
        except ImportFailed as exc:
            flash(str(exc), 'danger')
            return render_template('recipes/import.html', form=form)

        recipe_form = RecipeForm()
        recipe_form.title.data = draft['title']
        recipe_form.description.data = draft['description']
        recipe_form.prep_minutes.data = draft['prep_minutes']
        recipe_form.cook_minutes.data = draft['cook_minutes']
        recipe_form.servings.data = draft['servings']
        recipe_form.source_url.data = draft['source_url']
        recipe_form.tags.data = ', '.join(draft['tags'])
        recipe_form.ingredients.data = '\n'.join(draft['ingredients'])
        recipe_form.instructions.data = '\n'.join(draft['instructions'])
        recipe_form.photo_url.data = draft['photo_url'] or ''
        return render_template('recipes/new.html', form=recipe_form, edit=False, imported=True)
    return render_template('recipes/import.html', form=form)
