from __future__ import annotations

from sqlite3 import Connection as SQLiteConnection

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

try:
    from flask_migrate import Migrate
except ImportError:  # Keeps local development usable before dependencies are installed.
    Migrate = None  # type: ignore[assignment]


db = SQLAlchemy()
migrate = Migrate() if Migrate is not None else None


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if not isinstance(dbapi_connection, SQLiteConnection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
