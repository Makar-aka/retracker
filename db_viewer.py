#!/usr/bin/env python3
import sqlite3
from datetime import datetime
import binascii
import socket
import struct

def decode_ip(ip_hex):
    """����������� 8 �������� hex � IP �����"""
    try:
        # ����������� ������ hex � ����� � ����� � IP
        ip_bytes = bytes.fromhex(ip_hex)
        return socket.inet_ntoa(ip_bytes)
    except:
        return ip_hex

def format_info_hash(info_hash):
    """����������� �������� info_hash � �������� ���"""
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
        
        # �������� ����� �������
        print("\n����� �������:")
        cursor = conn.execute("PRAGMA table_info(tracker)")
        for col in cursor:
            print(f"{col['name']}: {col['type']}")
        
        # �������� ����������
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
        
        print("\n����������:")
        print(f"����� �����: {stats['total_peers']}")
        print(f"���������� ���������: {stats['total_torrents']}")
        print(f"���������� IP: {stats['unique_ips']}")
        print(f"��������� ������: {datetime.fromtimestamp(stats['oldest_update'])}")
        print(f"��������� ����������: {datetime.fromtimestamp(stats['latest_update'])}")
        
        # �������� ��������� ������
        print("\n��������� ������:")
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
            print(f"Left: {row.get('left', 'N/A')}")
            print(f"Update Time: {datetime.fromtimestamp(row['update_time'])}")
            
    except Exception as e:
        print(f"������: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/tracker.sqlite'
    view_db(db_path)