import mysql.connector
import sqlite3
from typing import Dict, List, Any, Optional
from threading import local

# Добавляем thread-local storage
thread_local = local()

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self._connect()
        self.random_fn = "RANDOM()"

    def _connect(self):
        """Создает новое соединение для текущего потока"""
        if not hasattr(thread_local, 'db'):
            thread_local.db = sqlite3.connect(self.cfg['db_file_path'])
            thread_local.db.execute(self.cfg['table_schema'])
            thread_local.db.commit()

    @property
    def db(self):
        """Возвращает соединение для текущего потока"""
        if not hasattr(thread_local, 'db'):
            self._connect()
        return thread_local.db

    def query(self, query: str, params: tuple = None) -> sqlite3.Cursor:
        try:
            if params:
                return self.db.execute(query, params)
            return self.db.execute(query)
        except sqlite3.OperationalError as e:
            if "thread" in str(e):
                # Если ошибка связана с потоками, пересоздаем соединение
                if hasattr(thread_local, 'db'):
                    delattr(thread_local, 'db')
                self._connect()
                if params:
                    return self.db.execute(query, params)
                return self.db.execute(query)
            raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        cursor = self.query(query, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def escape(self, value: str) -> str:
        return value.replace("'", "''")