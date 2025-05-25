from flask import Flask, request, Response
from tracker import *
from db_handlers import SQLiteCommon, MySQLCommon
import configparser
import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Создание директории для базы данных
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    logger.info(f"Создана директория для базы данных: {data_dir}")

# Загрузка конфигурации
config = configparser.ConfigParser()
config.read('config.ini')

logger.info("Загрузка конфигурации...")

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
logger.info(f"Инициализация кэша типа: {tr_cfg.tr_cache_type}")
if tr_cfg.tr_cache_type == 'sqlite':
    tr_cache = CacheSQLite(tr_cfg.tr_cache)
else:
    tr_cache = CacheCommon()

# Инициализация БД
logger.info(f"Инициализация БД типа: {tr_cfg.tr_db_type}")
if tr_cfg.tr_db_type == 'mysql':
    db = MySQLCommon(tr_cfg.tr_db)
elif tr_cfg.tr_db_type == 'sqlite':
    default_cfg = {
        'db_file_path': os.path.join(data_dir, 'tracker.sqlite'),
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
    logger.info(f"База данных SQLite инициализирована: {default_cfg['db_file_path']}")
else:
    raise ValueError('Unsupported DB type')

@app.route('/announce')
def announce():
    # Garbage collector
    if tr_cfg.run_gc_key in request.args:
        logger.info("Запущена сборка мусора")
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
        logger.warning(f"Получен некорректный info_hash от {request.remote_addr}")
        return Response(bencode({'failure reason': 'Invalid info_hash'}), mimetype='text/plain')

    try:
        port = int(request.args.get('port', 0))
    except ValueError:
        port = 0
    
    if not 0 <= port <= 0xFFFF:
        logger.warning(f"Получен некорректный порт от {request.remote_addr}: {port}")
        return Response(bencode({'failure reason': 'Invalid port'}), mimetype='text/plain')

    # Обработка IP
    ip = request.remote_addr
    logger.debug(f"Запрос announce от {ip}:{port}")
    
    # ... остальная логика обработки запроса ...

    return Response(bencode(output), mimetype='text/plain')

if __name__ == '__main__':
    host = config['TRACKER'].get('host', '0.0.0.0')
    port = config['TRACKER'].getint('port', 8080)
    logger.info(f"Запуск сервера на {host}:{port}")
    app.run(host=host, port=port)