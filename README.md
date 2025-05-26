# retracker

retracker - is a lightweight BitTorrent tracker built with Flask, storing configuration, database, and templates in separate folders.  
It works both in interactive mode (console) and as a systemd service.

---

## Features

- BitTorrent tracker with announce/scrape support
- Web statistics interface with authentication (Flask sessions)
- Flexible configuration via config.ini
- Log rotation support
- Universal launch: console or systemd
- Supports **proxy** and **direct** operation modes

---

## Use Cases

- For local networks (e.g., ISP or within an organization)
- For private torrent communities
- For testing and developing BitTorrent clients
- When you need a simple and transparent tracker without extra features

`retracker does not require user registration, does not store files, but only coordinates peers for data exchange via the BitTorrent protocol.`

---

## Quick Start

### 1. Clone the repository

```
git clone https://github.com/Makar-aka/retracker.git cd retracker
```

### 2. Configure

Copy the example config and edit it as needed:

cp config/config_example.ini config/config.ini


**Required parameters:**
- `[FLASK]` — secret key for session authorization in statistics
- `[STATS]` — login and password for statistics access
- `[TRACKER]` — port, host, announce interval, and other options

---

## Operation Modes: proxy and direct

The tracker can work in two modes, set by the `mode` parameter in the `[TRACKER]` section of `config.ini`:

- `direct` — direct connection, the client's IP address is taken from the standard connection (default).
- `proxy` — used if the tracker is behind a reverse proxy (e.g., nginx, haproxy). In this mode, the tracker determines the real client IP from the `X-Real-IP` and/or `X-Forwarded-For` headers.

If the tracker is behind a reverse proxy, all incoming connections will appear to come from the proxy's IP address. In this case, it's impossible to determine the real user's IP in the standard way.  
The `proxy` mode allows you to get the real client IP from special HTTP headers added by the proxy server. This is important for correct tracker operation, peer accounting, and abuse prevention.

Use `proxy` mode if:
- You run the tracker behind nginx, haproxy, cloudflare, or another reverse proxy.
- You need to see real user IP addresses, not the proxy's address.

- For `proxy` mode to work correctly, your proxy server must forward the real client IP in headers.  
See your proxy server's documentation for setup details.

Use `direct` mode if:
- The tracker is accessible directly, without a proxy server.
- You want to get client IP addresses directly from the connection.

---

## Configuration

All settings are in `config/config.ini`.  
Example sections:
```ini
[FLASK] 
secret_key = your_random_session_secret_key
[LOGGING]
log_file = tracker.log 
level = INFO 
format = %(asctime)s [%(levelname)s] %(message)s 
console_output = True 
max_bytes = 5242880 
backup_count = 5 
clear_on_start = False

[TRACKER] 
host = 0.0.0.0 
port = 8080 
announce_interval = 1800 
peer_expire_factor = 2 
ignore_reported_ip = False 
verify_reported_ip = True 
allow_internal_ip = False 
numwant = 50 
run_gc_key = gc

[CACHE] 
type = sqlite

[DB] 
type = sqlite

[STATS] 
access_username = admin 
access_password = password
```

---

## Local Launch (console)

1. Install dependencies:
```sh
pip install -r requirements.txt
```
2. Start the server:
```sh
python3 main.py
```


---

## Running as a systemd Service

1. Copy and edit `retracker.service_example`:
    - Specify absolute paths to the working directory and main.py
    - Set the user and group

2. Copy the file to `/etc/systemd/system/retracker.service` and run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now retracker
```

---

## Accessing Statistics

- Open `http://your_server/stat` in your browser.
- Enter the login and password from the `[STATS]` section of config.ini.

---

## Update

```
git pull 

systemctl restart retracker

```

---

## License

MIT

---

Author: [MakarSPB](https://github.com/Makar-aka)