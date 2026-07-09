"""
storage/exceptions.py — exception hierarchy for the OneDrive storage SDK.

Kept deliberately small and specific so callers can catch precisely what
they care about (e.g. retry on TransientAPIError, prompt re-auth on
AuthenticationError) without parsing Graph's raw error payloads themselves.
"""


class StorageError(Exception):
    """Base class for all errors raised by the storage package."""


class ConfigurationError(StorageError):
    """Raised when config/storage.yaml is missing, malformed, or missing
    a required key (client_id, tenant_id, scopes, root_folder, ...)."""


class AuthenticationError(StorageError):
    """Raised when MSAL cannot obtain a token: no cached account, refresh
    token expired/revoked, interactive login failed or was cancelled, etc.
    """


class NotFoundError(StorageError):
    """Raised when a requested item does not exist on OneDrive (Graph
    404). Distinct from a failed *check* -- exists() returns False rather
    than raising this."""


class ConflictError(StorageError):
    """Raised on a Graph 409 (e.g. creating a folder that already exists
    with conflict-behavior=fail, or a move/copy destination collision)."""


class TransientAPIError(StorageError):
    """Raised when a Graph call fails in a way that is likely to succeed
    on retry: 429 (throttling), 5xx, or a network-level timeout. Callers
    that want custom retry/backoff behavior beyond the SDK's built-in
    retry (see config/storage.yaml: retry.count) can catch this
    specifically; by default graph_client already retries these
    internally before this ever surfaces."""


class MigrationError(StorageError):
    """Raised by storage/migration.py when the first-run local -> OneDrive
    migration cannot be completed and verified in full. Callers (book_
    orchestrator.py's startup gate) must treat this as fatal and must NOT
    proceed to PDF extraction -- migration completing successfully is a
    precondition for extraction, not a best-effort step."""
