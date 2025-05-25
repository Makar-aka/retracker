#!/usr/bin/env python3
import sqlite3
from datetime import datetime
import binascii
import socket

def decode_ip(ip_hex):
    try:
        return socket.inet_ntoa(bytes.fromhex(ip_hex))
    except:
        return ip_hex

def format_info_hash(info_hash):
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

        print("\nСхема таблицы:")
        for col in conn.execute("PRAGMA table_info(tracker)"):
            print(f"{col['name']}: {col['type']}")

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

        print("\nПоследние записи:")
        for row in conn.execute("SELECT * FROM tracker ORDER BY update_time DESC LIMIT 10"):
            print("\n-------------------")
            print(f"Info Hash: {format_info_hash(row['info_hash'])}")
            print(f"IP: {decode_ip(row['ip'])}")
            print(f"Port: {row['port']}")
            print(f"Left: {row['left'] if 'left' in row.keys() else 'N/A'}")
            print(f"Update Time: {datetime.fromtimestamp(row['update_time'])}")
            print("\nВсе поля:")
            for key in row.keys():
                print(f"{key}: {row[key]}")
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/tracker.sqlite'
    view_db(db_path)