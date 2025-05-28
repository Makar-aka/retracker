import sqlite3
from typing import Dict, List, Any
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.random_fn = "RANDOM()"
        with self.get_connection() as conn:
            conn.executescript(self.cfg['table_schema'])
            conn.commit()

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = sqlite3.connect(
                self.cfg['db_file_path'],
                isolation_level=None,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            logger.error(f"Ошибка соединения с SQLite: {e}")
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def query(self, query: str, params: tuple = None) -> List[Dict]:
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                if query.strip().upper().startswith(('SELECT', 'PRAGMA')):
                    columns = [col[0] for col in cursor.description] if cursor.description else []
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                return []
            except Exception as e:
                logger.error(f"Ошибка выполнения запроса: {e}")
                raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        return self.query(query, params)

    def escape(self, value: str) -> str:
        return value.replace("'", "''")