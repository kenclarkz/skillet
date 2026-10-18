"""SSRF guard for user-supplied import URLs."""

import pytest

from skillet.safe_fetch import FetchError, assert_public_url

PUBLIC_IP = "93.184.216.34"  # example.com's public IP — avoids DNS in tests


def test_rejects_non_http_schemes():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"):
        with pytest.raises(FetchError):
            assert_public_url(url)


def test_rejects_localhost_and_local_domains():
    for url in (
        "http://localhost/recipe",
        "http://localhost.localdomain/",
        "http://printer.local/",
        "http://nas.internal/",
    ):
        with pytest.raises(FetchError):
            assert_public_url(url)


def test_rejects_private_and_metadata_addresses():
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://[::1]/",
    ):
        with pytest.raises(FetchError):
            assert_public_url(url)


def test_allows_public_address():
    assert assert_public_url(f"https://{PUBLIC_IP}/recipe") == f"https://{PUBLIC_IP}/recipe"


def test_error_messages_are_user_safe():
    with pytest.raises(FetchError) as excinfo:
        assert_public_url("http://169.254.169.254/")
    message = str(excinfo.value)
    assert "not allowed" in message.lower()
    assert "169.254" not in message


def test_fetch_error_exposes_message_attribute():
    """The import API reads exc.message — it must exist on every FetchError."""
    error = FetchError("The site responded with 403.")
    assert error.message == "The site responded with 403."
    assert str(error) == "The site responded with 403."
