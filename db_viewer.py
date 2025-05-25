#!/usr/bin/env python3
import sqlite3
from datetime import datetime
import binascii
import socket
import struct

def decode_ip(ip_hex):
    """Преобразует 8 символов hex в IP адрес"""
    try:
        # Преобразуем строку hex в байты и затем в IP
        ip_bytes = bytes.fromhex(ip_hex)
        return socket.inet_ntoa(ip_bytes)
    except:
        return ip_hex

def format_info_hash(info_hash):
    """Преобразует бинарный info_hash в читаемый вид"""
    try:
        if isinstance(info_hash, bytes):
            return binascii.hexlify(info_hash).decode()
        return info_hash
    except:
        return str(info_hash)

def view_db(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Показать схему таблицы
        print("\nСхема таблицы:")
        cursor = conn.execute("PRAGMA table_info(tracker)")
        for col in cursor:
            print(f"{col['name']}: {col['type']}")
        
        # Показать статистику
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_peers,
                COUNT(DISTINCT info_hash) as total_torrents,
                COUNT(DISTINCT ip) as unique_ips,
                MIN(update_time) as oldest_update,
                MAX(update_time) as latest_update
            FROM tracker
        """)
        stats = dict(cursor.fetchone())
        
        print("\nСтатистика:")
        print(f"Всего пиров: {stats['total_peers']}")
        print(f"Уникальных торрентов: {stats['total_torrents']}")
        print(f"Уникальных IP: {stats['unique_ips']}")
        print(f"Старейшая запись: {datetime.fromtimestamp(stats['oldest_update'])}")
        print(f"Последнее обновление: {datetime.fromtimestamp(stats['latest_update'])}")
        
        # Показать последние записи
        print("\nПоследние записи:")
        cursor = conn.execute("""
            SELECT * FROM tracker 
            ORDER BY update_time DESC 
            LIMIT 10
        """)
        
        for row in cursor:
            print("\n-------------------")
            print(f"Info Hash: {format_info_hash(row['info_hash'])}")
            print(f"IP: {decode_ip(row['ip'])}")
            print(f"Port: {row['port']}")
            try:
                left = row['left']
                print(f"Left: {left}")
            except:
                print("Left: N/A")
            print(f"Update Time: {datetime.fromtimestamp(row['update_time'])}")
            
            # Дополнительно покажем все доступные колонки и их значения для 