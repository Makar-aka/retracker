from flask import Flask, request, Response
from tracker import *
from db_handlers import SQLiteCommon, MySQLCommon
import configparser
import os
import logging
import urllib.parse

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
    try:
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
        info_hash = request.args.get('info_hash', '')
        if info_hash:
            try:
                info_hash = urllib.parse.unquote_to_bytes(info_hash)
            except Exception as e:
                logger.error(f"Ошибка декодирования info_hash: {e}")
                return Response(bencode({'failure reason': 'Invalid info_hash encoding'}), mimetype='text/plain')

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
        if not ip or not verify_ip(ip):
            logger.warning(f"Некорректный IP адрес: {ip}")
            return Response(bencode({'failure reason': 'Invalid IP'}), mimetype='text/plain')

        # Проверка reported_ip если разрешено
        if not tr_cfg.ignore_reported_ip and 'ip' in request.args:
            reported_ip = request.args.get('ip')
            if tr_cfg.verify_reported_ip and verify_ip(reported_ip):
                ip = reported_ip

        # Дополнительные параметры
        event = request.args.get('event', '')
        uploaded = int(request.args.get('uploaded', 0))
        downloaded = int(request.args.get('downloaded', 0))
        left = int(request.args.get('left', 0))
        compact = int(request.args.get('compact', 0))
        no_peer_id = int(request.args.get('no_peer_id', 0))
        numwant = min(int(request.args.get('numwant', tr_cfg.numwant)), 200)

        # Кэширование списка пиров
        cache_key = f"{PEERS_LIST_PREFIX}{info_hash.hex()}"
        peers_list = tr_cache.get(cache_key) if tr_cache.used else False

        if not peers_list:
            # Обновляем информацию о пире в БД
            db.query(
                f"REPLACE INTO tracker (info_hash, ip, port, update_time) VALUES (?, ?, ?, ?)",
                (info_hash, encode_ip(ip), port, TIMENOW)
            )

            # Получаем список активных пиров
            peers_query = db.fetch_rowset(
                f"SELECT ip, port FROM tracker WHERE info_hash = ? AND update_time > ? ORDER BY {db.random_fn} LIMIT ?",
                (info_hash, TIMENOW - tr_cfg.announce_interval, numwant)
            )

            peers_list = []
            complete = incomplete = 0

            for peer in peers_query:
                if peer.get('left', 0) == 0:
                    complete += 1
                else:
                    incomplete += 1
                
                peer_data = {
                    'ip': decode_ip(peer['ip']),
                    'port': peer['port']
                }
                if not no_peer_id and 'peer_id' in peer:
                    peer_data['peer_id'] = peer['peer_id']
                peers_list.append(peer_data)

            # Кэшируем результат
            if tr_cache.used:
                tr_cache.set(cache_key, {
                    'peers': peers_list,
                    'complete': complete,
                    'incomplete': incomplete
                }, PEERS_LIST_EXPIRE)

        # Формируем ответ
        output = {
            'interval': tr_cfg.announce_interval,
            'min interval': tr_cfg.announce_interval,
            'complete': peers_list.get('complete', 0) if isinstance(peers_list, dict) else 0,
            'incomplete': peers_list.get('incomplete', 0) if isinstance(peers_list, dict) else 0,
            'peers': peers_list.get('peers', []) if isinstance(peers_list, dict) else peers_list
        }

        logger.info(f"Обработан announce запрос от {ip}:{port} для {info_hash.hex()}")
        return Response(bencode(output), mimetype='text/plain')

    except Exception as e:
        logger.error(f"Ошибка обработки announce запроса: {e}")
        return Response(bencode({'failure reason': str(e)}), mimetype='text/plain')

@app.route('/scrape')
def scrape():
    try:
        info_hashes = request.args.getlist('info_hash')
        if not info_hashes:
            return Response(bencode({'failure reason': 'No info_hash provided'}), mimetype='text/plain')

        files = {}
        for info_hash in info_hashes:
            try:
                info_hash = urllib.parse.unquote_to_bytes(info_hash)
                if len(info_hash) != 20:
                    continue

                # Получаем статистику
                stats = db.fetch_rowset(
                    f"SELECT COUNT(*) as total, SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as complete FROM tracker WHERE info_hash = ?",
                    (info_hash,)
                )

                if stats:
                    files[info_hash] = {
                        'complete': stats[0].get('complete', 0) or 0,
                        'downloaded': 0,  # Не храним эту информацию
                        'incomplete': stats[0].get('total', 0) - (stats[0].get('complete', 0) or 0)
                    }

            except Exception as e:
                logger.error(f"Ошибка обработки info_hash в scrape: {e}")
                continue

        return Response(bencode({'files': files}), mimetype='text/plain')

    except Exception as e:
        logger.error(f"Ошибка обработки scrape запроса: {e}")
        return Response(bencode({'failure reason': str(e)}), mimetype='text/plain')

if __name__ == '__main__':
    host = config['TRACKER'].get('host', '0.0.0.0')
    port = config['TRACKER'].getint('port', 8080)
    logger.info(f"Запуск сервера на {host}:{port}")
    app.run(host=host, port=port)