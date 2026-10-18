"""Authentication and security tests."""
def test_home_page_loads(client):
    res = client.get('/')
    assert res.status_code == 200
    assert b'Skillet' in res.data


def test_register_and_login(client):
    res = client.post('/auth/signup', data={
        'email': 'new@example.com',
        'display_name': 'Newbie',
        'password': 'supersecret1',
        'password2': 'supersecret1',
    })
    assert res.status_code == 302

    res = client.post('/auth/login', data={
        'email': 'new@example.com',
        'password': 'supersecret1',
    })
    assert res.status_code == 302

    res = client.get('/recipes')
    assert res.status_code == 200
    assert b'My recipes' in res.data


def test_wrong_password_rejected(client, user):
    res = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'wrongpassword',
    }, follow_redirects=True)
    assert b'Invalid email or password' in res.data


def test_password_is_hashed(client, user, db):
    from app.models import User
    row = User.query.filter_by(email='test@example.com').first()
    assert row.password_hash != 'password123'
    assert row.check_password('password123')
    assert not row.check_password('nope')


def test_protected_pages_require_login(client):
    for path in ['/recipes', '/recipes/new', '/plans', '/grocery']:
        res = client.get(path)
        assert res.status_code == 302
        assert '/auth/login' in res.headers['Location']


def test_csrf_protection_is_on_by_default(client, user, db):
    """CSRF is disabled in tests, so verify the app config enables it by default."""
    from app import create_app
    app = create_app(config={
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'UPLOAD_FOLDER': '/tmp/skillet_test_uploads',
    })
    with app.test_request_context():
        assert app.config['WTF_CSRF_ENABLED'] is True
        assert app.config['SECRET_KEY'] != ''


def test_registration_duplicate_email(client, user):
    res = client.post('/auth/signup', data={
        'email': 'test@example.com',
        'display_name': 'Dup',
        'password': 'supersecret1',
        'password2': 'supersecret1',
    }, follow_redirects=True)
    assert b'already registered' in res.data
