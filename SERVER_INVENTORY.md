# Server inventory — 9 September 2026, before changes

Inspected over authorized SSH as hp. No existing service configuration changed during discovery.

- Host hp, HP Pavilion 15-cc1xx; Ubuntu 26.04 LTS, kernel 7.0.0-29.
- Intel i5-8250U, four physical/eight logical CPUs; 15 GiB usable RAM, 12 GiB available; 4 GiB unused swap.
- Root ext4 209 GiB, 52 GiB used, 147 GiB available. `/storage` ext4 915 GiB, 863 GiB available.
- Intel UHD620 and NVIDIA 940MX detected. No NVIDIA runtime/CLI installed. CPU inference selected to avoid driver changes.
- Docker 29.1.3, Compose 2.40.3 present. Python3 present. Ollama/Node/npm absent.
- Network wlo1 192.168.1.252, gateway 192.168.1.1. Tailscale 100.98.193.60, direct peer connection verified.
- SSH, Docker, containerd, cloudflared, tailscaled, systemd-networkd and resolved active. Existing services enabled on boot.
- UFW inactive; iptables INPUT/OUTPUT ACCEPT, FORWARD DROP with existing Docker and Tailscale chains. Rules preserved.
- Cloudflare tunnel is remotely managed using a token in `/etc/systemd/system/cloudflared.service`; token deliberately excluded. Metrics loopback 20241. No local ingress config; do not replace service.

## CodeDuel baseline

Actual production Compose: `/opt/codeduel/docker-compose.prod.yml`; environment `/opt/codeduel/.env`. Development Compose differs and is NOT the deployment source.

| Component | Deployment | Baseline |
|---|---|---|
| Public frontend | https://codeduel.online | HTTP 200, 1.07 s |
| Proxy | codeduel-proxy-1, 127.0.0.1:8085 -> 80 | Healthy |
| Frontend | codeduel-frontend-1, internal 8080 | Healthy |
| API | codeduel-api-1, internal 5000, /health/ready | Already crash-looping before changes |
| Worker | codeduel-worker-1 | Already repeatedly exiting before changes |
| Redis | codeduel-redis-1, private 6379, password authentication | Healthy |
| MongoDB | External Atlas cluster0.etfzpvb.mongodb.net | API/worker report MongooseServerSelectionError |
| Judge Docker | Rootless socket /run/user/1001/docker.sock mounted into worker | Existing isolated execution runtime |

API and worker logs say they cannot reach any Atlas server. The log's IP allowlist suggestion is generic; the precise Atlas/network cause is unverified. A successful homepage request does not establish API or submission health. There is no deployed local CodeDuel MongoDB container. Redis data lives at `/opt/codeduel-data/redis`. Networks: codeduel_edge, codeduel_backend (internal), codeduel_egress. These existing services and volumes must remain untouched.

## Other existing containers

maigret, homepage, uptime-kuma, netdata, pihole, flaresolverr, qbittorrent, prowlarr, radarr, sonarr, jellyseerr, jellyfin, nextcloud, nextcloud-redis, nextcloud-db, filebrowser, portainer. 22 existing containers total including five CodeDuel containers. None belong to this project.

Existing TCP listeners include 22,53,3000,3001,5055,6881,7878,8080,8081,8085(loopback),8090,8092,8096,8191,8989,9443,9696,19999; additional loopback/Tailscale ephemeral metrics/control ports. AI project ports chosen separately: web3080; backend18000 and gateway18081 loopback; internal inference11434,Postgres15432,Qdrant16333 loopback.

Project directories: `/opt/codeduel`, `/opt/codeduel-data`, existing `/opt/codeduel-backup-20260712-174119`, `~/docker`, `/srv` media/application directories. Local HomeserverAI repository initially empty. New server project directory reserved: `/home/hp/ai-home-lab-operator`.

## Follow-up observation —07:24UTC

CodeDuel API/worker became healthy around07:19UTC without this project modifying or restarting them. The preexisting outage was transient or recovered externally; its ultimate cause is not established. `/api/health` is not an implemented route (404 after recovery); public checks now use the discovered `/api/explore/problems` route. Internal `/health/ready` verifies MongoDB, Redis, worker heartbeat and sandbox.
