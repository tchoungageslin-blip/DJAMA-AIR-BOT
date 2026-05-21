import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from api.config import settings


@contextmanager
def get_db_connection():
    """Get a database connection from the pool."""
    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
