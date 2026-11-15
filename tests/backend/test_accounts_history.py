"""Accounts and saved history (docs/design/user_history.md): sign-up, login, sessions, CSRF header,
login limit, shortlist of 3, retention, and that one user can never see another user's entries."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mediroute.backend.accounts import store as store_mod
from mediroute.backend.accounts.api import COOKIE, router
from mediroute.backend.accounts.store import AccountStore, hash_password, verify_password

H = {"X-MediRoute": "1"}
HOSPITALS = ["H056", "H001", "H002", "H003"]


@pytest.fixture()
def store(tmp_path):
    s = AccountStore(tmp_path / "test.db")
    store_mod.set_store(s)
    yield s
    store_mod.set_store(None)


@pytest.fixture()
def app(store):
    a = FastAPI()
    a.include_router(router)
    return a


def client(app):
    return TestClient(app)


def signup(c, email="pat@example.com", password="secret123", country="Kenya", consent=True, **extra):
    return c.post("/api/auth/signup", headers=H,
                  json={"email": email, "password": password, "country": country, "consent": consent, **extra})


def save(c, hospital_id="H056", workflow_id="wf1", **extra):
    body = {"hospital_id": hospital_id, "workflow_id": workflow_id, "request_text": "IVF after 4 years",
            "city": "Hyderabad", "specialty": "Reproductive Medicine",
            "thread": [{"question": "Which part of the body?", "answer": "More than one / whole body"}], **extra}
    return c.post("/api/history", headers=H, json=body)


def test_password_hash_roundtrip():
    stored = hash_password("secret123")
    assert "secret123" not in stored and stored.startswith("scrypt$")
    assert verify_password("secret123", stored) and not verify_password("secret124", stored)


def test_signup_requires_email_password_country_consent(app):
    c = client(app)
    assert signup(c, email="not-an-email").status_code == 400
    assert signup(c, password="short").status_code == 400
    assert signup(c, country="").status_code == 400
    assert signup(c, consent=False).status_code == 400
    r = signup(c, name="Pat", language="English")
    assert r.status_code == 200 and r.json()["user"]["country"] == "Kenya"
    assert "password" not in str(r.json())
    assert signup(c).status_code == 409  # same email again


def test_session_cookie_login_logout(app):
    c = client(app)
    r = signup(c)
    cookie = r.headers.get("set-cookie", "")
    assert COOKIE in cookie and "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    assert c.get("/api/auth/me").json()["user"]["email"] == "pat@example.com"
    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", headers=H, json={"email": "PAT@example.com", "password": "secret123"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200


def test_changes_need_the_header(app):
    c = client(app)
    assert c.post("/api/auth/signup", json={"email": "a@b.co", "password": "secret123", "country": "Oman",
                                            "consent": True}).status_code == 403
    signup(c)
    assert c.post("/api/history", json={"hospital_id": "H056"}).status_code == 403


def test_too_many_failed_logins(app):
    c = client(app)
    signup(c)
    for _ in range(5):
        assert c.post("/api/auth/login", headers=H, json={"email": "pat@example.com", "password": "wrong-pass"}).status_code == 401
    r = c.post("/api/auth/login", headers=H, json={"email": "pat@example.com", "password": "secret123"})
    assert r.status_code == 429


def test_history_needs_login(app):
    c = client(app)
    assert c.get("/api/history").status_code == 401
    assert save(c).status_code == 401


def test_save_and_shortlist_of_three(app):
    c = client(app)
    signup(c)
    first = save(c).json()["entry"]
    assert first["hospitals"][0]["name"]  # snapshot from the server's hospital table
    assert first["thread"][0]["answer"] == "More than one / whole body"
    for hid in HOSPITALS[1:3]:
        save(c, hospital_id=hid)
    assert len(c.get(f"/api/history/{first['id']}").json()["entry"]["hospitals"]) == 3
    assert save(c, hospital_id=HOSPITALS[0]).status_code == 200  # already saved: no change
    assert save(c, hospital_id=HOSPITALS[3]).status_code == 409  # a fourth one
    assert len(c.get("/api/history").json()["entries"]) == 1     # one search, one entry
    assert save(c, hospital_id="NOPE").status_code == 404


def test_description_not_saved_when_unticked(app):
    c = client(app)
    signup(c)
    entry = save(c, save_description=False).json()["entry"]
    assert entry["request_text"] is None and entry["specialty"] == "Reproductive Medicine"


def test_one_user_never_sees_another_users_entries(app):
    a, b = client(app), client(app)
    signup(a, email="a@example.com")
    signup(b, email="b@example.com")
    entry_id = save(a).json()["entry"]["id"]
    assert b.get("/api/history").json()["entries"] == []
    assert b.get(f"/api/history/{entry_id}").status_code == 404
    assert b.delete(f"/api/history/{entry_id}", headers=H).status_code == 404
    assert b.delete(f"/api/history/{entry_id}/hospitals/H056", headers=H).status_code == 404
    assert a.get(f"/api/history/{entry_id}").status_code == 200


def test_remove_hospital_and_delete_entry_and_account(app, store):
    c = client(app)
    signup(c)
    entry_id = save(c).json()["entry"]["id"]
    save(c, hospital_id="H001")
    left = c.delete(f"/api/history/{entry_id}/hospitals/H056", headers=H).json()["entry"]
    assert [h["hospital_id"] for h in left["hospitals"]] == ["H001"]
    assert c.delete(f"/api/history/{entry_id}/hospitals/H001", headers=H).json()["entry"] is None  # last one: entry gone
    entry_id = save(c, workflow_id="wf2").json()["entry"]["id"]
    assert c.delete(f"/api/history/{entry_id}", headers=H).status_code == 200
    save(c, workflow_id="wf3")
    assert c.delete("/api/auth/me", headers=H).status_code == 200
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM saved_requests").fetchone()[0] == 0
    assert c.get("/api/auth/me").status_code == 401


def test_entries_older_than_90_days_are_deleted(app, store):
    c = client(app)
    signup(c)
    entry_id = save(c).json()["entry"]["id"]
    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat(timespec="seconds")
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE saved_requests SET updated_at = ? WHERE id = ?", (old, entry_id))
    assert c.get("/api/history").json()["entries"] == []
