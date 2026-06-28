"""SQLite 数据库操作（日志 + 健康记录）。"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.config import get_settings

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """获取线程局部连接。"""
    if not hasattr(_local, "conn"):
        settings = get_settings()
        conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    """初始化数据库表。"""
    with _get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                op_type TEXT NOT NULL,
                target_source TEXT,
                detail TEXT,
                ip TEXT,
                operator TEXT
            );

            CREATE TABLE IF NOT EXISTS health_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                source_name TEXT,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                message TEXT,
                checked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS access_users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                access_key TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                request_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_logs_ts ON operation_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_health_src ON health_records(source_id, checked_at);
            CREATE INDEX IF NOT EXISTS idx_health_checked ON health_records(checked_at);
            CREATE INDEX IF NOT EXISTS idx_access_users_key ON access_users(access_key);
            """
        )


@contextmanager
def get_conn():
    """获取连接上下文管理器（自动提交）。"""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------- 操作日志 ----------------


def add_log(
    op_type: str,
    target_source: Optional[str] = None,
    detail: Optional[str] = None,
    ip: Optional[str] = None,
    operator: str = "admin",
) -> None:
    """记录操作日志。"""
    ts = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO operation_logs (timestamp, op_type, target_source, detail, ip, operator) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, op_type, target_source, detail, ip, operator),
        )


def query_logs(
    op_type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询操作日志（分页）。"""
    conditions = []
    params: list = []
    if op_type and op_type != "all":
        conditions.append("op_type = ?")
        params.append(op_type)
    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    with _get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM operation_logs{where}", params).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM operation_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    items = [dict(r) for r in rows]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_recent_logs(limit: int = 20) -> list[dict]:
    """获取最近的操作日志。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM operation_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------- 健康记录 ----------------


def add_health_record(
    source_id: str,
    source_name: str,
    status: str,
    latency_ms: Optional[int],
    message: str = "",
) -> None:
    """记录一次健康检查结果。"""
    ts = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO health_records (source_id, source_name, status, latency_ms, message, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, source_name, status, latency_ms, message, ts),
        )


def query_health_records(
    source_id: Optional[str] = None, page: int = 1, page_size: int = 20
) -> dict:
    """查询健康检查记录（分页）。"""
    conditions = []
    params: list = []
    if source_id:
        conditions.append("source_id = ?")
        params.append(source_id)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    with _get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM health_records{where}", params
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM health_records{where} ORDER BY checked_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    items = [dict(r) for r in rows]
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


def get_latest_health_by_source(source_id: str) -> Optional[dict]:
    """获取某个书源最近一次健康记录。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM health_records WHERE source_id = ? ORDER BY checked_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
    return dict(row) if row else None


def get_latest_health_records() -> list[dict]:
    """获取每个书源最近一次健康记录。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT h.* FROM health_records h "
            "INNER JOIN (SELECT source_id, MAX(checked_at) AS max_ts FROM health_records GROUP BY source_id) latest "
            "ON h.source_id = latest.source_id AND h.checked_at = latest.max_ts "
            "ORDER BY h.checked_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_health_trend() -> list[dict]:
    """获取近24小时平均延迟趋势（按小时聚合）。"""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=now.hour - 23, minute=0, second=0, microsecond=0).isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT strftime('%Y-%m-%dT%H:00:00', checked_at) AS hour, "
            "AVG(latency_ms) AS avg_latency, COUNT(*) AS cnt "
            "FROM health_records WHERE checked_at >= ? AND latency_ms IS NOT NULL "
            "GROUP BY hour ORDER BY hour",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_health_overview() -> dict:
    """获取健康概览统计。"""
    with _get_conn() as conn:
        # 最近一次检查的各源状态
        rows = conn.execute(
            "SELECT h.* FROM health_records h "
            "INNER JOIN (SELECT source_id, MAX(checked_at) AS max_ts FROM health_records GROUP BY source_id) latest "
            "ON h.source_id = latest.source_id AND h.checked_at = latest.max_ts"
        ).fetchall()
    total = len(rows)
    healthy = sum(1 for r in rows if r["status"] == "healthy")
    unhealthy = sum(1 for r in rows if r["status"] == "unhealthy")
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    last_check = max((r["checked_at"] for r in rows), default=None)
    return {
        "total": total,
        "healthy": healthy,
        "unhealthy": unhealthy,
        "avg_latency_ms": avg_latency,
        "last_check": last_check,
    }


# ---------------- 访问用户 ----------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_access_user(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    return item


def generate_access_key() -> str:
    """Generate a URL-safe access key for public reading APIs."""
    return uuid4().hex + uuid4().hex


def list_access_users() -> list[dict]:
    """List all reading-app access users."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM access_users ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_access_user(row) for row in rows]


def create_access_user(name: str, note: str = "") -> dict:
    """Create a reading-app access user with an individual key."""
    ts = _now_iso()
    user_id = uuid4().hex
    access_key = generate_access_key()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO access_users "
            "(id, name, access_key, enabled, note, request_count, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, 0, ?, ?)",
            (user_id, name, access_key, note, ts, ts),
        )
        row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_access_user(row)


def get_access_user(user_id: str) -> Optional[dict]:
    """Get a reading-app access user by id."""
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_access_user(row) if row else None


def get_enabled_access_user_by_key(access_key: str) -> Optional[dict]:
    """Get an enabled access user by key."""
    if not access_key:
        return None
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM access_users WHERE access_key = ? AND enabled = 1",
                (access_key,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    return _row_to_access_user(row) if row else None


def count_enabled_access_users() -> int:
    """Return the number of enabled access users."""
    try:
        with _get_conn() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM access_users WHERE enabled = 1").fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def update_access_user(
    user_id: str,
    name: Optional[str] = None,
    note: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict]:
    """Update access user fields."""
    existing = get_access_user(user_id)
    if not existing:
        return None

    next_name = existing["name"] if name is None else name
    next_note = (existing.get("note") or "") if note is None else note
    next_enabled = existing["enabled"] if enabled is None else enabled
    ts = _now_iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE access_users SET name = ?, note = ?, enabled = ?, updated_at = ? WHERE id = ?",
            (next_name, next_note, 1 if next_enabled else 0, ts, user_id),
        )
        row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_access_user(row)


def rotate_access_user_key(user_id: str) -> Optional[dict]:
    """Replace an access user's key."""
    if not get_access_user(user_id):
        return None
    ts = _now_iso()
    access_key = generate_access_key()
    with get_conn() as conn:
        conn.execute(
            "UPDATE access_users SET access_key = ?, updated_at = ? WHERE id = ?",
            (access_key, ts, user_id),
        )
        row = conn.execute("SELECT * FROM access_users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_access_user(row)


def delete_access_user(user_id: str) -> bool:
    """Delete an access user."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM access_users WHERE id = ?", (user_id,))
    return cur.rowcount > 0


def record_access_user_usage(access_key: str) -> None:
    """Record public API usage for an access key."""
    if not access_key:
        return
    ts = _now_iso()
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE access_users "
                "SET request_count = request_count + 1, last_used_at = ? "
                "WHERE access_key = ? AND enabled = 1",
                (ts, access_key),
            )
    except sqlite3.OperationalError:
        return
