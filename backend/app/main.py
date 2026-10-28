"""FastAPI application entry point: `uvicorn app.main:app --reload`."""

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import rules
from app.config import get_settings
from app.db import get_db
from app.routers import auth, tickets, users

settings = get_settings()

app = FastAPI(title="Smart Support Desk API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # JWT travels in the Authorization header, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(users.router)


# --- Error handling: every error leaves as {"detail": str, "code": str, ...} ----

# The one place business-rule errors become HTTP status codes.
DOMAIN_STATUS = {
    rules.NotFound: 404,
    rules.PermissionDenied: 403,
    rules.RuleViolation: 400,
    rules.VersionConflict: 409,
}

HTTP_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}


@app.exception_handler(rules.DomainError)
def domain_error_handler(_: Request, exc: rules.DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=DOMAIN_STATUS.get(type(exc), 400),
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(StarletteHTTPException)
def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": HTTP_CODES.get(exc.status_code, "http_error")},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Flatten Pydantic's errors to {field, message} so the frontend can show them per input.
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query")), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation failed", "code": "validation_error", "errors": errors},
    )


@app.get("/api/health", tags=["meta"])
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """Liveness check that also proves the database is reachable."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unreachable"
    return {"status": "ok", "database": database}
