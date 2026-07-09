"""
storage/path_resolver.py — the single centralized place that knows how
Board/Class/Subject/Book map to a OneDrive folder path.

No other file in this package (or, later, the rest of the project) should
build one of these paths by hand. That keeps the folder layout a one-place
change if it ever needs to evolve.

Layout:

    <root>/<Board>/Class_<Class>/<Subject>/<Book>/

e.g. PathResolver().resolve("CBSE", "12", "Chemistry", "NCERT_Chemistry_Part_1")
  -> "AI_TUTOR/CBSE/Class_12/Chemistry/NCERT_Chemistry_Part_1"
"""
from typing import Optional

from .utils import normalize_path_component


class PathResolver:
    def __init__(self, root_folder: str = "AI_TUTOR"):
        # Strip slashes so joins below never produce "//" or a trailing "/".
        self.root_folder = root_folder.strip("/")

    def resolve(
        self,
        board: str,
        klass: str,
        subject: str,
        book: Optional[str] = None,
    ) -> str:
        """Builds the folder path for a given Board/Class/Subject/(Book).

        `book` is optional so callers can resolve down to the Subject
        level (e.g. to list all books in a subject) as well as the full
        Book level.
        """
        board_c = normalize_path_component(board)
        subject_c = normalize_path_component(subject)
        klass_c = self._format_class(klass)

        parts = [self.root_folder, board_c, klass_c, subject_c]
        if book:
            parts.append(normalize_path_component(book))
        return "/".join(parts)

    def resolve_file(
        self,
        board: str,
        klass: str,
        subject: str,
        book: str,
        filename: str,
    ) -> str:
        """Builds the full path (folder + filename) for a single file
        inside a Book folder."""
        folder = self.resolve(board, klass, subject, book)
        return f"{folder}/{filename.lstrip('/')}"

    @staticmethod
    def _format_class(klass: str) -> str:
        """Formats a class value as "Class_<N>", tolerating callers who
        already pass "Class_12", "12", or "class 12"."""
        text = str(klass).strip()
        if text.lower().startswith("class"):
            text = text.split("_", 1)[-1] if "_" in text else text.split(" ", 1)[-1]
            text = text.strip("_ ")
        return f"Class_{text}"
