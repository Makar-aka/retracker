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
        if not hasattr(thread_local, 'sqlite_db'):
            thread_local.sqlite_db = sqlite3.connect(
                self.cfg['db_file_path'],
                check_same_thread=False  # Разрешаем использование в разных потоках
            )
            thread_local.sqlite_db.execute(self.cfg['table_schema'])
            thread_local.sqlite_db.commit()

    @property
    def db(self):
        """Возвращает соединение для текущего потока"""
        if not hasattr(thread_local, 'sqlite_db'):
            self._connect()
        return thread_local.sqlite_db

    def query(self, query: str, params: tuple = None) -> sqlite3.Cursor:
        try:
            cursor = None
            if params:
                cursor = self.db.execute(query, params)
            else:
                cursor = self.db.execute(query)
            self.db.commit()  # Фиксируем изменения
            return cursor
        except sqlite3.OperationalError as e:
            if "thread" in str(e) or "locked" in str(e):
                # Если ошибка связана с потоками или блокировкой, пересоздаем соединение
                if hasattr(thread_local, 'sqlite_db'):
                    try:
                        thread_local.sqlite_db.close()
                    except:
                        pass
                    delattr(thread_local, 'sqlite_db')
                self._connect()
                if params:
                    cursor = self.db.execute(query, params)
                else:
                    cursor = self.db.execute(query)
                self.db.commit()
                return cursor
            raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        try:
            cursor = self.query(query, params)
            columns = [col[0] for col in cursor.description]
            result = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка в fetch_rowset: {e}")
            return []

    def escape(self, value: str) -> str:
        return value.replace("'", "''")

    def __del__(self):
        """Закрываем соединение при уничтожении объекта"""
        if hasattr(thread_local, 'sqlite_db'):
            try:
                thread_local.sqlite_db.close()
            except:
                pass

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