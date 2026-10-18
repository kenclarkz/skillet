#!/usr/bin/env python
"""End-to-end smoke test against a running Skillet server.

Usage:  python scripts/smoke.py [base_url]   (default http://127.0.0.1:5000)
Exercises: signup, login, recipe creation with photo, meal plan assignment,
and the generated shopping list — through the real HTTP interface with CSRF.
"""
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000'
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
       b'\x00\x00IEND\xaeB`\x82')

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))


def get(path):
    with opener.open(BASE + path) as r:
        return r.status, r.read().decode('utf-8', 'replace')


def post(path, data, multipart=False):
    if multipart:
        boundary = '----smokeboundary123'
        parts = []
        for key, value in data.items():
            if isinstance(value, tuple):
                filename, blob, ctype = value
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; '
                    f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + blob + b'\r\n'
                )
            else:
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
                    f'{value}\r\n'.encode()
                )
        parts.append(f'--{boundary}--\r\n'.encode())
        body = b''.join(parts)
        req = urllib.request.Request(BASE + path, data=body, method='POST')
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    else:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(BASE + path, data=body, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with opener.open(req) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def csrf(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None


def main():
    status, html = get('/')
    check('GET / returns 200 and Skillet branding', status == 200 and 'Skillet' in html)

    email = 'smoke@example.com'
    _, signup_html = get('/auth/signup')
    token = csrf(signup_html)
    status, body = post('/auth/signup', {
        'csrf_token': token,
        'email': email,
        'display_name': 'Smoke Tester',
        'password': 'password123',
        'password2': 'password123',
    })
    check('Signup succeeds', status in (200, 302), f'status {status}')

    _, login_html = get('/auth/login')
    status, _ = post('/auth/login', {
        'csrf_token': csrf(login_html),
        'email': email,
        'password': 'password123',
    })
    check('Login succeeds', status in (200, 302), f'status {status}')

    _, new_html = get('/recipes/new')
    status, body = post('/recipes/new', {
        'csrf_token': csrf(new_html),
        'title': 'Smoke Chili',
        'description': 'Created by smoke test',
        'prep_minutes': '10',
        'cook_minutes': '30',
        'servings': '4',
        'tags': 'test',
        'ingredients': '2 cups all-purpose flour\n1 tsp salt\n3 cloves garlic',
        'instructions': 'Mix\nSimmer',
        'source_url': '',
        'photo': ('smoke.png', PNG, 'image/png'),
    }, multipart=True)
    check('Recipe created with photo upload', status in (200, 302), f'status {status}')

    status, body = get('/recipes')
    check('Recipe appears in the card list', status == 200 and 'Smoke Chili' in body)

    m = re.search(r'(?:src=")(/uploads/[^"]*smoke[^"]*\.png)', body)
    if m:
        status, photo_html = get(m.group(1))
        with opener.open(BASE + m.group(1)) as r:
            blob = r.read()
        check('Photo served from /uploads', status == 200 and blob[:8] == b'\x89PNG\r\n\x1a\n')
    else:
        check('Photo served from /uploads', False, 'photo path not found in page')

    status, body = get('/plans/new')
    token = csrf(body)
    status, _ = post('/plans/new', {
        'csrf_token': token,
        'week_start': '2026-10-19',
        'title': 'Smoke week',
    })
    check('Meal plan created', status in (200, 302), f'status {status}')

    status, body = get('/plans')
    m = re.search(r'/plans/(\d+)', body)
    plan_id = m.group(1) if m else None
    check('Plan listed', bool(plan_id), body[:120])

    status, body = get('/recipes')
    m = re.search(r'/recipes/(\d+)', body)
    recipe_id = m.group(1) if m else None
    check('Recipe id found', bool(recipe_id))

    _, view_html = get(f'/plans/{plan_id}') if plan_id else (0, '')
    token = csrf(view_html) if view_html else None
    status, _ = post(f'/plans/{plan_id}/assign', {
        'csrf_token': token,
        'recipe_id': recipe_id,
        'day_of_week': 0,
    }) if plan_id and recipe_id else (0, '')
    check('Recipe assigned to Monday', status in (200, 302), f'status {status}')

    status, body = get(f'/grocery/{plan_id}') if plan_id else (0, '')
    body = body or ''
    check('Shopping list shows merged ingredient', 'flour' in body.lower(), body[:200])
    check('Shopping list flags pantry staple', 'pantry' in body.lower())

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {name}" + (f' — {detail}' if not ok else ''))
    print(f"\n{len(results) - len(failed)}/{len(results)} smoke checks passed")
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
