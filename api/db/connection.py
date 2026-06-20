import logging
import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from api.config import settings

logger = logging.getLogger("djama.db")

# ThreadedConnectionPool: min=1, max=10 connections
# Created once at module load; Vercel reuses the same process across warm invocations.
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=settings.DATABASE_URL,
        )
        logger.info("PostgreSQL connection pool created (min=1, max=10)")
    return _pool


@contextmanager
def get_db_connection():
    """Borrow a connection from the pool, return it when done."""
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Return connection to pool (not closed)
        pool.putconn(conn)


def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
    """Execute a query and optionally fetch results."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()
            return None


def execute_ddl(statement: str):
    """Execute a DDL statement with autocommit=True (required for ALTER TYPE etc.)."""
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
    finally:
        pool.putconn(conn)
