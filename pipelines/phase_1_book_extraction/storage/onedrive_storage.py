"""
storage/onedrive_storage.py — public storage API for OneDrive.

OneDriveStorage is the ONLY class the rest of the project should ever
touch. It exposes plain upload/download/exists/delete/copy/move/list
methods that work in terms of Board/Class/Subject/Book (via
PathResolver) or, for lower-level callers, raw paths relative to the
AI_TUTOR root -- never Microsoft Graph item IDs, and never a raw REST
call. graph_client.py is the only module that talks to Graph.

This module is used by modules/json_writer.py for every persistent write/
read the extraction pipeline does; that module is the only caller of this
class in the pipeline.

Two upload/download surfaces are provided on every write/read method:
  - a Board/Class/Subject/Book-aware surface (upload_file(..., board=,
    klass=, subject=, book=, filename=)), which uses PathResolver so no
    caller has to hand-build a folder path.
  - a raw-path surface (upload_file_at_path(path, ...)) for callers who
    already have a full AI_TUTOR-relative path (e.g. from list_directory()
    or from copy/move destinations).

Large-file note: uploads go through Graph's simple PUT :/content: upload,
which supports files up to 4MB. This project's artifacts (chapter JSON,
manifests, source PDFs/images per chapter) are expected to stay well under
that in the common case; if a future caller needs >4MB uploads, add a
chunked "upload session" path to graph_client.py rather than growing this
class's surface.
"""
import io
import json
import logging
from typing import Any, Dict, List, Optional

from .auth import TokenManager
from .graph_client import GraphClient
from .path_resolver import PathResolver
from .cache import TTLCache
from .exceptions import NotFoundError
from .utils import load_storage_config

logger = logging.getLogger("storage.onedrive")


class OneDriveStorage:
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
    ):
        """
        `config`: a pre-loaded config dict (matching config/storage.yaml's
            `onedrive:` section) -- mainly for tests. If omitted, loads
            from `config_path` (or config/storage.yaml / STORAGE_CONFIG_PATH).
        """
        self._config = config or load_storage_config(config_path)
        self._resolver = PathResolver(self._config.get("root_folder", "AI_TUTOR"))
        self._cache = TTLCache(ttl_seconds=self._config.get("cache_ttl_seconds", 30))

        token_manager = TokenManager(
            auth_config=self._config["auth"],
            token_cache_path=self._config["token_cache"],
        )
        self._graph = GraphClient(token_manager, self._config)

    # -- path helpers -------------------------------------------------------

    @property
    def root_folder(self) -> str:
        return self._resolver.root_folder

    def authenticate(self) -> None:
        """Explicitly triggers MSAL token acquisition now, so a caller's
        startup sequence can treat "Authenticate" as its own step (and
        surface any interactive device-code prompt / AuthenticationError
        immediately) before doing anything else, such as checking
        migration state. Not required before any other method here --
        they all authenticate on demand -- but calling it first makes
        startup ordering explicit and its failures easy to attribute."""
        self._graph.authenticate()

    def resolve_path(self, board: str, klass: str, subject: str, book: Optional[str] = None) -> str:
        """Exposes PathResolver for callers that want the folder path
        without performing an operation (e.g. to display it, or to pass
        into the raw-path methods below)."""
        return self._resolver.resolve(board, klass, subject, book)

    def _resolve_file_path(
        self,
        board: Optional[str],
        klass: Optional[str],
        subject: Optional[str],
        book: Optional[str],
        filename: Optional[str],
        path: Optional[str],
    ) -> str:
        if path:
            return path.strip("/")
        if not all([board, klass, subject, book, filename]):
            raise ValueError(
                "Either `path` or all of (board, klass, subject, book, filename) must be provided"
            )
        return self._resolver.resolve_file(board, klass, subject, book, filename)

    # -- folder creation ------------------------------------------------------

    def create_directory(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        path: Optional[str] = None,
    ) -> str:
        """Creates the resolved folder (and any missing ancestors) if it
        doesn't already exist. Returns the folder's AI_TUTOR-relative
        path. This is called automatically by the upload_* methods, so
        callers rarely need it directly -- it's exposed for cases like
        pre-provisioning a Book folder before any file exists."""
        folder_path = path.strip("/") if path else self._resolver.resolve(board, klass, subject, book)
        self._graph.ensure_folder(folder_path)
        self._cache.invalidate_prefix(folder_path)
        return folder_path

    # -- upload / download: bytes -------------------------------------------

    def upload_file(
        self,
        data: bytes,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> str:
        """Uploads raw bytes, creating the destination folder if needed.
        Returns the AI_TUTOR-relative path the file was written to.

        Provide either `path` (full AI_TUTOR-relative file path) or all of
        board/klass/subject/book/filename.
        """
        file_path = self._resolve_file_path(board, klass, subject, book, filename, path)
        folder_path = "/".join(file_path.split("/")[:-1])
        self._graph.ensure_folder(folder_path)
        self._graph.upload_content(file_path, data)
        self._cache.invalidate_prefix(folder_path)
        logger.info("storage: uploaded %s (%d bytes)", file_path, len(data))
        return file_path

    def download_file(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> bytes:
        """Downloads and returns raw file bytes. Raises NotFoundError if
        the file doesn't exist."""
        file_path = self._resolve_file_path(board, klass, subject, book, filename, path)
        return self._graph.download_content(file_path)

    # -- upload / download: JSON ---------------------------------------------

    def upload_json(
        self,
        obj: Any,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
        indent: int = 2,
    ) -> str:
        """Serializes `obj` as UTF-8 JSON and uploads it. Same
        path-resolution rules as upload_file()."""
        payload = json.dumps(obj, indent=indent, ensure_ascii=False).encode("utf-8")
        return self.upload_file(
            payload, board=board, klass=klass, subject=subject,
            book=book, filename=filename, path=path,
        )

    def download_json(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> Any:
        """Downloads a file and parses it as JSON."""
        raw = self.download_file(
            board=board, klass=klass, subject=subject,
            book=book, filename=filename, path=path,
        )
        return json.loads(raw.decode("utf-8"))

    # -- existence / listing --------------------------------------------------

    def exists(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> bool:
        """Returns True/False; never raises NotFoundError."""
        item_path = self._resolve_file_path(board, klass, subject, book, filename, path)
        item = self._cache.get_or_set(
            f"item:{item_path}", lambda: self._graph.get_item(item_path)
        )
        return item is not None

    def list_directory(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists immediate children of a folder. Returns a list of dicts:
        {"name": str, "is_folder": bool, "size": int, "path": str}.
        Raises NotFoundError if the folder doesn't exist."""
        folder_path = path.strip("/") if path else self._resolver.resolve(board, klass, subject, book)

        def _list():
            raw_children = self._graph.list_children(folder_path)
            return [
                {
                    "name": child["name"],
                    "is_folder": "folder" in child,
                    "size": child.get("size", 0),
                    "path": f"{folder_path}/{child['name']}",
                }
                for child in raw_children
            ]

        return self._cache.get_or_set(f"list:{folder_path}", _list)

    # -- delete / copy / move -------------------------------------------------

    def delete(
        self,
        board: Optional[str] = None,
        klass: Optional[str] = None,
        subject: Optional[str] = None,
        book: Optional[str] = None,
        filename: Optional[str] = None,
        path: Optional[str] = None,
    ) -> None:
        """Deletes a file or folder (folders are deleted recursively, per
        Graph's default behavior). No-op if it doesn't exist."""
        item_path = self._resolve_file_path(board, klass, subject, book, filename, path)
        self._graph.delete_item(item_path)
        self._cache.invalidate_prefix(item_path)

    def copy(self, source_path: str, dest_folder_path: str, new_name: Optional[str] = None) -> str:
        """Copies the item at `source_path` into `dest_folder_path`,
        optionally renaming it. Both paths are AI_TUTOR-relative (use
        resolve_path() to build them from board/klass/subject/book if
        needed). Returns the destination path."""
        name = new_name or source_path.rstrip("/").split("/")[-1]
        self._graph.ensure_folder(dest_folder_path)
        self._graph.copy_item(source_path, dest_folder_path, name)
        self._cache.invalidate_prefix(dest_folder_path)
        return f"{dest_folder_path.rstrip('/')}/{name}"

    def move(self, source_path: str, dest_folder_path: str, new_name: Optional[str] = None) -> str:
        """Moves (and optionally renames) the item at `source_path` into
        `dest_folder_path`. Returns the destination path."""
        self._graph.ensure_folder(dest_folder_path)
        result = self._graph.move_item(source_path, dest_folder_path, new_name)
        self._cache.invalidate_prefix(source_path)
        self._cache.invalidate_prefix(dest_folder_path)
        name = new_name or result.get("name") or source_path.rstrip("/").split("/")[-1]
        return f"{dest_folder_path.rstrip('/')}/{name}"
