"""SQLAlchemy engine/session wiring for the Flask app."""

from __future__ import annotations

import logging

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

db = SQLAlchemy(session_options={"expire_on_commit": False})


def _configure_sqlite(dbapi_connection, connection_record):  # noqa: ANN001
    """SQLite pragmas: WAL for concurrent readers, FK enforcement, busy waits."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=20000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


_sqlite_configured = False


def init_db(app) -> None:
    """Attach SQLAlchemy (and Alembic via Flask-Migrate) to the app.

    The database directory is created up front and pending migrations are
    applied once at startup so a fresh deploy is immediately usable.
    """
    global _sqlite_configured

    cfg = app.config["SKILLET"]
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = cfg.DATABASE_URI
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False, "timeout": 20},
    }
    db.init_app(app)

    if cfg.DATABASE_URI.startswith("sqlite") and not _sqlite_configured:
        event.listen(Engine, "connect", _configure_sqlite)
        _sqlite_configured = True

    from flask_migrate import Migrate

    Migrate(app, db, directory=str(_migrations_dir()))

    with app.app_context():
        _apply_pending_migrations(app)


def _migrations_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "migrations"


def _apply_pending_migrations(app) -> None:
    """Run `flask db upgrade` semantics at boot (idempotent)."""
    from alembic.config import Config as AlembicConfig
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from flask_migrate import upgrade

    migrations = _migrations_dir()
    if not (migrations / "env.py").is_file():
        return  # `flask db init` has not been run in this checkout
    alembic_cfg = AlembicConfig()
    alembic_cfg.set_main_option("script_location", str(migrations))
    script = ScriptDirectory.from_config(alembic_cfg)
    with db.engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
    heads = set(script.get_heads())
    if set(current) == heads:
        return
    logger.info("Applying database migrations (current=%s heads=%s)", current, sorted(heads))
    try:
        upgrade()
    except Exception:  # pragma: no cover - boot-time safety net
        logger.exception("Database migration failed")
        raise


def table_exists(model) -> bool:  # noqa: ANN001
    return inspect(db.engine).has_table(model.__tablename__)
