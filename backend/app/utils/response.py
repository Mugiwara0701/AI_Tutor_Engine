"""
Small helpers to keep API responses in a consistent shape:

{
  "success": true,
  "message": "...",
  "data": { ... }
}
"""

from typing import Any, Optional

from fastapi.responses import JSONResponse


def success_response(message: str = "Success", data: Optional[Any] = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "message": message, "data": data},
    )


def error_response(message: str = "Something went wrong", status_code: int = 400, data: Optional[Any] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "data": data},
    )
