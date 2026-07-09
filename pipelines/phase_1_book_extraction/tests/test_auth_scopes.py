"""
tests/test_auth_scopes.py — regression tests for the
`ValueError: You cannot use any scope value that is reserved.` bug.

Root cause: config/storage.yaml's onedrive.auth.scopes used to list
"offline_access" explicitly. MSAL's PublicClientApplication adds
openid/profile/offline_access to every token request automatically, and
raises if a caller also requests them -- so TokenManager.__init__ (via
storage/auth.py's _sanitize_scopes()) must strip any reserved scope out
of what config/storage.yaml provides, rather than passing it straight to
MSAL and crashing.

These tests exercise storage/auth.py's scope/tenant validation directly,
without constructing a real msal.PublicClientApplication (no network).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.auth import (
    _sanitize_scopes,
    _warn_if_not_personal_account_compatible,
    _MSAL_RESERVED_SCOPES,
)
from storage.exceptions import ConfigurationError


def test_sanitize_scopes_strips_offline_access_and_keeps_resource_scope(caplog):
    result = _sanitize_scopes(["Files.ReadWrite.All", "offline_access"])
    assert result == ["Files.ReadWrite.All"]
    assert "reserved scope" in caplog.text.lower()


def test_sanitize_scopes_strips_all_three_reserved_scopes():
    result = _sanitize_scopes(["Files.ReadWrite.All", "openid", "profile", "offline_access"])
    assert result == ["Files.ReadWrite.All"]


def test_sanitize_scopes_passthrough_when_already_clean():
    result = _sanitize_scopes(["Files.ReadWrite.All"])
    assert result == ["Files.ReadWrite.All"]


def test_sanitize_scopes_raises_when_nothing_but_reserved_scopes():
    with pytest.raises(ConfigurationError):
        _sanitize_scopes(["offline_access", "openid"])


def test_reserved_scope_constant_matches_msal():
    # Cross-check against MSAL's own reserved set so this doesn't silently
    # drift if a future MSAL version changes it.
    import msal.application as msal_app
    import inspect
    sig = inspect.signature(msal_app.ClientApplication._decorate_scope)
    msal_reserved = sig.parameters["reserved_scope"].default
    assert set(_MSAL_RESERVED_SCOPES) == set(msal_reserved)


def test_warn_if_not_personal_account_compatible_warns_for_organizations(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        _warn_if_not_personal_account_compatible("organizations")
    assert "will not allow" in caplog.text.lower()


def test_warn_if_not_personal_account_compatible_silent_for_consumers(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        _warn_if_not_personal_account_compatible("consumers")
    assert caplog.text == ""


def test_warn_if_not_personal_account_compatible_silent_for_common(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        _warn_if_not_personal_account_compatible("common")
    assert caplog.text == ""
