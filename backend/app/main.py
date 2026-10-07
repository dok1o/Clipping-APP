"""FastAPI application factory, /health (liveness), /ready (readiness), CORS, unified error handlers."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Clipper API", version=settings.app_version)
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in (settings.frontend_origin,) if o],
        allow_origin_regex=settings.cors_allow_origin_regex or None,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_v1_router)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": settings.app_version, "checks": _health_checks()}

    @app.get("/ready", tags=["system"])
    def ready() -> JSONResponse:
        """Schema-aware readiness (CONTRACTS §4.1a, ADR-022).

        Unlike /health (pure liveness, always 200), this gates on the DB schema:
        the alembic revision must equal the script head and required tables must
        exist — an empty or stale schema is NOT ready (503).
        """
        checks = _health_checks()
        checks["schema"] = _check_schema()
        is_ready = (
            checks.get("db") == "ok" and checks["schema"] == "ok" and checks.get("s3") == "ok"
        )
        payload = {
            "status": "ready" if is_ready else "not_ready",
            "version": settings.app_version,
            "checks": checks,
        }
        return JSONResponse(status_code=200 if is_ready else 503, content=payload)

    return app


def _health_checks() -> dict[str, str]:
    return {"db": _check_db(), "redis": _check_redis(), "s3": _check_s3()}


def _check_db() -> str:
    try:
        from sqlalchemy import text

        from app.db.session import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - health diagnostics only
        logger.debug("health: db check failed: %s", exc)
        return "skip"


def _check_redis() -> str:
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
        )
        client.ping()
        client.close()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.debug("health: redis check failed: %s", exc)
        return "skip"


def _alembic_head() -> str | None:
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    from app.core.config import BACKEND_DIR

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _check_schema() -> str:
    """ok | no_alembic_version | missing_tables | stale_revision:{rev} | error."""
    try:
        from sqlalchemy import inspect, text

        from app.db.session import get_engine

        engine = get_engine()
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" not in tables:
            return "no_alembic_version"
        if "videos" not in tables:
            return "missing_tables"
        head = _alembic_head()
        with engine.connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head is None or revision != head:
            return f"stale_revision:{revision}"
        return "ok"
    except Exception as exc:  # noqa: BLE001 - readiness diagnostics only
        logger.debug("ready: schema check failed: %s", exc)
        return "error"


def _check_s3() -> str:
    try:
        from app.infra.s3 import S3Storage

        S3Storage.from_settings(get_settings()).head_bucket()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.debug("health: s3 check failed: %s", exc)
        return "skip"


app = create_app()
