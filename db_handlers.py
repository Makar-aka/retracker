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
        self._migrate_schema()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.cfg['db_file_path'],
                isolation_level=None,  # Автоматический commit
                check_same_thread=False  # Разрешаем использование в разных потоках
            )
            conn.row_factory = sqlite3.Row  # Для удобного доступа к колонкам
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

    def _migrate_schema(self):
        """Миграция схемы базы данных"""
        try:
            with self.get_connection() as conn:
                # Получаем информацию о существующих колонках
                cursor = conn.execute("PRAGMA table_info(tracker)")
                columns = {row['name'] for row in cursor.fetchall()}

                if 'left' not in columns:
                    logger.info("Добавление колонки 'left' в таблицу tracker")
                    # Создаем временную таблицу с новой схемой
                    conn.execute("""
                        CREATE TABLE tracker_new (
                            info_hash CHAR(20),
                            ip CHAR(8),
                            port INTEGER,
                            left INTEGER DEFAULT 0,
                            update_time INTEGER,
                            PRIMARY KEY (info_hash, ip, port)
                        )
                    """)
                    
                    # Копируем данные из старой таблицы если она существует
                    try:
                        conn.execute("""
                            INSERT INTO tracker_new (info_hash, ip, port, update_time)
                            SELECT info_hash, ip, port, update_time FROM tracker
                        """)
                    except sqlite3.OperationalError:
                        pass  # Таблица не существует

                    # Удаляем старую таблицу и переименовываем новую
                    conn.execute("DROP TABLE IF EXISTS tracker")
                    conn.execute("ALTER TABLE tracker_new RENAME TO tracker")
                    logger.info("Миграция схемы базы данных успешно завершена")
                else:
                    logger.debug("Миграция схемы не требуется")

        except Exception as e:
            logger.error(f"Ошибка миграции схемы: {e}")
            # Если что-то пошло не так, создаем таблицу заново
            with self.get_connection() as conn:
                conn.execute("DROP TABLE IF EXISTS tracker")
                conn.execute(self.cfg['table_schema'])

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
        self.random_fn = "RAND()"
        # Создаем таблицу при инициализации
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self.cfg['table_schema'])
                conn.commit()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения соединения"""
        conn = None
        try:
            conn = mysql.connector.connect(
                host=self.cfg.get('dbhost', 'localhost'),
                user=self.cfg.get('dbuser', 'root'),
                password=self.cfg.get('dbpasswd', ''),
                database=self.cfg.get('dbname', 'tracker'),
                charset='utf8mb4',
                autocommit=True,
                pool_name='tracker_pool',
                pool_size=5,
                pool_reset_session=True,
                get_warnings=True,
                raise_on_warnings=True,
                connection_timeout=5
            )
            yield conn
        except Exception as e:
            logger.error(f"Ошибка соединения с MySQL: {e}")
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
                cursor = conn.cursor(dictionary=True, buffered=True)
                try:
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)

                    if query.strip().upper().startswith('SELECT'):
                        result = cursor.fetchall()
                        return result
                    else:
                        conn.commit()
                        return []
                finally:
                    cursor.close()
            except Exception as e:
                logger.error(f"Ошибка выполнения запроса: {e}")
                raise

    def fetch_rowset(self, query: str, params: tuple = None) -> List[Dict]:
        """Получает набор строк из базы"""
        return self.query(query, params)

    def escape(self, value: str) -> str:
        with self.get_connection() as conn:
            return conn.converter.escape(value)
