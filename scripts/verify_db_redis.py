#!/usr/bin/env python3
"""DB + Redis runtime verification (runtime-audit t11.3, §8.3).

DB: safe SELECT 1 -> alembic revision == script head -> required tables exist.
No destructive queries. Redis: ping -> set/get/del one unique temporary key
(no flushdb/flushall ever). Honest PASS/FAIL/SKIP per check; the exit code
reflects the real result.
"""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

REQUIRED_TABLES = {"videos", "clips", "jobs", "rendered_assets", "publications"}


def check_db() -> bool:
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, inspect, text

    from app.core.config import get_settings

    url = get_settings().database_url
    # safe display: hide userinfo credentials (postgresql://user:pass@host/...)
    scheme, _, rest = url.partition("://")
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    print(f"      database: {scheme}://{rest}")

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[PASS] DB connectivity (SELECT 1)")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] DB connectivity: {type(exc).__name__}: {exc}")
        return False

    ok = True
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "alembic_version" not in tables:
            print("[FAIL] schema: no alembic_version table (run: alembic upgrade head)")
            ok = False
        else:
            with engine.connect() as conn:
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
            cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
            head = ScriptDirectory.from_config(cfg).get_current_head()
            if revision == head:
                print(f"[PASS] schema: revision {revision} == head")
            else:
                print(f"[FAIL] schema: revision {revision} != head {head} (run: alembic upgrade head)")
                ok = False
        missing = REQUIRED_TABLES - tables
        if missing:
            print(f"[FAIL] schema: missing required tables: {sorted(missing)}")
            ok = False
        else:
            print("[PASS] schema: required tables present")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] schema inspection: {type(exc).__name__}: {exc}")
        ok = False
    finally:
        engine.dispose()
    return ok


def check_redis() -> bool:
    """Returns True when redis is PASS or an honest SKIP (eager/dev mode)."""
    from app.core.config import get_settings

    settings = get_settings()
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        client.ping()
        print("[PASS] Redis ping")
    except Exception as exc:  # noqa: BLE001
        if settings.celery_eager_by_default:
            print(f"[SKIP] Redis unreachable, but Celery runs in eager mode ({type(exc).__name__}).")
            print("       Start Redis and set CELERY_TASK_ALWAYS_EAGER=0 for the full mode.")
            return True
        print(f"[FAIL] Redis ping: {type(exc).__name__}: {exc}")
        return False

    key = f"ai-clipper:verify:{uuid.uuid4().hex[:12]}"
    value = f"verify-{uuid.uuid4().hex[:8]}"
    try:
        client.set(key, value, ex=60)
        got = client.get(key)
        if got is None or got.decode() != value:
            print("[FAIL] Redis roundtrip: value mismatch")
            return False
        print("[PASS] Redis set/get (unique temporary key)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] Redis roundtrip: {type(exc).__name__}: {exc}")
        return False
    finally:
        try:
            client.delete(key)
            print("[PASS] Redis cleanup (key deleted)")
        except Exception:  # noqa: BLE001
            print(f"[WARN] Redis cleanup failed for {key}")


def main() -> int:
    db_ok = check_db()
    redis_ok = check_redis()
    print("\nRESULT:", "PASS" if (db_ok and redis_ok) else "FAIL")
    return 0 if (db_ok and redis_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
