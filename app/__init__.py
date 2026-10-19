import os
from flask import Flask
from dotenv import load_dotenv
from app.extensions import db, login_manager, csrf

load_dotenv()

def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)

    # Environment-driven defaults
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.getenv('DATABASE_PATH')
    if db_path:
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        default_db_uri = 'sqlite:///' + db_path
    else:
        default_db_uri = 'sqlite:///' + os.path.join(app.instance_path, 'skillet.db')

    upload_folder = os.getenv('UPLOAD_FOLDER')
    if upload_folder and not os.path.isabs(upload_folder):
        upload_folder = os.path.abspath(upload_folder)
    if not upload_folder:
        upload_folder = os.path.join(app.root_path, 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key-change-me'),
        SQLALCHEMY_DATABASE_URI=default_db_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=upload_folder,
        MAX_CONTENT_LENGTH=int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024)),
        MAX_PDF_BYTES=int(os.getenv('MAX_PDF_BYTES', 4 * 1024 * 1024)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )

    # Explicit config (tests, etc.) always wins over environment defaults.
    if config:
        app.config.from_mapping(config)

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # Ensure instance exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.recipes import bp as recipes_bp
    from app.routes.plans import bp as plans_bp
    from app.routes.grocery import bp as grocery_bp
    from app.routes.main import bp as main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(grocery_bp)
    app.register_blueprint(main_bp)

    # Auto-create tables on startup so a fresh checkout works without
    # running `flask db-init` first. create_all only adds missing tables
    # and never touches existing data.
    from app.models import User, Recipe, Ingredient, MealPlan, PlanEntry, PantryItem  # noqa: F401
    with app.app_context():
        db.create_all()

    # CLI
    @app.cli.command('db-init')
    def db_init():
        db.create_all()
        print('Database initialized.')

    # Serve uploads
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    return app
