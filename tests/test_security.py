"""Security posture: CSRF, sessions, secrets, and image handling."""
import os

from app import create_app


def _csrf_app():
    return create_app(config={
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'UPLOAD_FOLDER': '/tmp/skillet_csrf_uploads',
        'WTF_CSRF_ENABLED': True,
    })


def test_csrf_rejects_missing_token():
    from app.extensions import db as _db
    app = _csrf_app()
    with app.app_context():
        _db.create_all()
        try:
            client = app.test_client()
            res = client.post('/auth/signup', data={
                'email': 'x@example.com',
                'password': 'password123',
                'password2': 'password123',
            })
            assert res.status_code == 400
        finally:
            _db.session.remove()
            _db.drop_all()


def test_session_cookie_is_httponly_and_samesite():
    from app.extensions import db as _db
    app = create_app(config={
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'UPLOAD_FOLDER': '/tmp/skillet_csrf_uploads',
        'WTF_CSRF_ENABLED': False,
    })
    with app.app_context():
        _db.create_all()
        try:
            client = app.test_client()
            client.post('/auth/signup', data={
                'email': 'cookie@example.com',
                'password': 'password123',
                'password2': 'password123',
            })
            res = client.post('/auth/login', data={
                'email': 'cookie@example.com',
                'password': 'password123',
            })
            set_cookie = res.headers.get('Set-Cookie', '')
            assert 'session=' in set_cookie
            assert 'HttpOnly' in set_cookie
            assert 'SameSite=Lax' in set_cookie
        finally:
            _db.session.remove()
            _db.drop_all()


def test_secret_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'rotated-in-prod')
    app = create_app(config={'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
    assert app.config['SECRET_KEY'] == 'rotated-in-prod'


def test_upload_folder_is_persisted_directory(app):
    folder = app.config['UPLOAD_FOLDER']
    assert os.path.isdir(folder)
    assert not folder.startswith('/proc')  # sanity


def test_password_hash_contains_method_and_salt(client, user):
    from app.models import User
    row = User.query.first()
    assert row.password_hash.startswith('pbkdf2:sha256:')
    # hash includes the salt separator, not a bare digest
    assert ':' in row.password_hash
