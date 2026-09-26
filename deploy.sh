#!/usr/bin/env bash
# One-command deploy for the Field Agent app (free-tier friendly).
# Usage: ./deploy.sh            -> build + start locally / on any Docker host
#        ./deploy.sh fly        -> deploy to Fly.io free tier (needs `fly` CLI + account)
#        ./deploy.sh render     -> print Render.com free-tier instructions
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-local}"

if [ "$MODE" = "fly" ]; then
  command -v fly >/dev/null || { echo "Install the fly CLI first: https://fly.io/docs/hands-on/install-flyctl/"; exit 1; }
  [ -f fly.toml ] || fly launch --no-deploy --name field-agent --region mia 2>/dev/null || true
  fly secrets set FIELD_AGENT_SECRET="$(openssl rand -hex 32)" 2>/dev/null || true
  fly deploy
  echo "Deployed. Open: $(fly info --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Hostname",""))')"
  exit 0
fi

if [ "$MODE" = "render" ]; then
  cat <<'EOF'
Render.com free tier + Neon free Postgres (recommended $0/mo deploy):
  1. Push this folder to a GitHub repo.
  2. Create a free database at https://neon.com and copy its connection string.
  3. In Render: New -> Blueprint -> connect the repo (render.yaml is included).
     When prompted, paste the Neon connection string as DATABASE_URL.
     FIELD_AGENT_SECRET is auto-generated; SECURE_COOKIES is preset to 1.
  4. Deploy. Render runs the included Dockerfile; health checks hit /healthz.

Why not SQLite on Render: free-tier disks are ephemeral, so a SQLite file
would be wiped on every sleep/redeploy. Neon Postgres is free forever and
the app uses it automatically when DATABASE_URL is set.
EOF
  exit 0
fi

# default: local / any Docker host
if [ ! -f .env ]; then
  echo "FIELD_AGENT_SECRET=$(openssl rand -hex 32)" > .env
  echo "Wrote .env with a random secret."
fi
docker compose up -d --build
echo "Field Agent is running at http://localhost:${PORT:-5000}"
