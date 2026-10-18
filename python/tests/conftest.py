"""Shared fixtures: a configured app with fake Supabase settings (no network)."""

from __future__ import annotations

import pytest

from skillet import create_app


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test-project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fake-anon-key-for-tests")
    monkeypatch.setenv("APP_URL", "http://localhost:5000")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
