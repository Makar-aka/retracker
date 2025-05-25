import sqlite3
from typing import Dict, List, Any
from threading import local
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# Thread-local storage
thread_local = local()

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.random_fn = "RANDOM()"
        self._migrate_schema()

    @property
    def db(self):
        """Возвращает соединение для текущего потока"""
        if not hasattr(thread_local, 'sqlite_db'):
            thread_local.sqlite_db = sqlite3.connect(
                self.cfg['db_file_path'],
                check_same_thread=False
            )
            thread_local.sqlite_db.row_factory = sqlite3.Row
        return thread_local.sqlite_db

    def _migrate_schema(self):
        """Миграция схемы базы данных"""
        try:
            with self.db as conn:
                cursor = conn.execute("PRAGMA table_info(tracker)")
                columns = {row['name'] for row in cursor.fetchall()}

                if 'left' not in columns:
                    logger.info("Добавление колонки 'left' в таблицу tracker")
                    conn.executescript(self.cfg['table_schema'])
                    conn.commit()
                    logger.info("Миграция схемы базы данных успешно завершена")
                else:
                    logger.debug("Миграция схемы не требуется")

        except Exception as e:
            logger.error(f"Ошибка миграции схемы: {e}")
            with self.db as conn:
                conn.executescript(self.cfg['table_schema'])
                conn.commit()

    def query(self, query: str, params: tuple = None) -> List[Dict]:
        """Выполняет запрос и возвращает результат"""
        try:
            with self.db as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if query.strip().upper().startswith(('SELECT', 'PRAGMA')):
                    columns = [col[0] for col in cursor.description] if cursor.description else []
                    result = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    return result
                else:
                    conn.commit()
                    return []
        except Exception as e:
            logger.error(f"Ошибка выполнения запроса: {e}")
            raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        """Получает набор строк из базы"""
        return self.query(query, params)

    def escape(self, value: str) -> str:
        return value.replace("'", "''")

    def __del__(self):
        """Закрываем соединение при уничтожении объекта"""
        if hasattr(thread_local, 'sqlite_db'):
            try:
                thread_local.sqlite_db.close()
            except:
                pass