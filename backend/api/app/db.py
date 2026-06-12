import os
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ["DATABASE_URL"]

# Sync endpoints run in FastAPI's threadpool, so a thread-safe pool lets us reuse
# connections instead of paying a TCP+auth round-trip on every request.
_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_MAX = int(os.getenv("DB_POOL_MAX", "10"))

_pool = ThreadedConnectionPool(
    _MIN, _MAX, dsn=DATABASE_URL, cursor_factory=RealDictCursor
)


@contextmanager
def get_db():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()  # release the read snapshot so the conn isn't idle-in-txn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
