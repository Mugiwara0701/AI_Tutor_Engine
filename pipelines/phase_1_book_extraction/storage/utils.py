"""
storage/utils.py — small shared helpers for the OneDrive storage SDK:
config-file loading and a retry/backoff decorator used by graph_client.

No Graph calls happen here; this module only knows about YAML and time.
"""
import os
import re
import time
import logging
import functools
from typing import Any, Callable, Dict, Optional, Tuple, Type

from .exceptions import ConfigurationError, TransientAPIError

logger = logging.getLogger("storage")

_REQUIRED_KEYS = ("auth", "root_folder", "token_cache")

# Azure AD app (client) IDs are always a GUID, e.g.
# "3b1e9c2a-4f5d-4a2b-9c1e-7d8f6a5b4c3d". MSAL/Graph reject anything else
# with Azure's own generic, unhelpful error -- AADSTS90013 "Invalid input
# received from the user" -- with no mention of *which* field was bad.
# Validating the shape locally turns that into an actionable error at
# config-load time, before any network call is made.
_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def load_storage_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Loads and lightly validates config/storage.yaml.

    `path` defaults to the STORAGE_CONFIG_PATH env var, falling back to
    "config/storage.yaml" relative to the current working directory --
    mirroring how config.py in the main project reads env vars with
    sensible local-dev defaults.
    """
    try:
        import yaml  # PyYAML
    except ImportError as e:
        raise ConfigurationError(
            "PyYAML is required to load config/storage.yaml (pip install pyyaml)"
        ) from e

    cfg_path = path or os.environ.get("STORAGE_CONFIG_PATH", "config/storage.yaml")
    if not os.path.isfile(cfg_path):
        raise ConfigurationError(f"Storage config file not found: {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if "onedrive" not in raw:
        raise ConfigurationError(
            f"{cfg_path} must have a top-level 'onedrive' key"
        )

    cfg = raw["onedrive"]
    missing = [k for k in _REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ConfigurationError(
            f"{cfg_path} is missing required key(s) under 'onedrive': {missing}"
        )

    auth = cfg["auth"]
    for key in ("client_id", "tenant_id", "scopes"):
        if not auth.get(key):
            raise ConfigurationError(
                f"{cfg_path}: onedrive.auth.{key} is required"
            )

    # A key being "present and non-empty" (the check above) is not the
    # same as it being *filled in*. The shipped config file's client_id is
    # the literal placeholder string "<AZURE_AD_APP_CLIENT_ID>" -- that
    # passes the truthiness check above but is not a valid Azure AD app
    # ID, so MSAL happily sends it to
    # https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode
    # and Azure rejects the whole request with AADSTS90013 ("Invalid
    # input received from the user") -- a generic, field-agnostic error
    # that gives no hint the problem is client_id specifically. Catch it
    # here instead, with a message that names the actual problem.
    client_id = str(auth["client_id"]).strip()
    if not _GUID_RE.match(client_id):
        raise ConfigurationError(
            f"{cfg_path}: onedrive.auth.client_id={client_id!r} is not a "
            "valid Azure AD Application (client) ID. It must be the GUID "
            "shown on your App Registration's Overview page in the Azure "
            "Portal (Entra ID -> App registrations -> your app -> "
            "'Application (client) ID'), e.g. "
            "'3b1e9c2a-4f5d-4a2b-9c1e-7d8f6a5b4c3d' -- not the placeholder "
            "'<AZURE_AD_APP_CLIENT_ID>' left in the template. Replace it "
            "in config/storage.yaml (or override via the client_id field "
            "if you construct OneDriveStorage(config=...) directly)."
        )

    # Defaults for optional knobs, so callers elsewhere can assume they exist.
    cfg.setdefault("retry", {}).setdefault("count", 3)
    cfg["retry"].setdefault("backoff_seconds", 1.5)
    cfg.setdefault("timeout_seconds", 30)
    cfg.setdefault("root_folder", "AI_TUTOR")

    return cfg


def with_retry(
    exceptions: Tuple[Type[BaseException], ...] = (TransientAPIError,),
    count_getter: Optional[Callable[[Any], int]] = None,
) -> Callable:
    """Decorator factory for retrying transient Graph failures with
    exponential backoff.

    `count_getter(self)` lets the decorated method pull retry count/backoff
    from `self._config` at call time rather than baking in fixed numbers,
    since these are configurable via config/storage.yaml.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            cfg = getattr(self, "_config", {}) or {}
            retry_cfg = cfg.get("retry", {})
            max_attempts = retry_cfg.get("count", 3)
            backoff = retry_cfg.get("backoff_seconds", 1.5)

            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(self, *args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        break
                    sleep_for = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "storage: transient error on %s (attempt %d/%d): %s -- retrying in %.1fs",
                        func.__name__, attempt, max_attempts, e, sleep_for,
                    )
                    time.sleep(sleep_for)
            raise last_exc

        return wrapper

    return decorator


def normalize_path_component(text: str) -> str:
    """Collapses whitespace/punctuation in a single path segment (Board,
    Class, Subject, Book) into a safe OneDrive folder-name component.
    Mirrors json_writer._dir_component()'s Title_Case_With_Underscores
    convention so local filesystem output and OneDrive output eventually
    look the same, without importing from modules/ (this package must
    stay fully standalone).
    """
    import re

    words = [w for w in re.split(r"[\s_-]+", str(text).strip()) if w]
    return "_".join(w[:1].upper() + w[1:] for w in words) if words else "Untitled"
