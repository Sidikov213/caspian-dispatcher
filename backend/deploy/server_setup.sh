#!/usr/bin/env bash
# Настройка VPS и выкатка. Запускается workflow .github/workflows/deploy.yml от root после
# rsync backend → /opt/caspian/backend, website/out → /opt/caspian/website и записи .env.
# Идемпотентно: повторный запуск ничего не ломает.
#   server_setup.sh <домен> <upgrade: 0|1>
set -euo pipefail
# $1 — имена через запятую: основное первым, дальше www и запасной <ip>.sslip.io.
HOSTS="$1"
DOMAIN="${HOSTS%%,*}"            # основное имя: по нему проверка HTTPS
FALLBACK="${HOSTS##*,}"          # запасное (sslip.io): если на основное сертификат не выдан
SITE_ADDR="${HOSTS//,/, }"
UPGRADE="${2:-0}"
APP=/opt/caspian/backend
WEB=/opt/caspian/website
MARK=/opt/caspian/.bootstrapped
export DEBIAN_FRONTEND=noninteractive

step() { echo; echo "::group::$*"; }
done_() { echo "::endgroup::"; }

step "Пакеты"
if [ ! -f "$MARK" ] || [ "$UPGRADE" = "1" ]; then
  apt-get update -q
  apt-get -y -q -o Dpkg::Options::=--force-confold upgrade
fi
apt-get install -y -q python3-venv python3-pip rsync curl ufw caddy >/dev/null
python3 --version; caddy version | head -1
done_

step "Firewall: только 22, 80, 443"
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
ufw status | sed -n '1,12p'
done_

step "Подкачка (если памяти меньше 3 ГБ)"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 3000 ] && ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "добавлен файл подкачки 2 ГБ"
fi
free -m | sed -n '1,3p'
done_

step "Python: venv и зависимости"
cd "$APP"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q --no-cache-dir -r requirements.txt
.venv/bin/python -c "import catboost, fastapi, aiogram; print('catboost', catboost.__version__)"
done_

step "systemd: caspian-backend"
cat > /etc/systemd/system/caspian-backend.service <<UNIT
[Unit]
Description=Caspian dispatcher backend (FastAPI + Telegram bot)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 5
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Restart=always
RestartSec=3
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable caspian-backend >/dev/null 2>&1
systemctl restart caspian-backend
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8000/health && echo
systemctl --no-pager --lines=0 status caspian-backend | sed -n '1,4p'
done_

step "Сайт: $WEB"
if [ ! -f "$WEB/index.html" ]; then
  echo "FAIL: нет $WEB/index.html — сначала соберите website и rsync out/"
  exit 1
fi
echo "файлов: $(find "$WEB" -type f | wc -l), index: $(wc -c < "$WEB/index.html") байт"
done_

# Caddy: / → статика сайта; /api /ws /docs /health и /tg/ (мини-приложение Telegram) → uvicorn.
write_caddyfile() {
  local scheme_host="$1"
  local addr="${2:-$SITE_ADDR}"
  if [ "$scheme_host" = "https" ]; then
    cat > /etc/caddy/Caddyfile <<CADDY
$addr {
	encode gzip

	handle /api* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /ws {
		reverse_proxy 127.0.0.1:8000
	}
	handle /docs* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /redoc* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /openapi.json {
		reverse_proxy 127.0.0.1:8000
	}
	handle /health {
		reverse_proxy 127.0.0.1:8000
	}

	handle /tg* {
		reverse_proxy 127.0.0.1:8000
	}

	handle {
		root * $WEB
		try_files {path} /index.html
		file_server
	}
}
CADDY
  else
    cat > /etc/caddy/Caddyfile <<CADDY
:80 {
	encode gzip

	handle /api* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /ws {
		reverse_proxy 127.0.0.1:8000
	}
	handle /docs* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /redoc* {
		reverse_proxy 127.0.0.1:8000
	}
	handle /openapi.json {
		reverse_proxy 127.0.0.1:8000
	}
	handle /health {
		reverse_proxy 127.0.0.1:8000
	}

	handle /tg* {
		reverse_proxy 127.0.0.1:8000
	}

	handle {
		root * $WEB
		try_files {path} /index.html
		file_server
	}
}
CADDY
  fi
}

step "Caddy: https://$SITE_ADDR → сайт + /api + /ws"
write_caddyfile https
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy || systemctl restart caddy
OK_HTTPS=0
for i in $(seq 1 60); do
  if curl -sf --max-time 5 "https://$DOMAIN/health" >/dev/null; then OK_HTTPS=1; break; fi
  sleep 5
done
if [ "$OK_HTTPS" = 1 ]; then
  echo "HTTPS_OK https://$DOMAIN"
  for h in ${HOSTS//,/ }; do
    curl -sf --max-time 10 "https://$h/health" >/dev/null && echo "HTTPS_HOST_OK https://$h" || echo "HTTPS_HOST_FAIL https://$h"
  done
else
  echo "HTTPS_FAILED: на $DOMAIN сертификат не выдан за 5 минут"
  journalctl -u caddy -n 30 --no-pager | grep -iE "error|acme|certificate" | tail -8 || true
  if [ "$FALLBACK" != "$DOMAIN" ]; then
    echo "возвращаю запасной адрес https://$FALLBACK"
    write_caddyfile https "$FALLBACK"
    systemctl reload caddy || systemctl restart caddy
    for i in $(seq 1 24); do curl -sf --max-time 5 "https://$FALLBACK/health" >/dev/null && { echo "HTTPS_FALLBACK_OK https://$FALLBACK"; OK_HTTPS=1; break; }; sleep 5; done
  fi
  if [ "$OK_HTTPS" != 1 ]; then
    echo "оставляем HTTP на 80 порту"
    write_caddyfile http
    systemctl reload caddy || systemctl restart caddy
  fi
fi
done_

touch "$MARK"
