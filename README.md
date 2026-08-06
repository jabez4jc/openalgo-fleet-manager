# OpenAlgo Fleet Manager

Multi-server orchestration dashboard for OpenAlgo trading instances.

## Quick Start

```bash
./setup.sh
docker compose up -d
```

Visit http://localhost:8000 — authenticate with the bootstrap password set during setup.

## Features

- Fleet dashboard with health KPIs and per-server instance tables
- Add/edit/remove servers with HTTPS admin API credentials and SSH keys
- Proxied actions: restart, stop, start, health-check, update, reboot, log retrieval
- SSH provisioning wizard: deploy new instances via multi-install.sh on any server
- Audit log tracking every action with actor, server, instance, and timestamp
- Global auth middleware on every route (except login, login-submit, health)

## Architecture

```
Browser → Fleet Manager (FastAPI + Jinja2) ──HTTPS──► Server 1 (openalgo-restart-api)
                                              ──SSH───► Server 1 (multi-install.sh)
                                              ──HTTPS──► Server 2 (openalgo-restart-api)
                                              ──SSH───► Server 2 (multi-install.sh)
                                                    ...
```

A background poller queries `/api/health` on every registered server every 60s.

## Environment Variables

| Variable | Required | Default |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://fleetmgr:changeme@localhost:5432/fleetmgr` |
| `FERNET_KEY` | Yes | — |
| `SESSION_SECRET` | Yes | `dev-secret-change-me` |
| `FLEET_ADMIN_BOOTSTRAP_PASSWORD` | No | — |
| `SCRIPTS_REF` | No | `main` |
| `POLL_INTERVAL_SECONDS` | No | `60` |
| `PARTNER_API_KEY` | No | — (unset disables `/api/partner/*`) |

## Partner API

`/api/partner/*` is the only surface reachable without a fleet operator session.
It exists so the simplifyed.in client area can show customers their own
instances without holding a copy of every server's admin credentials.

Authenticated by the `X-Fleet-Key` header against `PARTNER_API_KEY`. **Unset
means closed** — every request is rejected, not accepted.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/partner/instances` | All servers and their instances, from the poller cache. Explicit field whitelist — no URLs, credentials, SSH details or `raw_json`. |
| `POST` | `/api/partner/restart` | `{server_id, instance, actor}`. Audit-logged as `client:<actor>`. |

Two things this deliberately does not do:

- **It does not authorise anyone.** The key means "you are the website", not
  "you are a customer". Deciding which client may see or touch which instance
  is the website's job.
- **Restart is the only write verb.** Stop, start, update, reboot and
  provisioning stay operator-only and are unreachable with a partner key.

## Deployment (Coolify)

1. Point Coolify at this repo
2. Set build to Dockerfile
3. Add all environment variables as project secrets
4. The global auth middleware is active on first deploy — no unauthenticated pages except `/login`, `/login-submit`, `/health`

## Development

```bash
pip install -r requirements.txt
DATABASE_URL="postgresql+asyncpg://fleetmgr:changeme@localhost:5432/fleetmgr" \
FERNET_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" \
SESSION_SECRET="dev-secret" \
FLEET_ADMIN_BOOTSTRAP_PASSWORD="admin123" \
uvicorn app.main:app --reload --port 8000
```

## Adding a Server

1. Log into the Fleet Manager
2. Go to Servers → Add Server
3. Fill in:
   - Server name and base URL (e.g. `https://trade1.example.com`)
   - Admin API username/password (same as OA_ADMIN_USER / OA_ADMIN_PASS on the server)
   - SSH host, user, port, and private key (for provisioning)
4. The poller will discover instances on the next cycle
