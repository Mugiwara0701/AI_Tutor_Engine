"""
FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth.routes import router as auth_router
from app.config import settings
from app.dashboard.routes import router as dashboard_router
from app.database.postgres import check_connection
from app.utils.logger import logger
from app.utils.response import error_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info(f"Starting dashboard backend (env={settings.ENVIRONMENT})")

    db_ok = check_connection()
    if db_ok:
        logger.info("✓ PostgreSQL connection OK")
    else:
        logger.error("✗ Could not connect to PostgreSQL. Check DATABASE_URL.")

    if settings.AUTO_CREATE_TABLES:
        logger.info("AUTO_CREATE_TABLES=true → running table setup...")
        try:
            from app.database.init_db import create_tables

            create_tables()
        except SystemExit:
            logger.error("Table auto-creation failed. See errors above.")
        except Exception as exc:
            logger.error(f"Table auto-creation raised an exception: {exc}")

    yield
    # ---- Shutdown ----
    logger.info("Shutting down dashboard backend")


app = FastAPI(
    title="Dashboard Backend",
    description="Self-managed authentication + Supabase-hosted PostgreSQL dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Global exception handling ----

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return error_response(message=str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(message="Validation error", status_code=422, data=exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return error_response(message="Internal server error", status_code=500)


# ---- Routes ----

app.include_router(auth_router)
app.include_router(dashboard_router)


@app.get("/")
def root():
    return {"service": "Dashboard Backend", "docs": "/docs", "health": "/dashboard/health"}
