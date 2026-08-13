"""Tests for password auth helper."""
import os
import pytest


def test_check_password_correct(monkeypatch):
    monkeypatch.setenv("STREAMLIT_APP_PASSWORD", "securepass123")
    from app.auth import _check_password
    assert _check_password("securepass123") is True


def test_check_password_wrong(monkeypatch):
    monkeypatch.setenv("STREAMLIT_APP_PASSWORD", "securepass123")
    from app.auth import _check_password
    assert _check_password("wrongpassword") is False


def test_check_password_empty(monkeypatch):
    monkeypatch.setenv("STREAMLIT_APP_PASSWORD", "securepass123")
    from app.auth import _check_password
    assert _check_password("") is False
