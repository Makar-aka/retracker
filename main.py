from flask import Flask, request, Response, render_template, redirect, url_for, session, flash
from tracker import *
from db_handlers import SQLiteCommon
from logging.handlers import RotatingFileHandler
import logging
import os
import urllib.parse
import socket
import time
import json
import datetime
from functools import wraps
import traceback
import threading
import ipaddress
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

def get_path(docker_path, local_path):
    return docker_path if os.path.exists(docker_path) else local_path

DATA_DIR = get_path('/data', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
TEMPLATES_DIR = get_path('/templates', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))

# --- Получение настроек из переменных окружения с дефолтами ---
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'your-very-secret-key')

CACHE_TYPE = os.getenv('CACHE_TYPE', 'sqlite')
CACHE_DB_FILE_PATH = os.getenv('CACHE_DB_FILE_PATH', os.path.join(DATA_DIR, 'cache.sqlite'))

DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DB_FILE_PATH = os.getenv('DB_FILE_PATH', os.path.join(DATA_DIR, 'tracker.sqlite'))
DB_TABLE_NAME = os.getenv('DB_TABLE_NAME', 'tracker')
DB_TABLE_SCHEMA = os.getenv('DB_TABLE_SCHEMA', '''
    CREATE TABLE IF NOT EXISTS tracker (
        info_hash CHAR(20) NOT NULL,
        ip CHAR(8) NOT NULL,
        port INTEGER NOT NULL DEFAULT 0,
        left INTEGER DEFAULT 0,
        update_time INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (info_hash, ip, port)
    );
    CREATE TABLE IF NOT EXISTS blocklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        info_hash TEXT,
        reason TEXT,
        created_at INTEGER
    );
''')

TRACKER_MODE = os.getenv('TRACKER_MODE')
TRACKER_TRUSTED_PROXIES = os.getenv('TRACKER_TRUSTED_PROXIES', '127.0.0.1').split(',')
TRACKER_USE_X_REAL_IP = os.getenv('TRACKER_USE_X_REAL_IP', 'true').lower() == 'true'
TRACKER_USE_X_FORWARDED_FOR = os.getenv('TRACKER_USE_X_FORWARDED_FOR', 'true').lower() == 'true'
TRACKER_HOST = os.getenv('TRACKER_HOST')
TRACKER_PORT = int(os.getenv('TRACKER_PORT', 8088))
TRACKER_ANNOUNCE_INTERVAL = int(os.getenv('TRACKER_ANNOUNCE_INTERVAL', 1800))
TRACKER_PEER_EXPIRE_FACTOR = float(os.getenv('TRACKER_PEER_EXPIRE_FACTOR', 2.5))
TRACKER_IGNORE_IP = os.getenv('TRACKER_IGNORE_IP', '192.168.0.0/16 172.16.0.0/12 127.0.0.1')
TRACKER_NUMWANT = int(os.getenv('TRACKER_NUMWANT', 50))
TRACKER_RUN_GC_KEY = os.getenv('TRACKER_RUN_GC_KEY', 'gc')
TRACKER_PEER_CLEANUP_PERIOD = int(os.getenv('TRACKER_PEER_CLEANUP_PERIOD', 600))
TRACKER_DEBUG = os.getenv('TRACKER_DEBUG', 'true').lower() == 'true'
TRACKER_USE_RELOADER = os.getenv('TRACKER_USE_RELOADER', 'true').lower() == 'true'

LOGGING_LEVEL = os.getenv('LOGGING_LEVEL', 'INFO')
LOGGING_LOG_FILE = os.getenv('LOGGING_LOG_FILE', os.path.join(DATA_DIR, 'tracker.log'))
LOGGING_MAX_BYTES = int(os.getenv('LOGGING_MAX_BYTES', 5242880))
LOGGING_BACKUP_COUNT = int(os.getenv('LOGGING_BACKUP_COUNT', 5))
LOGGING_FORMAT = os.getenv('LOGGING_FORMAT', '%(asctime)s [%(levelname)s] %(message)s')
LOGGING_CONSOLE_OUTPUT = os.getenv('LOGGING_CONSOLE_OUTPUT', 'true').lower() == 'true'
LOGGING_CLEAR_ON_START = os.getenv('LOGGING_CLEAR_ON_START', 'false').lower() == 'true'

STATS_ACCESS_USERNAME = os.getenv('STATS_ACCESS_USERNAME', 'admin')
STATS_ACCESS_PASSWORD = os.getenv('STATS_ACCESS_PASSWORD', 'admin')

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = SECRET_KEY
app.start_time = time.time()

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

log_file = LOGGING_LOG_FILE
log_dir = os.path.dirname(log_file)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

if LOGGING_CLEAR_ON_START and os.path.exists(log_file):
    try:
        os.remove(log_file)
        for i in range(LOGGING_BACKUP_COUNT):
            backup = f"{log_file}.{i+1}"
            if os.path.exists(backup):
                os.remove(backup)
    except Exception as e:
        print(f"Ошибка при очистке старых логов: {e}")

handlers = []
file_handler = RotatingFileHandler(
    filename=log_file,
    maxBytes=LOGGING_MAX_BYTES,
    backupCount=LOGGING_BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
handlers.append(file_handler)

if LOGGING_CONSOLE_OUTPUT:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
    handlers.append(console_handler)

logging.basicConfig(
    level=getattr(logging, LOGGING_LEVEL.upper()),
    handlers=handlers
)

logger = logging.getLogger(__name__)
logger.info("Логирование инициализировано")

mode = TRACKER_MODE
TRUSTED_PROXIES = [ip.strip() for ip in TRACKER_TRUSTED_PROXIES]
logger.info(f"Режим работы: {mode}")
logger.info(f"Доверенные прокси: {TRUSTED_PROXIES}")

def get_real_ip():
    if mode == 'proxy':
        logger.debug("Headers: %s", dict(request.headers))
        logger.debug("Remote addr: %s", request.remote_addr)
        if request.remote_addr in TRUSTED_PROXIES:
            if TRACKER_USE_X_REAL_IP:
                real_ip = request.headers.get('X-Real-IP')
                if real_ip and verify_ip(real_ip):
                    logger.debug(f"Использован X-Real-IP: {real_ip}")
                    return real_ip
            if TRACKER_USE_X_FORWARDED_FOR:
                forwarded_for = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                if forwarded_for and verify_ip(forwarded_for):
                    logger.debug(f"Использован X-Forwarded-For: {forwarded_for}")
                    return forwarded_for
            logger.warning(f"Не удалось получить IP из заголовков прокси")
    else:
        logger.debug(f"Прямое подключение от {request.remote_addr}")
    return request.remote_addr

def parse_ignore_ip(cfg_value):
    result = []
    for part in cfg_value.split():
        try:
            if '/' in part:
                result.append(ipaddress.ip_network(part, strict=False))
            else:
                result.append(ipaddress.ip_address(part))
        except Exception:
            pass
    return result

IGNORE_IP_LIST = parse_ignore_ip(TRACKER_IGNORE_IP)

def is_ignored_ip(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        for net in IGNORE_IP_LIST:
            if isinstance(net, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                if ip_obj in net:
                    return True
            elif ip_obj == net:
                return True
        return False
    except Exception:
        return False

tr_cfg = Config(
    tr_cache_type=CACHE_TYPE,
    tr_db_type=DB_TYPE,
    tr_cache={'db_file_path': CACHE_DB_FILE_PATH},
    tr_db={'db_file_path': DB_FILE_PATH, 'table_name': DB_TABLE_NAME, 'table_schema': DB_TABLE_SCHEMA},
    announce_interval=TRACKER_ANNOUNCE_INTERVAL,
    peer_expire_factor=TRACKER_PEER_EXPIRE_FACTOR,
    numwant=TRACKER_NUMWANT,
    run_gc_key=TRACKER_RUN_GC_KEY
)

logger.info(f"Инициализация кэша типа: {tr_cfg.tr_cache_type}")
if tr_cfg.tr_cache_type == 'sqlite':
    tr_cache = CacheSQLite(tr_cfg.tr_cache)
else:
    tr_cache = CacheCommon()

logger.info(f"Инициализация БД типа: {tr_cfg.tr_db_type}")
if tr_cfg.tr_db_type != 'sqlite':
    raise ValueError('Only SQLite database is supported')

default_cfg = {
    'db_file_path': DB_FILE_PATH,
    'table_name': DB_TABLE_NAME,
    'table_schema': DB_TABLE_SCHEMA
}
db = SQLiteCommon({**default_cfg, **tr_cfg.tr_db})
logger.info(f"База данных SQLite инициализирована: {DB_FILE_PATH}")

def cleanup_dead_peers():
    while True:
        try:
            now = int(time.time())
            announce_interval = max(int(tr_cfg.announce_interval), 60)
            expire_factor = max(float(tr_cfg.peer_expire_factor), 2)
            peer_expire_time = now - int(announce_interval * expire_factor)
            db.query("DELETE FROM tracker WHERE update_time < ?", (peer_expire_time,))
            logger.info("Автоматическая очистка мертвых пиров выполнена")
        except Exception as e:
            logger.error(f"Ошибка автоматической очистки пиров: {e}")
        time.sleep(TRACKER_PEER_CLEANUP_PERIOD)

def is_blocked(ip, info_hash):
    res = db.query(
        "SELECT 1 FROM blocklist WHERE (ip = ? AND ip != '') OR (info_hash = ? AND info_hash != '') LIMIT 1",
        (ip, info_hash)
    )
    return bool(res)

@app.route('/status')
def status():
    try:
        db.query("SELECT 1")
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
        now = int(time.time())
        if tr_cfg.run_gc_key in request.args:
            logger.info("Запущена сборка мусора")
            announce_interval = max(int(tr_cfg.announce_interval), 60)
            expire_factor = max(float(tr_cfg.peer_expire_factor), 2)
            peer_expire_time = now - int(announce_interval * expire_factor)
            result = db.query("DELETE FROM tracker WHERE update_time < ?", (peer_expire_time,))
            logger.info(f"Удалено устаревших записей: {len(result) if result else 0}")
            if hasattr(tr_cache, 'gc'):
                tr_cache.gc()
            return Response("OK", mimetype='text/plain')

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

        ip = get_real_ip()
        if is_ignored_ip(ip):
            logger.warning(f"IP {ip} из ignore_ip — игнорируется")
            return Response(bencode({'failure reason': 'IP запрещён'}), mimetype='text/plain')

        info_hash_hex = info_hash.hex() if isinstance(info_hash, bytes) else info_hash
        if is_blocked(ip, info_hash_hex):
            logger.warning(f"Блокировка: {ip} или {info_hash_hex}")
            return Response(bencode({'failure reason': 'IP или торрент заблокирован'}), mimetype='text/plain')

        event = request.args.get('event', '')
        uploaded = int(request.args.get('uploaded', 0))
        downloaded = int(request.args.get('downloaded', 0))
        left = int(request.args.get('left', 0))
        compact = int(request.args.get('compact', 0))
        no_peer_id = int(request.args.get('no_peer_id', 0))
        numwant = min(int(request.args.get('numwant', tr_cfg.numwant)), 200)

        encoded_ip = encode_ip(ip)
        db.query(
            "REPLACE INTO tracker (info_hash, ip, port, left, update_time) VALUES (?, ?, ?, ?, ?)",
            (info_hash, encoded_ip, port, left, now)
        )
        logger.debug(f"Сохранен пир: {ip}({encoded_ip}):{port}")

        peers_query = db.query(
            "SELECT ip, port, left FROM tracker WHERE info_hash = ? AND update_time > ? ORDER BY RANDOM() LIMIT ?",
            (info_hash, now - tr_cfg.announce_interval, numwant)
        )

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
        logger.error(f"Ошибка обработки announce запроса: {e}\n{traceback.format_exc()}")
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
                stats = db.query(
                    "SELECT COUNT(*) as total, SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as complete FROM tracker WHERE info_hash = ?",
                    (info_hash,)
                )
                if stats:
                    complete = stats[0].get('complete', 0) or 0
                    total = stats[0].get('total', 0) or 0
                    files[info_hash] = {
                        'complete': complete,
                        'downloaded': complete,
                        'incomplete': total - complete
                    }
            except Exception as e:
                logger.error(f"Ошибка обработки info_hash в scrape: {e}\n{traceback.format_exc()}")
                continue

        return Response(bencode({'files': files}), mimetype='text/plain')

    except Exception as e:
        logger.error(f"Ошибка обработки scrape запроса: {e}\n{traceback.format_exc()}")
        return Response(bencode({'failure reason': str(e)}), mimetype='text/plain')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == STATS_ACCESS_USERNAME and password == STATS_ACCESS_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('stats'))
        else:
            error = 'Неверный логин или пароль'
    return render_template('login.html', error=error, current_year=datetime.datetime.now().year)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.')
    return redirect(url_for('login'))

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/stat')
@login_required
def stats():
    try:
        now = int(time.time())
        total_stats = db.query("""
            SELECT 
                COUNT(DISTINCT info_hash) as total_torrents,
                COUNT(*) as total_peers,
                SUM(CASE WHEN left = 0 THEN 1 ELSE 0 END) as total_seeds,
                COUNT(DISTINCT ip) as unique_peers
            FROM tracker 
            WHERE update_time > ?
        """, (now - tr_cfg.announce_interval,))

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
        """, (now - tr_cfg.announce_interval,))

        db_file_path = db.cfg['db_file_path']
        db_size = os.path.getsize(db_file_path) if os.path.exists(db_file_path) else 0

        total_records = db.query("SELECT COUNT(*) as cnt FROM tracker")
        record_count = total_records[0]['cnt'] if total_records else 0

        active_peers = db.query("""
            SELECT info_hash, ip, port, update_time
            FROM tracker
            WHERE update_time > ?
            ORDER BY update_time DESC
            LIMIT 20
        """, (now - tr_cfg.announce_interval,))

        for peer in active_peers:
            peer['ip'] = decode_ip(peer['ip'])
            peer['info_hash'] = peer['info_hash'].hex() if isinstance(peer['info_hash'], bytes) else peer['info_hash']
            peer['update_time'] = datetime.datetime.fromtimestamp(peer['update_time']).strftime('%Y-%m-%d %H:%M:%S')

        stats_data = {
            'server_time': datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S'),
            'uptime': str(datetime.timedelta(seconds=int(time.time() - app.start_time))),
            'announce_interval': f"{tr_cfg.announce_interval} сек.",
            'stats': total_stats[0] if total_stats else {},
            'top_torrents': [dict(t) for t in (top_torrents if top_torrents else [])],
            'db_size': db_size,
            'record_count': record_count,
            'active_peers': active_peers,
            'current_year': datetime.datetime.now().year
        }

        return render_template('stats.html', **stats_data)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}\n{traceback.format_exc()}")
        return Response(
            json.dumps({'error': str(e)}),
            mimetype='application/json'
        ), 500

@app.route('/all_peers')
@login_required
def all_peers():
    try:
        page = int(request.args.get('page', 1))
        per_page = 20
        offset = (page - 1) * per_page

        sort_by = request.args.get('sort_by', 'ip')
        sort = request.args.get('sort', 'desc')
        allowed_sort_by = {
            'ip': 'ip',
            'port': 'port',
            'info_hash': 'info_hash',
            'update_time': 'update_time'
        }
        sort_by_sql = allowed_sort_by.get(sort_by, 'ip')
        sort_sql = 'ASC' if sort == 'asc' else 'DESC'

        total_peers = db.query("SELECT COUNT(*) as cnt FROM tracker")
        total_count = total_peers[0]['cnt'] if total_peers else 0
        total_pages = (total_count + per_page - 1) // per_page

        peers = db.query(f"""
            SELECT info_hash, ip, port, update_time
            FROM tracker
            ORDER BY {sort_by_sql} {sort_sql}
            LIMIT ? OFFSET ?
        """, (per_page, offset))

        for peer in peers:
            peer['ip'] = decode_ip(peer['ip'])
            peer['info_hash'] = peer['info_hash'].hex() if isinstance(peer['info_hash'], bytes) else peer['info_hash']
            peer['update_time'] = datetime.datetime.fromtimestamp(peer['update_time']).strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            'all_peers.html',
            peers=peers,
            page=page,
            total_pages=total_pages,
            sort=sort,
            sort_by=sort_by
        )
    except Exception as e:
        logger.error(f"Ошибка при получении списка всех пиров: {e}\n{traceback.format_exc()}")
        return Response("Ошибка при получении списка пиров", mimetype='text/plain'), 500

@app.route('/blocklist', methods=['GET', 'POST'])
@login_required
def blocklist():
    message = None
    if request.method == 'POST':
        ip = request.form.get('ip', '').strip()
        info_hash = request.form.get('info_hash', '').strip()
        reason = request.form.get('reason', '').strip()
        if ip or info_hash:
            db.query(
                "INSERT INTO blocklist (ip, info_hash, reason, created_at) VALUES (?, ?, ?, ?)",
                (ip if ip else None, info_hash if info_hash else None, reason, int(time.time()))
            )
            message = "Добавлено в блоклист"
    blocks = db.query("SELECT * FROM blocklist ORDER BY created_at DESC")
    return render_template('blocklist.html', blocks=blocks, message=message)

@app.route('/blocklist/unblock/<int:block_id>', methods=['POST'])
@login_required
def unblock_blocklist(block_id):
    db.query("DELETE FROM blocklist WHERE id = ?", (block_id,))
    flash("Запись разблокирована", "success")
    return redirect(url_for('blocklist'))

@app.template_filter('datetime')
def _jinja2_filter_datetime(ts):
    if not ts:
        return ''
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts)

if __name__ == '__main__':
    threading.Thread(target=cleanup_dead_peers, daemon=True).start()

    def is_valid_ip(ip):
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except (AttributeError, TypeError, ValueError):
            return False

    host = TRACKER_HOST
    port = TRACKER_PORT

    if host != '0.0.0.0' and not is_valid_ip(host):
        try:
            socket.gethostbyname(host)
        except socket.gaierror:
            logger.warning(f"Некорректный хост: {host}, использую localhost")
            host = 'localhost'

    logger.info(f"Запуск сервера на {host}:{port}")
    app.run(
        host=host,
        port=port,
        debug=TRACKER_DEBUG,
        use_reloader=TRACKER_USE_RELOADER
    )