from flask import Flask, request, Response, render_template, redirect, url_for
from tracker import *
from db_handlers import SQLiteCommon
import configparser
from logging.handlers import RotatingFileHandler
import logging
import os
import urllib.parse
import socket
import time
import json
import datetime
import base64

# Создаем приложение Flask
app = Flask(__name__)
app.start_time = time.time()

# Загрузка конфигурации
config = configparser.ConfigParser()
config.read('config.ini')

# Создание директории для данных
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Настройка логирования
log_file = config['LOGGING'].get('log_file', 'data/tracker.log')
log_dir = os.path.dirname(log_file)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Очистка старых логов если включено
if config['LOGGING'].getboolean('clear_on_start', False) and os.path.exists(log_file):
    try:
        os.remove(log_file)
        for i in range(int(config['LOGGING'].get('backup_count', 5))):
            backup = f"{log_file}.{i+1}"
            if os.path.exists(backup):
                os.remove(backup)
    except Exception as e:
        print(f"Ошибка при очистке старых логов: {e}")

# Настройка обработчиков логов
handlers = []

# Файловый обработчик с ротацией
file_handler = RotatingFileHandler(
    filename=log_file,
    maxBytes=int(config['LOGGING'].get('max_bytes', 5242880)),
    backupCount=int(config['LOGGING'].get('backup_count', 5)),
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(config['LOGGING'].get('format', '%(asctime)s [%(levelname)s] %(message)s')))
handlers.append(file_handler)

# Консольный обработчик если включен
if config['LOGGING'].getboolean('console_output', True):
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(config['LOGGING'].get('format', '%(asctime)s [%(levelname)s] %(message)s')))
    handlers.append(console_handler)

# Применяем настройки логирования
logging.basicConfig(
    level=getattr(logging, config['LOGGING'].get('level', 'INFO').upper()),
    handlers=handlers
)

logger = logging.getLogger(__name__)
logger.info("Логирование инициализировано")

# Настройка доверенных прокси и режима работы
mode = config['TRACKER'].get('mode', 'direct')
TRUSTED_PROXIES = config['TRACKER'].get('trusted_proxies', '127.0.0.1').split(',')
logger.info(f"Режим работы: {mode}")
logger.info(f"Доверенные прокси: {TRUSTED_PROXIES}")

def get_real_ip():
    """Получает реальный IP адрес клиента с учетом режима работы"""
    if mode == 'proxy':
        # Логируем заголовки в режиме дебага
        logger.debug("Headers: %s", dict(request.headers))
        logger.debug("Remote addr: %s", request.remote_addr)

        if request.remote_addr in TRUSTED_PROXIES:
            # Пробуем получить IP из заголовков
            if config['TRACKER'].getboolean('use_x_real_ip', True):
                real_ip = request.headers.get('X-Real-IP')
                if real_ip and verify_ip(real_ip):
                    logger.debug(f"Использован X-Real-IP: {real_ip}")
                    return real_ip

            if config['TRACKER'].getboolean('use_x_forwarded_for', True):
                forwarded_for = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                if forwarded_for and verify_ip(forwarded_for):
                    logger.debug(f"Использован X-Forwarded-For: {forwarded_for}")
                    return forwarded_for

            logger.warning(f"Не удалось получить IP из заголовков прокси")
    else:
        logger.debug(f"Прямое подключение от {request.remote_addr}")

    return request.remote_addr

# Инициализация конфигурации трекера
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
if tr_cfg.tr_db_type != 'sqlite':
    raise ValueError('Only SQLite database is supported')

default_cfg = {
    'db_file_path': os.path.join(data_dir, 'tracker.sqlite'),
    'table_name': 'tracker',
    'table_schema': '''CREATE TABLE IF NOT EXISTS tracker (
        info_hash CHAR(20) NOT NULL,
        ip CHAR(8) NOT NULL,
        port INTEGER NOT NULL DEFAULT 0,
        left INTEGER DEFAULT 0,
        update_time INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (info_hash, ip, port)
    )'''
}
db = SQLiteCommon({**default_cfg, **tr_cfg.tr_db})
logger.info(f"База данных SQLite инициализирована: {default_cfg['db_file_path']}")

@app.route('/status')
def status():
    """Эндпоинт для проверки статуса трекера"""
    try:
        # Проверяем подключение к БД
        db.query("SELECT 1")
        # Показываем информацию о клиенте
        client_info = {
            'remote_addr': request.remote_addr,
            'x_real_ip': request.headers.get('X-Real-IP'),
            'x_forwarded_for': request.headers.get('X-Forwarded-For'),
            'determined_ip': get_real_ip()
        }
        return Response(str(client_info), mimetype='text/plain')
    except Exception as e:
        logger.error(f"Ошибка проверки статуса: {e}")
        return Response("ERROR", mimetype='text/plain'), 500

@app.route('/announce')
def announce():
    try:
        # Garbage collector
        if tr_cfg.run_gc_key in request.args:
            logger.info("Запущена сборка мусора")
            announce_interval = max(int(tr_cfg.announce_interval), 60)
            expire_factor = max(float(tr_cfg.peer_expire_factor), 2)
            peer_expire_time = TIMENOW - int(announce_interval * expire_factor)

            result = db.query("DELETE FROM tracker WHERE update_time < ?", (peer_expire_time,))
            logger.info(f"Удалено устаревших записей: {len(result) if result else 0}")
            
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

        # Получение реального IP адреса
        ip = get_real_ip()
        if not verify_ip(ip):
            logger.warning(f"Некорректный IP адрес: {ip}")
            return Response(bencode({'failure reason': 'Invalid IP'}), mimetype='text/plain')

        # Проверка reported_ip если разрешено
        if not tr_cfg.ignore_reported_ip and 'ip' in request.args:
            reported_ip = request.args.get('ip')
            if tr_cfg.verify_reported_ip and verify_ip(reported_ip):
                ip = reported_ip
                logger.debug(f"Использован reported_ip: {ip}")

        # Дополнительные параметры
        event = request.args.get('event', '')
        uploaded = int(request.args.get('uploaded', 0))
        downloaded = int(request.args.get('downloaded', 0))
        left = int(request.args.get('left', 0))
        compact = int(request.args.get('compact', 0))
        no_peer_id = int(request.args.get('no_peer_id', 0))
        numwant = min(int(request.args.get('numwant', tr_cfg.numwant)), 200)

        # Обновляем информацию о пире в БД
        encoded_ip = encode_ip(ip)
        db.query(
            "REPLACE INTO tracker (info_hash, ip, port, left, update_time) VALUES (?, ?, ?, ?, ?)",
            (info_hash, encoded_ip, port, left, TIMENOW)
        )
        logger.debug(f"Сохранен пир: {ip}({encoded_ip}):{port}")

        # Получаем список активных пиров
        peers_query = db.query(
            "SELECT ip, port, left FROM tracker WHERE info_hash = ? AND update_time > ? ORDER BY RANDOM() LIMIT ?",
            (info_hash, TIMENOW - tr_cfg.announce_interval, numwant)
        )

        # Формируем список пиров и считаем статистику
        peers = []
        complete = 0
        incomplete = 0

        for peer in peers_query:
            if peer['left'] == 0:
                complete += 1
            else:
                incomplete += 1

            peers.append({
                'ip': decode_ip(peer['ip']),
                'port': peer['port']
            })

        # Формируем ответ
        output = {
            'interval': tr_cfg.announce_interval,
            'min interval': tr_cfg.announce_interval // 2,
            'complete': complete,
            'incomplete': incomplete,
            'peers': peers
        }

        logger.debug(f"Отправлен ответ для {ip}:{port}, peers: {len(peers)}, complete: {complete}, incomplete: {incomplete}")
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
                stats = db.query(
                    "SELECT COUNT(*) as total, SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as complete FROM tracker WHERE info_hash = ?",
                    (info_hash,)
                )

                if stats:
                    complete = stats[0].get('complete', 0) or 0
                    total = stats[0].get('total', 0) or 0
                    files[info_hash] = {
                        'complete': complete,
                        'downloaded': complete,  # Примерная оценка
                        'incomplete': total - complete
                    }

            except Exception as e:
                logger.error(f"Ошибка обработки info_hash в scrape: {e}")
                continue

        return Response(bencode({'files': files}), mimetype='text/plain')

    except Exception as e:
        logger.error(f"Ошибка обработки scrape запроса: {e}")
        return Response(bencode({'failure reason': str(e)}), mimetype='text/plain')

def check_basic_auth(auth_header):
    """Проверка HTTP Basic Auth"""
    if not auth_header or not auth_header.startswith('Basic '):
        return False
    try:
        auth_decoded = base64.b64decode(auth_header.split(' ', 1)[1]).decode('utf-8')
        # Формат: username:password
        username, password = auth_decoded.split(':', 1)
        # Можно задать username в config.ini, но обычно достаточно только пароля
        expected_password = config['STATS'].get('access_password')
        # username можно не проверять или задать, например, 'admin'
        return password == expected_password
    except Exception:
        return False

@app.route('/stat')
def stats():
    """Эндпоинт для отображения общей статистики сервера с HTTP Basic Auth"""
    auth_header = request.headers.get('Authorization')
    if not check_basic_auth(auth_header):
        return Response(
            'Требуется авторизация',
            401,
            {'WWW-Authenticate': 'Basic realm="Statistics"'}
        )

    try:
        # Получаем общую статистику
        total_stats = db.query("""
            SELECT 
                COUNT(DISTINCT info_hash) as total_torrents,
                COUNT(*) as total_peers,
                SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as total_seeds,
                COUNT(DISTINCT ip) as unique_peers
            FROM tracker 
            WHERE update_time > ?
        """, (TIMENOW - tr_cfg.announce_interval,))

        # Получаем статистику по самым активным торрентам
        top_torrents = db.query("""
            SELECT 
                hex(info_hash) as info_hash,
                COUNT(*) as peer_count,
                SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as seed_count
            FROM tracker 
            WHERE update_time > ?
            GROUP BY info_hash
            ORDER BY peer_count DESC
            LIMIT 10
        """, (TIMENOW - tr_cfg.announce_interval,))

        stats_data = {
            'server_time': datetime.datetime.fromtimestamp(TIMENOW).strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': str(datetime.timedelta(seconds=int(time.time() - app.start_time))),
            'announce_interval': f"{tr_cfg.announce_interval} сек.",
            'stats': total_stats[0] if total_stats else {},
            'top_torrents': [dict(t) for t in (top_torrents if top_torrents else [])],
            'current_year': datetime.datetime.now().year
        }

        return render_template('stats.html', **stats_data)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return Response(
            json.dumps({'error': str(e)}),
            mimetype='application/json'
        ), 500

if __name__ == '__main__':
    # Проверка корректности хоста
    host = config['TRACKER'].get('host', '127.0.0.1')
    port = config['TRACKER'].getint('port', 8080)
    
    def is_valid_ip(ip):
        try:
            # Проверяем является ли строка валидным IP адресом
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    # Проверяем хост
    if host != '0.0.0.0' and not is_valid_ip(host):
        try:
            # Пробуем DNS резолвинг только если это не IP адрес
            socket.gethostbyname(host)
        except socket.gaierror:
            logger.warning(f"Некорректный хост: {host}, использую localhost")
            host = 'localhost'
    
    logger.info(f"Запуск сервера на {host}:{port}")
    app.run(
        host=host,
        port=port,
        debug=config['TRACKER'].getboolean('debug', True),
        use_reloader=config['TRACKER'].getboolean('use_reloader', True)
    )