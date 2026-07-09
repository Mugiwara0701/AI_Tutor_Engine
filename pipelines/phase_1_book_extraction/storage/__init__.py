"""
storage/ — reusable Microsoft OneDrive storage SDK for the AI Tutor project.

As of the pipeline storage migration, this package is wired into the
extraction pipeline: modules/json_writer.py is the one caller that talks to
it (via OneDriveStorage), for every persistent write/read the pipeline
does (chapter JSON, book manifests). Nothing else in the extraction/
validation/prompt-manager code talks to Graph directly, or should ever
need to -- json_writer.py is the boundary.

Everything this SDK writes lives under a single OneDrive root folder
(default: "AI_TUTOR/"), organized as:

    AI_TUTOR/<Board>/Class_<Class>/<Subject>/<Book>/{json_out,logs,cache,assets}/

Usage:

    from storage import OneDriveStorage

    store = OneDriveStorage()  # reads config/storage.yaml
    store.upload_json(
        {"hello": "world"},
        board="CBSE", klass="12", subject="Chemistry",
        book="NCERT_Chemistry_Part_1", filename="manifest.json",
    )

See onedrive_storage.py for the full public API and README.md (generated
alongside this package) for setup instructions.
"""

from .onedrive_storage import OneDriveStorage
from .path_resolver import PathResolver
from .exceptions import (
    StorageError,
    AuthenticationError,
    NotFoundError,
    ConflictError,
    TransientAPIError,
    ConfigurationError,
    MigrationError,
)

__all__ = [
    "OneDriveStorage",
    "PathResolver",
    "StorageError",
    "AuthenticationError",
    "NotFoundError",
    "ConflictError",
    "TransientAPIError",
    "ConfigurationError",
    "MigrationError",
]
