from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from app.extensions import db
from app.models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember me')
    submit = SubmitField('Sign in')

class SignupForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    display_name = StringField('Display name', validators=[Length(max=60)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password2 = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create account')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('recipes.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))
        from flask_login import login_user
        login_user(user, remember=form.remember.data)
        next_page = request.args.get('next')
        if not next_page or next_page.startswith('/'):
            next_page = url_for('recipes.index')
        flash('Welcome back!', 'success')
        return redirect(next_page)
    return render_template('auth/login.html', form=form)

@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('recipes.index'))
    form = SignupForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('auth.signup'))
        user = User(email=form.email.data.lower(), display_name=form.display_name.data or form.email.data.split('@')[0])
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please sign in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/signup.html', form=form)

@bp.route('/logout')
def logout():
    from flask_login import logout_user
    if current_user.is_authenticated:
        logout_user()
        flash('You have been logged out.', 'info')
    return redirect(url_for('main.home'))
