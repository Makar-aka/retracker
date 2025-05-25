# retracker

**retracker** — это легковесный BitTorrent-трекер на Flask с хранением конфигурации, базы данных и шаблонов в отдельных папках.  
Работает как в интерактивном режиме (консоль), так и как systemd-сервис.

---

## Возможности

- BitTorrent-трекер с поддержкой announce/scrape
- Веб-интерфейс статистики с авторизацией (Flask-сессии)
- Гибкая настройка через config.ini
- Логирование с ротацией
- Универсальный запуск: консоль, systemd
- Поддержка работы в режимах **proxy** и **direct**
---

## Быстрый старт

### 1. Клонирование репозитория
```
git clone https://github.com/Makar-aka/retracker.git cd retracker
```
### 2. Настройка конфигурации

Скопируйте пример конфига и отредактируйте под себя:

cp config/config_example.ini config/config.ini


**Обязательные параметры:**
- `[FLASK]` — секретный ключ для сессий авторизации в статистике
- `[STATS]` — логин и пароль для входа в статистику
- `[TRACKER]` — порт, host, интервал анонса и др.

---

## Режимы работы: proxy и direct

Трекер может работать в двух режимах, которые задаются параметром `mode` в секции `[TRACKER]` файла `config.ini`:

- **direct** — прямое подключение, IP-адрес клиента берётся из стандартного соединения (по умолчанию).
- **proxy** — используется, если трекер работает за обратным прокси (например, nginx, haproxy). В этом режиме трекер определяет реальный IP клиента по заголовкам `X-Real-IP` и/или `X-Forwarded-For`.

Если трекер работает за обратным прокси-сервером, то все входящие подключения для приложения будут приходить с одного и того же IP-адреса (адреса прокси). В этом случае невозможно определить реальный IP-адрес пользователя стандартным способом.  
Режим `proxy` позволяет получать настоящий IP-адрес клиента из специальных HTTP-заголовков, которые прокси-сервер добавляет к каждому запросу. Это важно для корректной работы трекера, учёта пиров и предотвращения злоупотреблений.

**Используйте режим `proxy`, если:**
- Вы запускаете трекер за nginx, haproxy, cloudflare или другим обратным прокси.
- Вам нужно видеть реальные IP-адреса пользователей, а не адрес прокси.

**Используйте режим `direct`, если:**
- Трекер доступен напрямую, без прокси-сервера.
- Вы хотите получать IP-адреса клиентов напрямую из соединения.
 
Пример настройки:
## Локальный запуск (консоль)

1. Установите зависимости:
```sh
pip install -r requirements.txt
```
2. Запустите сервер:
```sh
python3 main.py
```
3. Откройте http://localhost:8080/stat (или порт, указанный в config.ini)

---

## Запуск как systemd-сервис

1. Скопируйте и отредактируйте `retracker.service_example`:
    - Укажите абсолютные пути к рабочей директории и main.py
    - Укажите пользователя и группу

2. Скопируйте файл в `/etc/systemd/system/retracker.service` и выполните:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now retracker
```

---

## Конфигурация

Все настройки — в `config/config.ini`.  
Пример секций:
```ini
[FLASK] secret_key = your-very-secret-key
[LOGGING] log_file = tracker.log level = INFO format = %(asctime)s [%(levelname)s] %(message)s console_output = True max_bytes = 5242880 backup_count = 5 clear_on_start = False
[TRACKER] host = 0.0.0.0 port = 8080 announce_interval = 1800 peer_expire_factor = 2 ignore_reported_ip = False verify_reported_ip = True allow_internal_ip = False numwant = 50 run_gc_key = gc
[CACHE] type = sqlite
[DB] type = sqlite
[STATS] access_username = admin access_password = password
```

---

## Вход в статистику

- Откройте `http://ваш_сервер/stat` в браузере.
- Введите логин и пароль из секции `[STATS]` файла config.ini.

---

## Обновление

```
git pull 

systemctl restart retracker

```

---

## Лицензия

MIT

---

**Автор:** [MakarSPB](https://github.com/Makar-aka)