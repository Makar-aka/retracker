import time
import sqlite3
import json
import socket
import re
from typing import Union, Dict, Any
from dataclasses import dataclass

TIMENOW = int(time.time())
PEERS_LIST_PREFIX = "peers_"
PEERS_LIST_EXPIRE = 300

@dataclass
class Config:
    tr_cache_type: str
    tr_db_type: str
    tr_cache: Dict
    tr_db: Dict
    announce_interval: int
    peer_expire_factor: float
    numwant: int
    run_gc_key: str

class CacheCommon:
    def __init__(self):
        self.used = False
    def get(self, name: str) -> Any:
        return False
    def set(self, name: str, value: Any, ttl: int = 0) -> bool:
        return False
    def rm(self, name: str) -> bool:
        return False

class CacheSQLite(CacheCommon):
    def __init__(self, config: Dict):
        super().__init__()
        self.used = True
        self.cfg = {
            'db_file_path': '/dev/shm/tr.cache.sqlite',
            'table_name': 'cache',
            'table_schema': '''CREATE TABLE IF NOT EXISTS cache (
                cache_name VARCHAR(255),
                cache_expire_time INTEGER,
                cache_value TEXT,
                PRIMARY KEY (cache_name)
            )''',
            'pconnect': True,
            'con_required': True,
            'log_name': 'CACHE'
        }
        self.cfg.update(config)
        self.db = sqlite3.connect(self.cfg['db_file_path'])
        self.db.execute(self.cfg['table_schema'])
        self.db.commit()
    def get(self, name: str) -> Any:
        cursor = self.db.execute(
            f"SELECT cache_value FROM {self.cfg['table_name']} "
            f"WHERE cache_name = ? AND cache_expire_time > ?",
            (name, TIMENOW)
        )
        row = cursor.fetchone()
        return json.loads(row[0]) if row else False
    def set(self, name: str, value: Any, ttl: int = 86400) -> bool:
        expire = TIMENOW + ttl
        try:
            self.db.execute(
                f"REPLACE INTO {self.cfg['table_name']} "
                f"(cache_name, cache_expire_time, cache_value) VALUES (?, ?, ?)",
                (name, expire, json.dumps(value))
            )
            self.db.commit()
            return True
        except Exception:
            return False
    def gc(self, expire_time: int = None) -> int:
        if expire_time is None:
            expire_time = TIMENOW
        cursor = self.db.execute(
            f"DELETE FROM {self.cfg['table_name']} WHERE cache_expire_time < ?",
            (expire_time,)
        )
        self.db.commit()
        return cursor.rowcount

def bencode(var: Any) -> bytes:
    if isinstance(var, str):
        var_bytes = var.encode('utf-8')
        return f"{len(var_bytes)}:".encode() + var_bytes
    elif isinstance(var, (int, float)):
        return f"i{int(var)}e".encode()
    elif isinstance(var, dict):
        if not var:
            return b"de"
        items = []
        for k, v in sorted(var.items()):
            items.append(bencode(str(k)) + bencode(v))
        return b"d" + b"".join(items) + b"e"
    elif isinstance(var, list):
        return b"l" + b"".join(bencode(i) for i in var) + b"e"
    else:
        raise ValueError(f"Cannot bencode type: {type(var)}")

def encode_ip(ip: str) -> str:
    return ''.join(f"{int(x):02x}" for x in ip.split('.'))

def decode_ip(ip_hex: str) -> str:
    return socket.inet_ntoa(bytes.fromhex(ip_hex))

def verify_ip(ip: str) -> bool:
    return bool(re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip))

def msg_die(msg: str) -> None:
    output = bencode({
        'min interval': 1800,
        'failure reason': msg
    })
    raise Exception(output)