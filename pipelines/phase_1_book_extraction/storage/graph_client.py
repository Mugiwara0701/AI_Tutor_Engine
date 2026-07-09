"""
storage/graph_client.py — thin wrapper over the Microsoft Graph HTTP API
for the specific set of drive-item operations OneDriveStorage needs.

This is the ONLY module in the project that should ever construct a Graph
URL or call `requests` against graph.microsoft.com. Everything above it
(onedrive_storage.py) works in terms of paths and bytes/dicts, not Graph
item IDs or REST verbs.

Every method here goes through _request(), which attaches the bearer
token, applies the configured timeout, and retries transient failures
(429 / 5xx / network timeout) via storage.utils.with_retry.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from .auth import TokenManager
from .exceptions import (
    NotFoundError,
    ConflictError,
    TransientAPIError,
    StorageError,
)
from .utils import with_retry

logger = logging.getLogger("storage.graph_client")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class GraphClient:
    def __init__(self, token_manager: TokenManager, config: Dict[str, Any]):
        self._tokens = token_manager
        self._config = config
        self._timeout = config.get("timeout_seconds", 30)

    # -- low-level request plumbing -----------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self._tokens.acquire_token()}"}
        if extra:
            headers.update(extra)
        return headers

    def authenticate(self) -> None:
        """Explicitly triggers MSAL token acquisition now, instead of
        waiting for it to happen lazily on the first real Graph call.
        Every other method already authenticates on demand via
        _headers() -- this exists purely so a caller (OneDriveStorage.
        authenticate(), and above that, an app's startup sequence) can
        surface an interactive device-code prompt or an
        AuthenticationError as its own explicit "Authenticate" step,
        before doing anything else (e.g. migration)."""
        self._tokens.acquire_token()

    @with_retry(exceptions=(TransientAPIError,))
    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        expect_json: bool = True,
        allow_404: bool = False,
    ):
        import requests

        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(extra_headers),
                params=params,
                json=json_body,
                data=data,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as e:
            raise TransientAPIError(f"Network error calling Graph: {e}") from e

        if resp.status_code == 404:
            if allow_404:
                return None
            raise NotFoundError(f"Graph item not found: {url}")

        if resp.status_code == 409:
            raise ConflictError(f"Graph conflict on {method} {url}: {resp.text}")

        if resp.status_code in _TRANSIENT_STATUS:
            raise TransientAPIError(
                f"Graph returned transient status {resp.status_code} on {method} {url}: {resp.text}"
            )

        if resp.status_code >= 400:
            raise StorageError(
                f"Graph request failed ({resp.status_code}) on {method} {url}: {resp.text}"
            )

        if not expect_json or resp.status_code == 204 or not resp.content:
            return resp.content
        return resp.json()

    # -- item lookup by path --------------------------------------------------

    def _item_by_path_url(self, path: str) -> str:
        """Graph addresses drive items either by id or by a colon-suffixed
        path segment: /me/drive/root:/AI_TUTOR/CBSE/...:/  This is the one
        place that builds that URL form."""
        clean = path.strip("/")
        return f"{GRAPH_BASE}/me/drive/root:/{clean}:"

    def get_item(self, path: str) -> Optional[Dict[str, Any]]:
        """Returns the driveItem metadata for `path`, or None if it
        doesn't exist."""
        return self._request("GET", self._item_by_path_url(path), allow_404=True)

    def list_children(self, path: str) -> List[Dict[str, Any]]:
        url = self._item_by_path_url(path) + "/children"
        items: List[Dict[str, Any]] = []
        while url:
            page = self._request("GET", url)
            items.extend(page.get("value", []))
            url = page.get("@odata.nextLink")
        return items

    # -- folder management ----------------------------------------------------

    def ensure_folder(self, path: str) -> Dict[str, Any]:
        """Creates `path` (and any missing parent folders) if it doesn't
        already exist, and returns its driveItem metadata either way.
        Idempotent -- safe to call before every upload."""
        existing = self.get_item(path)
        if existing is not None:
            return existing

        segments = [s for s in path.strip("/").split("/") if s]
        current = ""
        item: Optional[Dict[str, Any]] = None
        for segment in segments:
            parent = current
            current = f"{current}/{segment}" if current else segment
            found = self.get_item(current)
            if found is not None:
                item = found
                continue
            item = self._create_folder(parent, segment)
        return item

    def _create_folder(self, parent_path: str, name: str) -> Dict[str, Any]:
        if parent_path:
            url = self._item_by_path_url(parent_path) + "/children"
        else:
            url = f"{GRAPH_BASE}/me/drive/root/children"
        body = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }
        try:
            return self._request("POST", url, json_body=body)
        except ConflictError:
            # Created concurrently between our get_item check and this
            # call -- fetch and return the now-existing item instead of
            # failing the whole ensure_folder() chain.
            resolved_path = f"{parent_path}/{name}" if parent_path else name
            return self.get_item(resolved_path)

    # -- file content -----------------------------------------------------

    def download_content(self, path: str) -> bytes:
        url = self._item_by_path_url(path) + "/content"
        return self._request("GET", url, expect_json=False)

    def upload_content(self, path: str, data: bytes) -> Dict[str, Any]:
        """Simple upload (Graph's PUT :/content: endpoint). Suitable for
        files up to 4MB, which covers this project's JSON manifests and
        typical source assets. Larger files should use an upload session
        (not implemented here -- see onedrive_storage.py docstring)."""
        url = self._item_by_path_url(path) + "/content"
        return self._request(
            "PUT",
            url,
            data=data,
            extra_headers={"Content-Type": "application/octet-stream"},
        )

    # -- delete / copy / move ----------------------------------------------

    def delete_item(self, path: str) -> None:
        url = self._item_by_path_url(path)
        self._request("DELETE", url, expect_json=False, allow_404=True)

    def copy_item(self, source_path: str, dest_parent_path: str, new_name: str) -> None:
        """Graph's copy is asynchronous (returns 202 + a monitor URL); for
        this SDK's use case (small JSON/text files, not media libraries)
        we fire the request and don't poll the monitor link -- callers
        needing a synchronous guarantee should follow up with exists()."""
        url = self._item_by_path_url(source_path) + "/copy"
        parent_item = self.get_item(dest_parent_path)
        if parent_item is None:
            raise NotFoundError(f"Copy destination folder does not exist: {dest_parent_path}")
        body = {
            "parentReference": {"id": parent_item["id"]},
            "name": new_name,
        }
        self._request("POST", url, json_body=body, expect_json=False)

    def move_item(self, source_path: str, dest_parent_path: str, new_name: Optional[str] = None) -> Dict[str, Any]:
        url = self._item_by_path_url(source_path)
        parent_item = self.get_item(dest_parent_path)
        if parent_item is None:
            raise NotFoundError(f"Move destination folder does not exist: {dest_parent_path}")
        body: Dict[str, Any] = {"parentReference": {"id": parent_item["id"]}}
        if new_name:
            body["name"] = new_name
        return self._request("PATCH", url, json_body=body)
