#!/usr/bin/env bash
# NGULIK BASS STUDIO — installer for a Hostinger VPS that already runs n8n + Traefik.
# Safe by design: only creates/updates the "ngulik-bass-studio" compose project.
# Usage (from the project folder):  bash deploy/hostinger-install.sh [domain]
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*"; exit 1; }

command -v docker >/dev/null || die "Docker tidak ditemukan."
docker compose version >/dev/null || die "docker compose tidak ditemukan."

say "Mendeteksi Traefik yang sudah ada"
TRAEFIK=$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /traefik/ {print $1; exit}')
[ -n "$TRAEFIK" ] || die "Container Traefik tidak ditemukan. Hentikan instalasi agar n8n tidak terganggu."
ARGS=$(docker inspect "$TRAEFIK" --format '{{range .Args}}{{println .}}{{end}}{{range .Config.Cmd}}{{println .}}{{end}}')
RESOLVER=$(printf '%s\n' "$ARGS" | sed -n 's/.*--certificatesresolvers\.\([^.]*\)\..*/\1/p' | head -1)
ENTRY=$(printf '%s\n' "$ARGS" | sed -n 's/.*--entrypoints\.\([^.]*\)\.address=:443.*/\1/p' | head -1)
NET=$(docker inspect "$TRAEFIK" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | awk '{print $1}')
[ -n "$RESOLVER" ] || die "Nama certresolver Traefik tidak terdeteksi. Kirim output: docker inspect $TRAEFIK --format '{{json .Args}}'"
ENTRY=${ENTRY:-websecure}
echo "Traefik: $TRAEFIK | network: $NET | entrypoint: $ENTRY | certresolver: $RESOLVER"

PUBIP=$(curl -4 -fsS --max-time 8 https://api.ipify.org || hostname -I | awk '{print $1}')
DOMAIN_ARG=${1:-}

if [ ! -f .env ]; then
  say "Membuat .env (password & secret acak)"
  DOMAIN=${DOMAIN_ARG:-"ngulikbass.${PUBIP//./-}.sslip.io"}
  umask 077
  cat > .env <<EOF
DOMAIN=$DOMAIN
POSTGRES_DB=ngulik
POSTGRES_USER=ngulik
POSTGRES_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 32)
ALLOW_REGISTRATION=true
MAX_UPLOAD_MB=50
MAX_DURATION_SEC=900
RATE_LIMIT_AUTH=10/minute
RATE_LIMIT_UPLOAD=20/hour
TRAEFIK_NETWORK=$NET
TRAEFIK_ENTRYPOINT=$ENTRY
TRAEFIK_CERTRESOLVER=$RESOLVER
EOF
elif [ -n "$DOMAIN_ARG" ]; then
  sed -i "s/^DOMAIN=.*/DOMAIN=$DOMAIN_ARG/" .env
fi
# shellcheck disable=SC1091
DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2)

say "Cek DNS $DOMAIN -> $PUBIP"
RESOLVED=$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)
if [ "$RESOLVED" != "$PUBIP" ]; then
  echo "PERINGATAN: $DOMAIN mengarah ke '${RESOLVED:-tidak ada}', bukan $PUBIP."
  echo "HTTPS baru aktif setelah A record domain diarahkan ke $PUBIP."
fi

say "Build & start (pertama kali ~5-10 menit)"
docker compose -f docker-compose.hostinger.yml --env-file .env up -d --build

say "Menunggu backend sehat"
for i in $(seq 1 40); do
  if docker compose -f docker-compose.hostinger.yml exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)" >/dev/null 2>&1; then
    echo "backend OK"; break
  fi
  sleep 3
  [ "$i" = 40 ] && die "Backend belum sehat. Lihat: docker compose -f docker-compose.hostinger.yml logs backend"
done

say "Status container"
docker compose -f docker-compose.hostinger.yml ps
echo
echo "n8n tetap berjalan:"; docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'n8n|traefik' || true

say "Selesai. Buka: https://$DOMAIN  (sertifikat HTTPS bisa butuh 1-2 menit pertama)"
echo "Cek dari VPS:  curl -sk https://$DOMAIN/api/health"
