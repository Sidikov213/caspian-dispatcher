#!/usr/bin/env bash
# Настройка VPS и выкатка бэкенда. Запускается workflow .github/workflows/deploy.yml от root после
# rsync кода в /opt/caspian/backend и записи .env. Идемпотентно: повторный запуск ничего не ломает.
#   server_setup.sh <домен> <upgrade: 0|1>
set -euo pipefail
DOMAIN="$1"
UPGRADE="${2:-0}"
APP=/opt/caspian/backend
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

step "Caddy: https://$DOMAIN → 127.0.0.1:8000"
https_caddyfile() {
  cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
CADDY
}
http_caddyfile() {
  cat > /etc/caddy/Caddyfile <<CADDY
:80 {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
CADDY
}
# Если раньше пришлось откатиться на HTTP, при каждой выкатке пробуем HTTPS снова.
https_caddyfile
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy || systemctl restart caddy
OK_HTTPS=0
for i in $(seq 1 60); do   # до 5 минут на сертификат
  if curl -sf --max-time 5 "https://$DOMAIN/health" >/dev/null; then OK_HTTPS=1; break; fi
  sleep 5
done
if [ "$OK_HTTPS" = 1 ]; then
  echo "HTTPS_OK https://$DOMAIN"
else
  echo "HTTPS_FAILED: сертификат не выдан за 5 минут — оставляем HTTP на 80 порту"
  journalctl -u caddy -n 20 --no-pager | grep -iE "error|acme|certificate" | tail -8 || true
  http_caddyfile
  systemctl reload caddy || systemctl restart caddy
fi
done_

touch "$MARK"
