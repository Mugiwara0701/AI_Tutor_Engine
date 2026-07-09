"""
Root conftest.py.

Ensures the project root (this file's directory) is on sys.path so that
top-level packages -- `schemas`, `modules`, `prompt_manager`, etc. -- can
be imported from test modules regardless of how pytest is invoked
(`pytest tests/...` vs `python -m pytest`) or which directory it's run
from.

This is test-infrastructure only; it does not modify any pipeline or
schema code.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent)

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)