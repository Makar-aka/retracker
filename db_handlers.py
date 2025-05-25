import mysql.connector
import sqlite3
from typing import Dict, List, Any, Optional

class SQLiteCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.db = sqlite3.connect(config['db_file_path'])
        self.db.execute(config['table_schema'])
        self.db.commit()
        self.random_fn = "RANDOM()"

    def query(self, query: str) -> sqlite3.Cursor:
        return self.db.execute(query)

    def fetch_rowset(self, query: str) -> List[Dict]:
        cursor = self.query(query)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def escape(self, value: str) -> str:
        return value.replace("'", "''")

class MySQLCommon:
    def __init__(self, config: Dict):
        self.cfg = config
        self.db = mysql.connector.connect(
            host=config['dbhost'],
            user=config['dbuser'],
            password=config['dbpasswd'],
            database=config['dbname']
        )
        self.random_fn = "RAND()"

    def query(self, query: str) -> mysql.connector.cursor.MySQLCursor:
        cursor = self.db.cursor(dictionary=True)
        cursor.execute(query)
        return cursor

    def fetch_rowset(self, query: str) -> List[Dict]:
        cursor = self.query(query)
        return cursor.fetchall()

    def escape(self, value: str) -> str:
        return self.db.converter.escape(value)