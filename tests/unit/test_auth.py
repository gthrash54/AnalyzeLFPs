"""Users, roles, sessions. Attribution is the point, so identity has to be real."""

from __future__ import annotations

from datetime import UTC

import pytest

from dbsspeech.auth import (
    ROLES,
    AuthError,
    add_user,
    get_user,
    list_users,
    login,
    logout,
    purge_expired,
    set_disabled,
    set_password,
    set_role,
    user_for_token,
)

pytestmark = pytest.mark.unit

GOOD = "correct-horse-battery"


@pytest.fixture
def db(tmp_path):
    return tmp_path / "app.db"


def _user(db, email="g@example.org", role="admin"):
    return add_user("Garrett", email, role, GOOD, db)


# ---- accounts ----------------------------------------------------------------

def test_a_user_can_be_created_and_found(db):
    created = _user(db)
    found = get_user("g@example.org", db)
    assert found is not None
    assert found.id == created.id
    assert found.role == "admin"


def test_email_is_stored_lowercase_and_matched_that_way(db):
    add_user("G", "MiXeD@Example.ORG", "analyst", GOOD, db)
    assert get_user("mixed@example.org", db) is not None


def test_a_duplicate_email_is_refused(db):
    _user(db)
    with pytest.raises(AuthError, match="already exists"):
        _user(db)


def test_an_unknown_role_lists_the_valid_ones(db):
    with pytest.raises(AuthError, match="valid roles"):
        add_user("G", "x@example.org", "wizard", GOOD, db)


def test_an_invalid_email_is_refused(db):
    with pytest.raises(AuthError, match="not a valid email"):
        add_user("G", "not-an-email", "analyst", GOOD, db)


def test_a_short_password_is_refused(db):
    with pytest.raises(AuthError, match="at least 12"):
        add_user("G", "x@example.org", "analyst", "short", db)


def test_a_user_needs_a_name(db):
    with pytest.raises(AuthError, match="attribution"):
        add_user("   ", "x@example.org", "analyst", GOOD, db)


def test_the_password_is_never_stored_in_plain_text(db, tmp_path):
    _user(db)
    assert GOOD.encode() not in db.read_bytes()


def test_the_hash_is_argon2(db):
    import sqlite3

    _user(db)
    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored.startswith("$argon2")


# ---- roles -------------------------------------------------------------------

def test_roles_are_ordered_so_a_check_means_at_least(db):
    reviewer = add_user("R", "r@example.org", "reviewer", GOOD, db)
    analyst = add_user("A", "a@example.org", "analyst", GOOD, db)
    admin = add_user("D", "d@example.org", "admin", GOOD, db)

    assert reviewer.can("reviewer") and not reviewer.can("analyst")
    assert analyst.can("reviewer") and analyst.can("analyst") and not analyst.can("admin")
    assert all(admin.can(role) for role in ROLES)


def test_a_disabled_user_can_do_nothing(db):
    _user(db)
    set_disabled("g@example.org", True, db)
    assert not get_user("g@example.org", db).can("reviewer")


def test_a_role_can_be_changed(db):
    _user(db, role="reviewer")
    set_role("g@example.org", "admin", db)
    assert get_user("g@example.org", db).role == "admin"


def test_changing_the_role_of_an_unknown_user_raises(db):
    with pytest.raises(AuthError, match="no user"):
        set_role("nobody@example.org", "admin", db)


def test_users_are_disabled_rather_than_deleted(db):
    """Deleting a user orphans the attribution on every past decision."""
    _user(db)
    set_disabled("g@example.org", True, db)
    assert len(list_users(db)) == 1


# ---- login -------------------------------------------------------------------

def test_login_returns_a_token_that_resolves_to_the_user(db):
    _user(db)
    token = login("g@example.org", GOOD, db)
    resolved = user_for_token(token, db)
    assert resolved is not None and resolved.email == "g@example.org"


def test_a_wrong_password_and_an_unknown_email_give_the_same_error(db):
    """A different message tells an attacker which emails exist."""
    _user(db)
    with pytest.raises(AuthError) as wrong:
        login("g@example.org", "wrong-password-here", db)
    with pytest.raises(AuthError) as unknown:
        login("nobody@example.org", GOOD, db)
    assert str(wrong.value) == str(unknown.value)


def test_a_disabled_account_cannot_log_in(db):
    _user(db)
    set_disabled("g@example.org", True, db)
    with pytest.raises(AuthError, match="disabled"):
        login("g@example.org", GOOD, db)


def test_a_reset_password_works_and_the_old_one_does_not(db):
    _user(db)
    set_password("g@example.org", "a-brand-new-passphrase", db)
    assert login("g@example.org", "a-brand-new-passphrase", db)
    with pytest.raises(AuthError):
        login("g@example.org", GOOD, db)


def test_logout_invalidates_the_token(db):
    _user(db)
    token = login("g@example.org", GOOD, db)
    logout(token, db)
    assert user_for_token(token, db) is None


def test_an_unknown_or_empty_token_resolves_to_nobody(db):
    assert user_for_token("", db) is None
    assert user_for_token("not-a-real-token", db) is None


def test_an_expired_session_resolves_to_nobody_and_is_cleaned_up(db):
    import sqlite3
    from datetime import datetime, timedelta

    _user(db)
    token = login("g@example.org", GOOD, db)
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET expires_at = ?", (past,))
    assert user_for_token(token, db) is None
    assert purge_expired(db) == 0, "the expired session should already be gone"


def test_two_logins_produce_different_tokens(db):
    _user(db)
    assert login("g@example.org", GOOD, db) != login("g@example.org", GOOD, db)
