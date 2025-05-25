import mysql.connector
import sqlite3
from typing import Dict, List, Any, Optional
from threading import local
from contextlib import contextmanager
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# Thread-local storage
thread_local = local()

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.random_fn = "RANDOM()"
        # Создаем таблицу при инициализации
        with self.get_connection() as conn:
            conn.execute(self.cfg['table_schema'])
            conn.commit()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.cfg['db_file_path'],
                isolation_level=None  # Автоматический commit
            )
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
        """Выполняет запрос и возвращает результат"""
        with self.get_connection() as conn:
            try:
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

class MySQLCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self._connect()
        self.random_fn = "RAND()"

    def _connect(self):
        """Создает новое соединение для текущего потока"""
        if not hasattr(thread_local, 'mysql_db'):
            thread_local.mysql_db = mysql.connector.connect(
                host=self.cfg.get('dbhost', 'localhost'),
                user=self.cfg.get('dbuser', 'root'),
                password=self.cfg.get('dbpasswd', ''),
                database=self.cfg.get('dbname', 'tracker'),
                charset='utf8mb4',
                autocommit=True,  # Автоматический commit
                pool_name='tracker_pool',
                pool_size=5,  # Размер пула соединений
                get_warnings=True,
                raise_on_warnings=True
            )
            # Создаем таблицу если она не существует
            with thread_local.mysql_db.cursor() as cursor:
                cursor.execute(self.cfg['table_schema'])
                thread_local.mysql_db.commit()

    @property
    def db(self):
        """Возвращает соединение для текущего потока"""
        if not hasattr(thread_local, 'mysql_db') or not thread_local.mysql_db.is_connected():
            self._connect()
        return thread_local.mysql_db

    def query(self, query: str, params: tuple = None) -> mysql.connector.cursor.MySQLCursor:
        try:
            cursor = self.db.cursor(dictionary=True, buffered=True)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.db.commit()
            return cursor
        except (mysql.connector.OperationalError, mysql.connector.InterfaceError) as e:
            # Переподключаемся при потере соединения
            if hasattr(thread_local, 'mysql_db'):
                try:
                    thread_local.mysql_db.close()
                except:
                    pass
                delattr(thread_local, 'mysql_db')
            self._connect()
            cursor = self.db.cursor(dictionary=True, buffered=True)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            self.db.commit()
            return cursor
        except Exception as e:
            logger.error(f"Ошибка в query: {e}")
            raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        try:
            cursor = self.query(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка в fetch_rowset: {e}")
            return []

    def escape(self, value: str) -> str:
        return self.db.converter.escape(value)

    def __del__(self):
        """Закрываем соединение при уничтожении объекта"""
        if hasattr(thread_local, 'mysql_db'):
            try:
                thread_local.mysql_db.close()
            except:
                pass

# Добавляем логирование
import logging
logger = logging.getLogger(__name__)