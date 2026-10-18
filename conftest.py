import tempfile
import pytest
from app import create_app
from app.extensions import db as _db

@pytest.fixture()
def app():
    """Test application with a fresh temporary database per test."""
    config = {
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'UPLOAD_FOLDER': tempfile.mkdtemp(prefix='skillet_test_uploads_'),
        'WTF_CSRF_ENABLED': False,
    }
    application = create_app(config=config)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def db(app):
    return _db

@pytest.fixture()
def auth(client):
    """Login helper."""
    def _login(email='test@example.com', password='password123'):
        client.post('/auth/login', data={'email': email, 'password': password})
        return client
    return _login

@pytest.fixture()
def user(db):
    from app.models import User
    u = User(email='test@example.com', display_name='Tester')
    u.set_password('password123')
    db.session.add(u)
    db.session.commit()
    return u
