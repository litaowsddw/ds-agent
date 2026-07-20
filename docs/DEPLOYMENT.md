# Production deployment

The production stack exposes only Caddy on `127.0.0.1:18080`. Caddy provides
same-origin routing for the Web application and `/api/*`; AgentFlow's own
identity flow remains responsible for application access. The database, cache,
object store, observability services, API, and Web containers have no
host-published ports.

## Prerequisites

- Docker Desktop with Docker Compose v2.24 or newer (`!reset` is required).
- `cloudflared` from Cloudflare for an optional HTTPS Quick Tunnel.
- PowerShell 7 for the commands below.

## Create external secrets

Use the ignored repository-root `.env` file. Never place live values in
`.env.example` or commit `.env`.

```powershell
$jwt = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48)).TrimEnd('=').Replace('+','-').Replace('/','_')
$encryption = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48)).TrimEnd('=').Replace('+','-').Replace('/','_')
$mysqlRoot = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
$mysql = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
$minioUser = "agentflow-" + [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(6)).ToLowerInvariant()
$minio = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
$grafana = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
@"
JWT_SECRET=$jwt
ENCRYPTION_KEY=$encryption
MYSQL_ROOT_PASSWORD=$mysqlRoot
MYSQL_USER=agentflow
MYSQL_PASSWORD=$mysql
MYSQL_DATABASE=agentflow
MINIO_ROOT_USER=$minioUser
MINIO_ROOT_PASSWORD=$minio
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=$grafana
"@ | Set-Content -Encoding utf8 .env
```

## Validate, build, and start

The public API origin is compiled into the Next bundle at image build time.
The production Compose file explicitly supplies `/api` as the build argument.

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose --env-file .env -f docker-compose.yml -f docker-compose.production.yml build
docker compose --env-file .env -f docker-compose.yml -f docker-compose.production.yml up -d
docker compose --env-file .env -f docker-compose.yml -f docker-compose.production.yml ps
```

## Verify locally

```powershell
# The web entry and API health must both be reachable without a browser-level
# Basic Auth prompt; application authentication happens inside AgentFlow.
curl.exe -sS -o NUL -w "%{http_code}`n" http://127.0.0.1:18080/
curl.exe -sS http://127.0.0.1:18080/api/health
```

Expected results are `200` and JSON containing `"status":"ok"`. In a browser,
complete the AgentFlow identity flow and smoke-test `/`, `/agents`, `/chat`,
`/workflows`, and `/runs` at desktop and mobile viewport widths.

## Publish a temporary HTTPS URL

Download `cloudflared` only from Cloudflare's official release or package, then
run:

```powershell
cloudflared tunnel --url http://127.0.0.1:18080
```

The command prints an ephemeral `https://*.trycloudflare.com` URL. Repeat the
Web, `/api/health`, and browser checks against that URL. Quick Tunnels are for
temporary access; use a named tunnel with access policies for persistent
deployment.

## Stop

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.production.yml down
```
