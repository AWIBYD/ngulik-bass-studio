# Deployment ke VPS — NGULIK BASS STUDIO (Phase 1)

Target: VPS Ubuntu 22.04/24.04, CPU-only, domain sendiri, HTTPS otomatis via Caddy.

## 0. Kebutuhan resource
| | Minimum | Disarankan |
|---|---|---|
| Phase 1 (upload, editor, player) | 1 vCPU, 1 GB RAM, 10 GB disk | 2 vCPU, 2 GB RAM |
| Phase 2 (Demucs, CPU) | 2 vCPU, **4 GB RAM** | 4 vCPU, 8 GB RAM |

Tanpa GPU, pemisahan bass Demucs di CPU butuh kira-kira 1–3× durasi lagu (lagu 4 menit ≈ 4–12 menit) dan RAM 3–4 GB per job. Phase 2 akan menjalankan 1 job sekaligus di worker terpisah agar web tetap responsif. Angka pasti akan diukur di VPS kamu saat Phase 2.

Disk: setiap lagu disimpan 2× (asli + versi playback AAC ~1,4 MB/menit). Lagu 5 menit MP3 ≈ 5 MB + 7 MB.

## 1. Persiapan VPS
```bash
ssh root@IP_VPS
adduser deploy && usermod -aG sudo deploy
apt update && apt -y upgrade
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable
# swap 2 GB (penting untuk VPS RAM kecil)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. Instal Docker
```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy      # logout-login setelah ini
docker --version && docker compose version
```

## 3. Upload source code
Pilih salah satu:
```bash
# a) git
git clone <repo-kamu> /opt/ngulik-bass-studio
# b) dari komputer lokal
scp ngulik-bass-studio.zip deploy@IP_VPS:/opt/ && ssh deploy@IP_VPS 'cd /opt && unzip ngulik-bass-studio.zip'
```

## 4. Konfigurasi environment
```bash
cd /opt/ngulik-bass-studio
cp .env.example .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
nano .env        # isi DOMAIN, ACME_EMAIL; atur MAX_UPLOAD_MB, MAX_DURATION_SEC
chmod 600 .env
```
Setelah akun kamu dibuat, set `ALLOW_REGISTRATION=false` jika aplikasi hanya untuk dipakai sendiri, lalu `docker compose up -d backend`.

## 5. Menjalankan container
```bash
docker compose build
docker compose up -d
docker compose ps          # semua harus "healthy"/"running"
```

## 6. Konfigurasi domain
Di DNS provider, buat record **A** `bass.domainkamu.com` → IP VPS (dan AAAA jika ada IPv6). Cek: `dig +short bass.domainkamu.com`. Nilai yang sama harus ada di `DOMAIN` pada `.env`.

## 7. SSL / HTTPS
Otomatis. Caddy mengambil sertifikat Let's Encrypt saat pertama kali domain diakses dan memperbaruinya sendiri. Syarat: port 80 & 443 terbuka dan DNS sudah mengarah ke VPS. Cek: `docker compose logs caddy | grep -i certificate`.

Cookie sesi memakai `Secure` + `HttpOnly` + `SameSite=Lax`, jadi login hanya berjalan lewat HTTPS.

## 8. Pemeriksaan log
```bash
docker compose logs -f --tail=100 backend
docker compose logs -f caddy
docker compose logs frontend db
curl -s https://bass.domainkamu.com/api/health    # {"status":"ok"}
```

## 9. Backup
```bash
mkdir -p /opt/backups
# database
docker compose exec -T db pg_dump -U ngulik ngulik | gzip > /opt/backups/db-$(date +%F).sql.gz
# file audio
docker run --rm -v ngulik-bass-studio_storage:/s -v /opt/backups:/b alpine tar czf /b/storage-$(date +%F).tgz -C /s .
```
Cron harian (`crontab -e`):
```
30 3 * * * cd /opt/ngulik-bass-studio && docker compose exec -T db pg_dump -U ngulik ngulik | gzip > /opt/backups/db-$(date +\%F).sql.gz && find /opt/backups -mtime +14 -delete
```
Restore DB: `gunzip -c db-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U ngulik ngulik`. Simpan salinan backup di luar VPS.

## 10. Update aplikasi
```bash
cd /opt/ngulik-bass-studio
docker compose exec -T db pg_dump -U ngulik ngulik | gzip > /opt/backups/pre-update-$(date +%F-%H%M).sql.gz   # backup dulu
git pull                     # atau upload source baru
docker compose build
docker compose up -d
docker compose ps && curl -s https://bass.domainkamu.com/api/health
```
Rollback: checkout versi sebelumnya, `docker compose build && docker compose up -d`, restore DB jika perlu.

## Catatan
- Phase 1 membuat tabel otomatis saat start (`create_all`). Mulai Phase 2 skema akan dikelola dengan migrasi Alembic agar perubahan tidak menghapus data.
- Audio privat: tidak ada URL publik; setiap file hanya bisa diambil lewat API dengan sesi pemilik proyek.
- Batas upload ditegakkan 2 lapis: Caddy (`CADDY_MAX_BODY`) dan backend (`MAX_UPLOAD_MB`).

## Hostinger VPS (yang sudah ada n8n + Traefik)
Pasang pertama / update ke versi terbaru (aman untuk n8n, backup DB otomatis):
```bash
cd /opt/ngulik-bass-studio && git pull && setsid nohup bash deploy/hostinger-install.sh > install.log 2>&1 < /dev/null &
tail -n 20 /opt/ngulik-bass-studio/install.log      # cek progres
```
Swap 4 GB (disarankan untuk worker AI, sekali saja):
```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
```
Log worker AI: `docker compose -f docker-compose.hostinger.yml logs --tail=100 worker`
