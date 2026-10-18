import os
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

# pbkdf2:sha256 is available on every Python build (scrypt needs OpenSSL support).
PASSWORD_HASH_METHOD = os.getenv('PASSWORD_HASH_METHOD', 'pbkdf2:sha256:600000')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(60), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    recipes = db.relationship('Recipe', backref='owner', lazy=True, cascade='all, delete-orphan')
    pantry_items = db.relationship('PantryItem', backref='owner', lazy=True, cascade='all, delete-orphan')
    meal_plans = db.relationship('MealPlan', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method=PASSWORD_HASH_METHOD)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    prep_minutes = db.Column(db.Integer, nullable=True)
    cook_minutes = db.Column(db.Integer, nullable=True)
    servings = db.Column(db.Integer, nullable=False, default=4)
    source_url = db.Column(db.String(500), nullable=True)
    tags = db.Column(db.Text, nullable=True)  # comma-separated
    instructions = db.Column(db.Text, nullable=False, default='')  # one per line
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade='all, delete-orphan')
    plan_entries = db.relationship('PlanEntry', backref='recipe', lazy=True)
    steps = db.relationship('RecipeStep', backref='recipe', lazy=True, cascade='all, delete-orphan',
                            order_by='RecipeStep.position')

class RecipeStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.Text, nullable=False)
    photo_path = db.Column(db.String(255), nullable=True)

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    qty = db.Column(db.String(50), nullable=True)  # keep as string like original
    unit = db.Column(db.String(50), nullable=True)
    note = db.Column(db.String(200), nullable=True)

class MealPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    week_start = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('PlanEntry', backref='plan', lazy=True, cascade='all, delete-orphan')

class PlanEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('meal_plan.id'), nullable=False, index=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Mon..6=Sun
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('plan_id', 'recipe_id', 'day_of_week', name='unique_plan_day_recipe'),)

class PantryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    normalized_name = db.Column(db.String(120), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'normalized_name', name='unique_user_pantry_norm'),)
