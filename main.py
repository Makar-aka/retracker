from flask import Flask, request, Response
from tracker import *
import configparser
import os

app = Flask(__name__)

# Загрузка конфигурации
config = configparser.ConfigParser()
config.read('config.ini')

tr_cfg = Config(
    tr_cache_type=config['CACHE']['type'],
    tr_db_type=config['DB']['type'],
    tr_cache=config['CACHE'],
    tr_db=config['DB'],
    announce_interval=int(config['TRACKER']['announce_interval']),
    peer_expire_factor=float(config['TRACKER']['peer_expire_factor']),
    ignore_reported_ip=config['TRACKER'].getboolean('ignore_reported_ip'),
    verify_reported_ip=config['TRACKER'].getboolean('verify_reported_ip'),
    allow_internal_ip=config['TRACKER'].getboolean('allow_internal_ip'),
    numwant=int(config['TRACKER']['numwant']),
    run_gc_key=config['TRACKER']['run_gc_key']
)

# Инициализация кэша
if tr_cfg.tr_cache_type == 'sqlite':
    tr_cache = CacheSQLite(tr_cfg.tr_cache)
else:
    tr_cache = CacheCommon()

# Инициализация БД
if tr_cfg.tr_db_type == 'mysql':
    db = MySQLCommon(tr_cfg.tr_db)
elif tr_cfg.tr_db_type == 'sqlite':
    default_cfg = {
        'db_file_path': '/dev/shm/tr.db.sqlite',
        'table_name': 'tracker',
        'table_schema': '''CREATE TABLE IF NOT EXISTS tracker (
            info_hash CHAR(20),
            ip CHAR(8),
            port INTEGER,
            update_time INTEGER,
            PRIMARY KEY (info_hash, ip, port)
        )''',
        'pconnect': True,
        'con_required': True,
        'log_name': 'SQLite'
    }
    db = SQLiteCommon({**default_cfg, **tr_cfg.tr_db})
else:
    raise ValueError('Unsupported DB type')

@app.route('/announce')
def announce():
    # Garbage collector
    if tr_cfg.run_gc_key in request.args:
        announce_interval = max(int(tr_cfg.announce_interval), 60)
        expire_factor = max(float(tr_cfg.peer_expire_factor), 2)
        peer_expire_time = TIMENOW - int(announce_interval * expire_factor)

        db.query(f"DELETE FROM tracker WHERE update_time < {peer_expire_time}")
        
        if hasattr(tr_cache, 'gc'):
            tr_cache.gc()
        
        return Response("OK", mimetype='text/plain')

    # Получение и проверка параметров
    info_hash = request.args.get('info_hash')
    if not info_hash or len(info_hash) != 20:
        return Response(bencode({'failure reason': 'Invalid info_hash'}), mimetype='text/plain')

    try:
        port = int(request.args.get('port', 0))
    except ValueError:
        port = 0
    
    if not 0 <= port <= 0xFFFF:
        return Response(bencode({'failure reason': 'Invalid port'}), mimetype='text/plain')

    # Обработка IP
    ip = request.remote_addr
    
    # ... остальная логика обработки запроса ...

    return Response(bencode(output), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)