import sqlite3
from typing import Dict, List, Any
from contextlib import contextmanager
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.random_fn = "RANDOM()"
        
        # Создаем БД и таблицу при инициализации
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
        """Экранирует специальные символы в строке"""
        return value.replace("'", "''")