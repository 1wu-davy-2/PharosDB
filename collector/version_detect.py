"""数据库版本检测 — 连接目标库并返回版本字符串。

MySQL/MariaDB: SELECT VERSION()  →  "5.7.44" / "10.5.29-MariaDB" / "8.0.36"
PostgreSQL:    SELECT version()  →  "PostgreSQL 15.3 on x86_64-pc-linux-gnu..."

返回 (db_version_raw, db_type_inferred)
db_type_inferred 用于在 db_type 未指定时自动推断（如 "mysql" / "postgresql"）
"""

import logging

from .crypto import decrypt

logger = logging.getLogger(__name__)


def detect_version(instance) -> tuple[str, str]:
    """连接目标实例，查询版本，返回 (version_raw, db_type_inferred)。

    db_type_inferred: "mysql" / "postgresql" / "unknown"
    """
    password = decrypt(instance.password)

    if instance.db_type == "mysql":
        return _detect_mysql(instance, password)
    elif instance.db_type == "postgresql":
        return _detect_postgresql(instance, password)
    else:
        raise ValueError(f"暂不支持 {instance.db_type} 的版本检测")


def _detect_mysql(instance, password: str) -> tuple[str, str]:
    import pymysql

    conn = pymysql.connect(
        host=instance.host,
        port=instance.port,
        user=instance.username,
        password=password,
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            row = cur.fetchone()
        version_raw = row["v"]

        # 推断是否为 MariaDB（版本字符串含 "MariaDB"）
        db_type_inferred = "mysql"  # pymysql 只用于 MySQL/MariaDB
        logger.info(f"[version_detect] {instance.name} -> {version_raw}")
        return version_raw, db_type_inferred
    finally:
        conn.close()


def _detect_postgresql(instance, password: str) -> tuple[str, str]:
    import psycopg2

    conn = psycopg2.connect(
        host=instance.host,
        port=instance.port,
        user=instance.username,
        password=password,
        connect_timeout=5,
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version_raw = cur.fetchone()[0]
        cur.close()
        logger.info(f"[version_detect] {instance.name} -> {version_raw}")
        return version_raw, "postgresql"
    finally:
        conn.close()


def parse_mysql_version(version_raw: str) -> tuple[int, int, bool]:
    """解析 MySQL/MariaDB 版本字符串，返回 (major, minor, is_mariadb)。

    示例:
      "5.7.44"           → (5, 7, False)
      "8.0.36"           → (8, 0, False)
      "10.5.29-MariaDB"  → (10, 5, True)
    """
    is_mariadb = "MariaDB" in version_raw
    raw = version_raw.split("-")[0]
    parts = raw.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        major, minor = 5, 7
    return major, minor, is_mariadb
