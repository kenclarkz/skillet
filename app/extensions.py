from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    from app.extensions import db as _db
    try:
        return _db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
