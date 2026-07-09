"""
storage/auth.py — MSAL-based delegated authentication against Microsoft
Graph, with a persistent token cache so the user only has to sign in
interactively once per machine.

Flow:
  1. On construction, load a serialized MSAL token cache from disk (if any).
  2. acquire_token() first tries silent acquisition (cached access token,
     or a cached refresh token exchanged transparently by MSAL).
  3. Only if silent acquisition fails entirely (no cached account, or the
     refresh token itself is expired/revoked) does it fall back to an
     interactive device-code login.
  4. Any time the cache is touched, it's re-serialized to disk.

This module never talks to Graph endpoints directly (that's
graph_client.py) -- it only produces bearer tokens for graph_client to use.
"""
import os
import logging
import threading
from typing import Any, Dict, Optional

from .exceptions import AuthenticationError, ConfigurationError

logger = logging.getLogger("storage.auth")

_AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"

# MSAL's PublicClientApplication adds these three to every token request
# automatically (they're what actually produce the ID token, refresh
# token, and profile claims) and raises ValueError if a caller also
# requests them explicitly ("You cannot use any scope value that is
# reserved."). Any of these three showing up in config/storage.yaml's
# onedrive.auth.scopes is a misconfiguration -- see _sanitize_scopes().
_MSAL_RESERVED_SCOPES = frozenset({"openid", "profile", "offline_access"})

# tenant_id values that allow a PERSONAL Microsoft account (Outlook.com/
# Hotmail/Live) to sign in. "organizations" and any specific tenant GUID
# both exclude personal accounts entirely -- see _warn_if_not_personal_account_compatible().
_PERSONAL_ACCOUNT_COMPATIBLE_TENANTS = frozenset({"consumers", "common"})


def _sanitize_scopes(requested_scopes) -> list:
    """Strips any MSAL-reserved scope out of a configured scope list,
    logging a clear warning so the misconfiguration is visible and fixed
    at the source (config/storage.yaml), rather than crashing every
    token-acquisition call with MSAL's own
    `ValueError: You cannot use any scope value that is reserved.`.
    Raises ConfigurationError if nothing but reserved scopes were
    configured (i.e. no real resource scope, like Files.ReadWrite.All,
    is actually being requested)."""
    requested = list(requested_scopes)
    reserved_found = [s for s in requested if s in _MSAL_RESERVED_SCOPES]
    if reserved_found:
        logger.warning(
            "storage.auth: config/storage.yaml's onedrive.auth.scopes lists "
            "reserved scope(s) %s. MSAL's PublicClientApplication adds "
            "openid/profile/offline_access to every token request "
            "automatically -- that's what actually gets you a refresh "
            "token, so you never need to (and cannot) request them "
            "yourself. Ignoring %s and continuing with the remaining "
            "scope(s); please also remove %s from config/storage.yaml.",
            reserved_found, reserved_found, reserved_found,
        )
    sanitized = [s for s in requested if s not in _MSAL_RESERVED_SCOPES]
    if not sanitized:
        raise ConfigurationError(
            "onedrive.auth.scopes in config/storage.yaml contains only "
            f"reserved scope(s) {requested!r} -- it must also list at "
            "least one real Microsoft Graph resource scope, e.g. "
            "'Files.ReadWrite.All'."
        )
    return sanitized


def _warn_if_not_personal_account_compatible(tenant_id: str) -> None:
    """This project's stated goal is authenticating against the user's
    PERSONAL Microsoft OneDrive (not OneDrive for Business / SharePoint).
    Only tenant_id="consumers" (personal accounts only) or "common"
    (personal + work/school) actually allow a personal Microsoft account
    to sign in -- "organizations" or a specific Entra tenant GUID both
    reject personal accounts outright. This doesn't raise (a caller may
    have a legitimate reason to target a work/school tenant instead) but
    surfaces the mismatch loudly rather than letting it fail silently at
    sign-in time with a confusing Microsoft-side error."""
    if tenant_id.strip().lower() not in _PERSONAL_ACCOUNT_COMPATIBLE_TENANTS:
        logger.warning(
            "storage.auth: onedrive.auth.tenant_id=%r will NOT allow "
            "sign-in with a personal Microsoft account (Outlook.com/"
            "Hotmail/Live) -- only 'consumers' (personal accounts only) "
            "or 'common' (personal + work/school) do. If the goal is the "
            "user's personal OneDrive, set tenant_id to 'consumers' (and "
            "make sure the App Registration's Supported account types "
            "includes personal Microsoft accounts).",
            tenant_id,
        )


class TokenManager:
    """Owns the MSAL PublicClientApplication + persistent token cache for
    one configured account. Thread-safe: a single lock guards both token
    acquisition and cache serialization, since MSAL's SerializableTokenCache
    is not safe for concurrent mutation.
    """

    def __init__(self, auth_config: Dict[str, Any], token_cache_path: str):
        self._client_id: str = auth_config["client_id"]
        self._tenant_id: str = auth_config["tenant_id"]
        _warn_if_not_personal_account_compatible(self._tenant_id)
        self._scopes = _sanitize_scopes(auth_config["scopes"])
        self._token_cache_path = token_cache_path
        self._lock = threading.Lock()

        self._cache = self._load_cache()
        self._app = self._build_app()

    # -- cache persistence ------------------------------------------------

    def _load_cache(self):
        import msal

        cache = msal.SerializableTokenCache()
        if os.path.isfile(self._token_cache_path):
            try:
                with open(self._token_cache_path, "r", encoding="utf-8") as fh:
                    cache.deserialize(fh.read())
            except (OSError, ValueError) as e:
                # Corrupt or unreadable cache file: log and start fresh
                # rather than blocking auth entirely on a stale file.
                logger.warning(
                    "storage.auth: could not load token cache at %s (%s); "
                    "starting a fresh cache (re-login will be required)",
                    self._token_cache_path, e,
                )
        return cache

    def _persist_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        os.makedirs(os.path.dirname(self._token_cache_path) or ".", exist_ok=True)
        with open(self._token_cache_path, "w", encoding="utf-8") as fh:
            fh.write(self._cache.serialize())

    def _build_app(self):
        import msal

        return msal.PublicClientApplication(
            client_id=self._client_id,
            authority=_AUTHORITY_TEMPLATE.format(tenant_id=self._tenant_id),
            token_cache=self._cache,
        )

    # -- token acquisition --------------------------------------------------

    def acquire_token(self) -> str:
        """Returns a valid bearer access token, refreshing or (as a last
        resort) prompting an interactive login as needed. Safe to call
        before every Graph request -- MSAL no-ops when the cached access
        token is still valid."""
        with self._lock:
            accounts = self._app.get_accounts()
            result: Optional[Dict[str, Any]] = None

            if accounts:
                # Silent path: MSAL transparently uses the cached refresh
                # token if the access token itself has expired.
                result = self._app.acquire_token_silent(
                    self._scopes, account=accounts[0]
                )

            if not result:
                result = self._interactive_login()

            self._persist_cache()

            if "access_token" not in result:
                raise AuthenticationError(
                    "MSAL did not return an access token: "
                    f"{result.get('error')}: {result.get('error_description')}"
                )
            return result["access_token"]

    def _interactive_login(self) -> Dict[str, Any]:
        """Falls back to MSAL's device-code flow: prints a URL + code for
        the user to complete sign-in in a browser. Used only when there is
        no usable cached account/refresh token -- i.e. first run, or after
        the refresh token has been revoked/expired.
        """
        flow = self._app.initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow:
            raise AuthenticationError(
                f"Failed to start device-code login: {flow.get('error_description', flow)}"
            )

        logger.info(
            "storage.auth: interactive sign-in required. %s",
            flow["message"],
        )
        print(flow["message"])  # noqa: T201 -- deliberate user-facing prompt

        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise AuthenticationError(
                "Interactive sign-in failed: "
                f"{result.get('error')}: {result.get('error_description')}"
            )
        return result

    def sign_out(self) -> None:
        """Removes all cached accounts, forcing the next acquire_token()
        call to prompt an interactive login again."""
        with self._lock:
            for account in self._app.get_accounts():
                self._app.remove_account(account)
            self._persist_cache()
