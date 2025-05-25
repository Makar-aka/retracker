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
        
        # Создаем БД и таблицу при инициализации
        with self.get_connection() as conn:
            conn.execute(self.cfg['table_schema'])
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