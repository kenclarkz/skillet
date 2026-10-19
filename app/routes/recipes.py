from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, SubmitField,
                     FileField, HiddenField, URLField)
from wtforms.validators import DataRequired, Length, Optional, NumberRange, URL
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
from app.extensions import db
from app.models import Recipe, Ingredient, RecipeStep
from app.lib.ingredients import parse_ingredient_text
from app.lib.importer import (ImportBlocked, ImportFailed, download_image,
                              fetch_html, parse_recipe_html)
from app.lib.pdf_importer import parse_recipe_pdf

bp = Blueprint('recipes', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def store_uploaded_photo(file_storage, step_pos=None):
    """Save an uploaded file to the media folder and return its stored name."""
    if not file_storage or not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(file_storage.filename)
    ts = f"{datetime.utcnow().timestamp():.0f}"
    prefix = f"{ts}_step{step_pos}_" if step_pos is not None else f"{ts}_"
    name = f"{prefix}{filename}"
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], name))
    return name


def _delete_upload(name):
    """Best-effort removal of a stored media file."""
    if not name:
        return
    try:
        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], name))
    except OSError:
        pass


def _submitted_rows():
    """Step rows as the browser submitted them (all four lists stay aligned
    because every row contributes exactly one value of each kind)."""
    texts = request.form.getlist('step_text')
    ids = request.form.getlist('step_id')
    files = request.files.getlist('step_photo')
    remotes = request.form.getlist('step_photo_url')
    drops = set(request.form.getlist('step_drop_photo'))
    rows = []
    for i, text in enumerate(texts):
        sid = ids[i] if i < len(ids) else ''
        rows.append({
            'text': text.strip(),
            'sid': sid,
            'file': files[i] if i < len(files) else None,
            'remote': remotes[i] if i < len(remotes) else '',
            'drop': bool(sid) and sid in drops,
        })
    return rows


def _legacy_texts(form):
    """One step per line from the plain instructions textarea (posts from
    tests or integrations that never send step rows)."""
    return [ln.strip() for ln in (form.instructions.data or '').splitlines() if ln.strip()]


def _has_steps(form):
    return any(r['text'] for r in _submitted_rows()) or bool(_legacy_texts(form))


def _redisplay_rows(form, old_steps=()):
    """Rebuild form rows after a validation error, keeping existing photos."""
    submitted = _submitted_rows()
    if submitted:
        old_by_id = {str(s.id): s for s in old_steps}
        rows = []
        for r in submitted:
            photo_url = None
            old = old_by_id.get(r['sid'])
            if old is not None and old.photo_path and not r['drop']:
                photo_url = old.photo_path
            rows.append({'text': r['text'], 'photo_url': photo_url,
                         'sid': r['sid'], 'remote': r['remote']})
        return rows or [{'text': '', 'photo_url': None, 'sid': '', 'remote': ''}]
    return [{'text': t, 'photo_url': None, 'sid': '', 'remote': ''}
            for t in _legacy_texts(form)] or \
        [{'text': '', 'photo_url': None, 'sid': '', 'remote': ''}]


def save_steps(recipe, form, old_steps=None):
    """Rebuild the recipe's steps from the submitted rows.

    Each row keeps its photo (matched by step id) unless a new file was
    uploaded or the remove-photo box was checked. Falls back to the legacy
    instructions textarea when no step rows were posted.
    """
    old_steps = list(old_steps if old_steps is not None else recipe.steps)
    old_by_id = {str(s.id): s for s in old_steps}
    rows = _submitted_rows()
    if not any(r['text'] for r in rows):
        rows = [{'text': t, 'sid': '', 'file': None, 'drop': False, 'remote': ''}
                for t in _legacy_texts(form)]

    reused = set()
    plan = []
    for r in rows:
        if not r['text']:
            continue
        upload = None
        path = None
        remote = r.get('remote') or ''
        f = r['file']
        if f is not None and getattr(f, 'filename', '') and allowed_file(f.filename):
            upload = f
        else:
            old = old_by_id.get(r['sid'])
            if old is not None and old.photo_path and not r['drop']:
                path = old.photo_path
                reused.add(path)
            elif remote:
                path = resolve_photo_reference(remote)
        plan.append((r['text'], upload, path))

    for old in old_steps:
        if old.photo_path and old.photo_path not in reused:
            _delete_upload(old.photo_path)
        db.session.delete(old)
    db.session.flush()

    for pos, (text, upload, path) in enumerate(plan):
        if upload is not None:
            path = store_uploaded_photo(upload, step_pos=pos)
        db.session.add(RecipeStep(recipe=recipe, position=pos, text=text, photo_path=path))
    recipe.instructions = '\n'.join(text for text, _, _ in plan)


def _edit_row_source(recipe):
    if recipe.steps:
        return [{'text': s.text, 'photo_url': s.photo_path, 'sid': str(s.id),
                 'remote': ''} for s in recipe.steps]
    return [{'text': t, 'photo_url': None, 'sid': '', 'remote': ''} for t in
            (recipe.instructions or '').splitlines() if t.strip()] or \
        [{'text': '', 'photo_url': None, 'sid': '', 'remote': ''}]


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


def _store_import_image(image):
    """Write importer-provided (extension, bytes) into the media folder."""
    if not image:
        return None
    ext, blob = image
    name = f'{uuid.uuid4().hex}_imported.{ext}'
    with open(os.path.join(current_app.config['UPLOAD_FOLDER'], name), 'wb') as fh:
        fh.write(blob)
    return name


def _adopt_local_photo(name):
    """Return a stored filename only when it is a plain, local file.

    Imported drafts carry photo *references* until save time. PDF imports
    write their images out immediately, so those references are already
    local filenames. This guards against path traversal and missing files.
    """
    if not name or secure_filename(name) != name:
        return None
    if not os.path.isfile(os.path.join(current_app.config['UPLOAD_FOLDER'], name)):
        return None
    return name


def resolve_photo_reference(ref):
    """Turn a photo reference (remote URL or local upload name) into a name."""
    if not ref:
        return None
    if ref.startswith(('http://', 'https://')):
        return fetch_remote_photo(ref)
    return _adopt_local_photo(ref)

class RecipeForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    prep_minutes = IntegerField('Prep minutes', validators=[Optional(), NumberRange(min=0)])
    cook_minutes = IntegerField('Cook minutes', validators=[Optional(), NumberRange(min=0)])
    servings = IntegerField('Servings', validators=[DataRequired(), NumberRange(min=1, max=100)])
    source_url = StringField('Source URL', validators=[Optional(), Length(max=500)])
    tags = StringField('Tags (comma separated)', validators=[Optional(), Length(max=200)])
    ingredients = TextAreaField('Ingredients (one per line)', validators=[DataRequired()])
    instructions = TextAreaField('Instructions (one per line)', validators=[Optional()])
    photo = FileField('Photo', validators=[Optional()])
    photo_url = HiddenField('Photo URL')
    submit = SubmitField('Save')


class ImportForm(FlaskForm):
    url = URLField('Recipe URL', validators=[DataRequired(), URL(require_tld=False), Length(max=2000)])
    submit = SubmitField('Fetch recipe')


class PdfImportForm(FlaskForm):
    pdf = FileField('Recipe PDF', validators=[DataRequired()])
    submit_pdf = SubmitField('Import PDF')

@bp.route('/recipes')
@login_required
def index():
    recipes = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.created_at.desc()).all()
    return render_template('recipes/index.html', recipes=recipes)

@bp.route('/recipes/new', methods=['GET', 'POST'])
@login_required
def new():
    form = RecipeForm()
    step_rows = [{'text': '', 'photo_url': None, 'sid': '', 'remote': ''}]
    if form.validate_on_submit():
        if not _has_steps(form):
            flash('Add at least one cooking step.', 'danger')
        else:
            recipe = Recipe(
                user_id=current_user.id,
                title=form.title.data.strip(),
                description=form.description.data.strip() if form.description.data else None,
                prep_minutes=form.prep_minutes.data,
                cook_minutes=form.cook_minutes.data,
                servings=form.servings.data or 4,
                source_url=form.source_url.data.strip() if form.source_url.data else None,
                tags=form.tags.data.strip() if form.tags.data else '',
            )
            # photo: uploaded file wins, else download the imported one
            recipe.photo_path = store_uploaded_photo(form.photo.data)
            if not recipe.photo_path and form.photo_url.data:
                recipe.photo_path = resolve_photo_reference(form.photo_url.data)
            db.session.add(recipe)
            db.session.flush()
            save_steps(recipe, form)
            for line in parse_ingredient_text(form.ingredients.data):
                db.session.add(Ingredient(recipe_id=recipe.id, name=line['name'],
                                          qty=line['qty'], unit=line['unit'], note=line['note']))
            db.session.commit()
            flash('Recipe created.', 'success')
            return redirect(url_for('recipes.view', recipe_id=recipe.id))
        step_rows = _redisplay_rows(form)
    elif form.is_submitted():
        step_rows = _redisplay_rows(form)
    return render_template('recipes/new.html', form=form, edit=False, step_rows=step_rows)

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
    step_rows = _edit_row_source(recipe)
    if not form.is_submitted():
        form.ingredients.data = '\n'.join(
            f"{(i.qty + ' ' if i.qty else '')}{(i.unit + ' ' if i.unit else '')}{i.name}"
            for i in recipe.ingredients
        )
    if form.validate_on_submit():
        if not _has_steps(form):
            flash('Add at least one cooking step.', 'danger')
            step_rows = _redisplay_rows(form, recipe.steps)
        else:
            recipe.title = form.title.data.strip()
            recipe.description = form.description.data.strip() if form.description.data else None
            recipe.prep_minutes = form.prep_minutes.data
            recipe.cook_minutes = form.cook_minutes.data
            recipe.servings = form.servings.data or 4
            recipe.source_url = form.source_url.data.strip() if form.source_url.data else None
            recipe.tags = form.tags.data.strip() if form.tags.data else ''
            uploaded = store_uploaded_photo(form.photo.data)
            if uploaded:
                recipe.photo_path = uploaded
            elif form.photo_url.data:
                downloaded = resolve_photo_reference(form.photo_url.data)
                if downloaded:
                    recipe.photo_path = downloaded
            recipe.updated_at = datetime.utcnow()
            old_steps = list(recipe.steps)
            save_steps(recipe, form, old_steps=old_steps)
            Ingredient.query.filter_by(recipe_id=recipe.id).delete()
            for line in parse_ingredient_text(form.ingredients.data):
                db.session.add(Ingredient(recipe_id=recipe.id, name=line['name'],
                                          qty=line['qty'], unit=line['unit'], note=line['note']))
            db.session.commit()
            flash('Recipe updated.', 'success')
            return redirect(url_for('recipes.view', recipe_id=recipe.id))
    elif form.is_submitted():
        step_rows = _redisplay_rows(form, recipe.steps)
    return render_template('recipes/edit.html', form=form, edit=True, recipe=recipe,
                           step_rows=step_rows)

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


def _import_page(url_form=None, pdf_form=None):
    return render_template('recipes/import.html',
                           form=url_form or ImportForm(),
                           pdf_form=pdf_form or PdfImportForm())


def _render_imported(draft, step_refs, photo_ref):
    """Prefill the recipe form with an imported draft for review."""
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
    recipe_form.photo_url.data = photo_ref or ''
    rows = []
    for i, text in enumerate(draft['instructions']):
        ref = step_refs[i] if i < len(step_refs) else ''
        local = ref if ref and not ref.startswith(('http://', 'https://')) else None
        rows.append({'text': text, 'photo_url': local, 'sid': '', 'remote': ref})
    if not rows:
        rows = [{'text': '', 'photo_url': None, 'sid': '', 'remote': ''}]
    return render_template('recipes/new.html', form=recipe_form, edit=False,
                           imported=True, step_rows=rows,
                           warnings=draft.get('warnings') or [])


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
            return _import_page(url_form=form)
        except ImportFailed as exc:
            flash(str(exc), 'danger')
            return _import_page(url_form=form)
        return _render_imported(draft, draft.get('step_photos') or [],
                                draft['photo_url'] or '')
    return _import_page(url_form=form)


@bp.route('/recipes/import/pdf', methods=['GET', 'POST'])
@login_required
def import_pdf():
    """Import a recipe-card PDF and show the editable preview."""
    form = PdfImportForm()
    if form.validate_on_submit():
        try:
            draft = parse_recipe_pdf(form.pdf.data.read())
        except ImportFailed as exc:
            flash(str(exc), 'danger')
            return _import_page(pdf_form=form)
        photo_ref = _store_import_image(draft.get('photo'))
        step_refs = [_store_import_image(photo)
                     for photo in (draft.get('step_photos') or [])]
        return _render_imported(draft, step_refs, photo_ref or draft['photo_url'] or '')
    if form.is_submitted():
        flash('Choose a PDF recipe card to import.', 'danger')
    return _import_page(pdf_form=form)
