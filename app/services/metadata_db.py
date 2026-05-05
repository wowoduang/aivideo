from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

from app.utils import workspace


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        FOREIGN KEY(email) REFERENCES users(email) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY(email) REFERENCES users(email) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        owner_email TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        thumbnail_url TEXT,
        video_url TEXT,
        video_file_name TEXT,
        video_duration_sec REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        current_step TEXT NOT NULL,
        inference_mode TEXT,
        uploaded_video_path TEXT,
        uploaded_subtitle_path TEXT,
        config_json TEXT,
        script_items_json TEXT,
        FOREIGN KEY(owner_email) REFERENCES users(email) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_owner_updated
    ON projects(owner_email, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        task_id TEXT PRIMARY KEY,
        owner_email TEXT,
        project_id TEXT,
        job_type TEXT NOT NULL,
        task_dir TEXT NOT NULL,
        status TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        message TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        result_json TEXT,
        FOREIGN KEY(owner_email) REFERENCES users(email) ON DELETE SET NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_jobs_owner_updated
    ON jobs(owner_email, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_jobs_project_updated
    ON jobs(project_id, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        owner_email TEXT,
        project_id TEXT,
        task_id TEXT,
        artifact_type TEXT NOT NULL,
        path TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata_json TEXT,
        UNIQUE(project_id, task_id, artifact_type, path),
        FOREIGN KEY(owner_email) REFERENCES users(email) ON DELETE SET NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES jobs(task_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_artifacts_project_updated
    ON artifacts(project_id, updated_at DESC)
    """,
)


_INITIALIZED_PATHS: set[str] = set()


def db_path() -> str:
    root = workspace.state_dir("metadata", create=True)
    return os.path.join(root, "app.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if path not in _INITIALIZED_PATHS:
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)
            conn.commit()
            _INITIALIZED_PATHS.add(path)
        yield conn
        conn.commit()
    finally:
        conn.close()



def fetch_one(query: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(query, tuple(params)).fetchone()



def fetch_all(query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute(query, tuple(params)).fetchall())



def execute(query: str, params: Iterable[Any] = ()) -> None:
    with connect() as conn:
        conn.execute(query, tuple(params))



def execute_many(query: str, rows: Iterable[Iterable[Any]]) -> None:
    with connect() as conn:
        conn.executemany(query, [tuple(row) for row in rows])



def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)



def json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default
