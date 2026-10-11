#!/usr/bin/env bash
# =====================================================================
#  deploy.sh - deploy the RAG chatbot to the server in one command
#
#  Run from Git Bash on your PC, inside the RAG folder:
#      bash deploy.sh
#
#  It will:
#    1. pack the project and upload it to the server
#    2. check your local .env.prod and upload it (the server always uses this file)
#    3. build + start rag-db, rag-api, rag-web (Docker)
#    4. load the PDFs into Postgres when they (or the ingest code) changed
#    5. start everything, incl. daily database backups
#    5. get an SSL certificate for the domain (first time only)
#    6. add the site to chat-nest-nginx (first time), or update its block when this
#       script has a newer version (always with a backup + nginx -t before reloading)
#
#  Safe to run again after every code or PDF change.
# =====================================================================
set -euo pipefail

SERVER="pingcrood-server"                 # ssh host (from your ~/.ssh/config)
DOMAIN="rag.store.fawadiqbal.dev"
REMOTE_DIR="RAG"                          # folder in the server's home
NGINX_CONTAINER="chat-nest-nginx"
NGINX_CONF="/home/opc/chat-nest-backend/nginx/nginx.conf"
NGINX_BLOCK_VERSION="rag-nginx-block v2"     # bump when nginx_block() changes, so the server gets updated

say()  { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# Read KEY from an env file (ignores comments and inline "# ..." notes)
env_value() {
  { grep -E "^$2=" "$1" || true; } | tail -1 | cut -d= -f2- | sed -e 's/[[:space:]]#.*$//' -e 's/\r$//' \
    -e 's/^["'"'"']//' -e 's/["'"'"']$//' | xargs
}

check_env_file() {
  local f="$1" v
  [ -f "$f" ] || fail "No $f here. Create it:  cp .env.prod.example .env.prod  and fill it in."
  for key in RAG_DB_PASSWORD ADMIN_TOKEN; do
    v="$(env_value "$f" "$key")"
    [ -n "$v" ] || fail "$key is missing in $f."
    case "$v" in change-me|changeme) fail "$key in $f is still the placeholder. Use: openssl rand -hex 16";; esac
    [ "${#v}" -ge 16 ] || fail "$key in $f is too short (use at least 16 characters)."
  done
  if [ "$(env_value "$f" LLM_PROVIDER)" = "anthropic" ]; then
    case "$(env_value "$f" ANTHROPIC_API_KEY)" in sk-ant-*) ;; *) fail "LLM_PROVIDER=anthropic needs ANTHROPIC_API_KEY in $f.";; esac
  fi
  echo "$f looks good (models: $(env_value "$f" LLM_PROVIDER || true) $(env_value "$f" LLM_MODEL || true))"
}

# ---------------------------------------------------------------------
#  PART A - runs on your PC
# ---------------------------------------------------------------------
local_part() {
  cd "$(dirname "$0")"
  [ -f docker-compose.prod.yml ] || fail "Run this from the RAG folder."

  check_env_file .env.prod

  say "Packing the project"
  local pkg; pkg="$(mktemp -t rag-XXXX).tgz"
  tar --exclude=node_modules --exclude=.next --exclude=__pycache__ \
      --exclude=chroma_db --exclude=.env --exclude=.env.prod --exclude=backups \
      -czf "$pkg" .

  say "Uploading to $SERVER"
  ssh "$SERVER" "mkdir -p ~/$REMOTE_DIR"
  scp -q "$pkg" "$SERVER:~/rag-upload.tgz"
  rm -f "$pkg"
  ssh "$SERVER" "tar xzf ~/rag-upload.tgz -C ~/$REMOTE_DIR && rm ~/rag-upload.tgz"

  say "Uploading .env.prod"
  local envtmp; envtmp="$(mktemp)"
  tr -d '\r' < .env.prod > "$envtmp"          # Windows line endings would break the values
  scp -q "$envtmp" "$SERVER:~/$REMOTE_DIR/.env.prod.new"
  rm -f "$envtmp"
  ssh "$SERVER" "chmod 600 ~/$REMOTE_DIR/.env.prod.new"

  say "Running the deployment on the server"
  ssh -t "$SERVER" "bash ~/$REMOTE_DIR/deploy.sh --remote"
}

# ---------------------------------------------------------------------
#  PART B - runs on the server
# ---------------------------------------------------------------------
dc() { docker compose -f docker-compose.prod.yml --env-file .env.prod "$@"; }

remote_part() {
  cd ~/"$REMOTE_DIR"

  # ---- 1. settings: install the uploaded .env.prod ----
  if [ -f .env.prod.new ]; then
    if [ -f .env.prod ] && docker volume inspect rag_rag_pgdata >/dev/null 2>&1 \
       && [ "$(env_value .env.prod RAG_DB_PASSWORD)" != "$(env_value .env.prod.new RAG_DB_PASSWORD)" ]; then
      rm -f .env.prod.new
      fail "RAG_DB_PASSWORD in your .env.prod differs from the one the server's database was created with.
Postgres only sets the password once, so the API couldn't log in. Put the old password back in .env.prod
(on the server: grep RAG_DB_PASSWORD ~/$REMOTE_DIR/.env.prod), or reset the database:
docker compose -f docker-compose.prod.yml --env-file .env.prod down -v   (deletes all chats)"
    fi
    mv .env.prod.new .env.prod
    chmod 600 .env.prod
  fi
  [ -f .env.prod ] || fail "No .env.prod on the server. Run deploy.sh from your PC with RAG/.env.prod present."
  mkdir -p backups

  # ---- 2. database ----
  say "Starting the database (rag-db)"
  dc up -d --build rag-db
  for _ in $(seq 1 30); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' rag-db)" = healthy ] && break
    sleep 2
  done

  # ---- 3. build images ----
  # ---- local LLM only when .env.prod asks for it ----
  local main_p fast_p
  main_p="$(env_value .env.prod LLM_PROVIDER)"; main_p="${main_p:-ollama}"
  fast_p="$(env_value .env.prod FAST_LLM_PROVIDER)"; fast_p="${fast_p:-$main_p}"
  if [ "$main_p" = ollama ] || [ "$fast_p" = ollama ]; then
    export COMPOSE_PROFILES=ollama
    say "Starting the local LLM and downloading the model (first time: ~2 GB, a few minutes)"
    dc up -d rag-ollama
    dc run --rm rag-ollama-pull
  else
    unset COMPOSE_PROFILES
    say "Models: $main_p (no local LLM needed)"
    docker stop rag-ollama >/dev/null 2>&1 && echo "Stopped the local LLM container to free memory (its model stays cached)." || true
  fi

  say "Building rag-api and rag-web (slow the first time on 2 ARM cores)"
  dc build rag-api rag-web

  # ---- 4. load PDFs when they changed or the table is empty ----
  local hash chunks
  hash="$(cat backend/data/*.pdf backend/app/rag/ingestion/*.py backend/app/core/config.py | sha256sum | cut -d' ' -f1)"
  chunks="$(docker exec rag-db psql -U rag -d rag -tAc 'SELECT count(*) FROM chunks' 2>/dev/null || echo 0)"
  if [ "$hash" != "$(cat .ingest-hash 2>/dev/null || true)" ] || [ "${chunks:-0}" = 0 ]; then
    say "Loading PDFs into Postgres (scripts/ingest.py)"
    dc run --rm rag-api python -m scripts.ingest
    echo "$hash" > .ingest-hash
  else
    say "PDFs and ingest settings unchanged ($chunks chunks) - skipping ingest"
  fi

  # ---- 5. start everything ----
  say "Starting rag-api and rag-web"
  dc up -d
  local ok=""
  for _ in $(seq 1 40); do
    if docker exec "$NGINX_CONTAINER" wget -qO- http://rag-api:5000/api/health >/dev/null 2>&1; then ok=1; break; fi
    sleep 3
  done
  [ -n "$ok" ] || fail "rag-api is not answering. See: docker logs rag-api"
  echo "API health: $(docker exec "$NGINX_CONTAINER" wget -qO- http://rag-api:5000/api/health)"

  # ---- 6. SSL certificate (first time only) ----
  if ! sudo test -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem"; then
    say "Getting an SSL certificate for $DOMAIN"
    getent hosts "$DOMAIN" >/dev/null || fail "$DOMAIN does not resolve yet. Add the DNS A record, wait a few minutes, run again."

    local auth
    auth="$(sudo sh -c 'grep -h "^authenticator" /etc/letsencrypt/renewal/*.conf 2>/dev/null' | head -1 | awk -F'= *' '{print $2}')"
    if [ -n "$auth" ] && [ "$auth" != standalone ]; then
      fail "Your existing certificates use '$auth', not 'standalone'. Get the certificate for $DOMAIN the same way, then run this script again."
    fi

    echo "nginx will stop for ~30 seconds while the certificate is issued (all sites briefly offline)."
    docker stop "$NGINX_CONTAINER" >/dev/null
    trap 'docker start '"$NGINX_CONTAINER"' >/dev/null' EXIT        # always bring nginx back
    sudo certbot certonly --standalone -d "$DOMAIN" \
      --non-interactive --agree-tos --register-unsafely-without-email \
      --pre-hook "docker stop $NGINX_CONTAINER" \
      --post-hook "docker start $NGINX_CONTAINER"
    docker start "$NGINX_CONTAINER" >/dev/null
    trap - EXIT
  fi

  # ---- 7. nginx site: add it, or replace an older version of our block ----
  if ! grep -q "server_name $DOMAIN;" "$NGINX_CONF" || ! grep -q "$NGINX_BLOCK_VERSION" "$NGINX_CONF"; then
    local backup; backup="$HOME/nginx.conf.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$NGINX_CONF" "$backup"
    if grep -q "server_name $DOMAIN;" "$NGINX_CONF"; then
      say "Updating the $DOMAIN block in nginx ($NGINX_BLOCK_VERSION: WebSockets, bigger uploads)"
      local tmp; tmp="$(mktemp)"
      # Copy the config without our old block: from its marker line through the end of
      # the two server { } blocks that follow it (counted by braces). Other sites are untouched.
      awk -v start="# ===================== RAG chatbot ($DOMAIN)" '
        !done && index($0, start) == 1 { skip = 1; depth = 0; opened = 0; finished = 0; next }
        skip {
          o = gsub(/\{/, "{"); c = gsub(/\}/, "}")
          if (o > 0) opened = 1
          depth += o - c
          if (opened && depth == 0) { finished++; opened = 0; if (finished == 2) { skip = 0; done = 1 } }
          next
        }
        { print }
      ' "$NGINX_CONF" > "$tmp"
      if grep -q "server_name $DOMAIN;" "$tmp"; then
        rm -f "$tmp"
        fail "Couldn't find the old $DOMAIN block cleanly; nginx left unchanged. Edit $NGINX_CONF by hand (backup: $backup)."
      fi
      cat "$tmp" > "$NGINX_CONF"          # same file (keeps the container's bind mount working)
      rm -f "$tmp"
    else
      say "Adding $DOMAIN to nginx"
    fi
    nginx_block | tee -a "$NGINX_CONF" >/dev/null
    if ! docker exec "$NGINX_CONTAINER" nginx -t; then
      cat "$backup" > "$NGINX_CONF"
      fail "nginx config test failed - restored the backup ($backup). Nothing was reloaded."
    fi
    docker exec "$NGINX_CONTAINER" nginx -s reload
    echo "Backup of the old config: $backup"
  fi

  say "Done!  https://$DOMAIN"
  echo "Usage stats:  curl -H \"Authorization: Bearer \$(grep ^ADMIN_TOKEN .env.prod | cut -d= -f2)\" https://$DOMAIN/api/admin/stats"
  echo "Backups:      ~/$REMOTE_DIR/backups (daily, last 7 days kept)"
  curl -s -o /dev/null -w "Website answered with HTTP %{http_code}\n" "https://$DOMAIN" || true
  dc ps
}

nginx_block() { cat <<EOF

# ===================== RAG chatbot ($DOMAIN) =====================
# $NGINX_BLOCK_VERSION (written by deploy.sh - edit there, not here)
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    client_max_body_size 20m;         # ticket attachments: up to 3 files x 5 MB

    location /ws/ {                   # live updates (WebSockets) for the chat panel and /admin
        proxy_pass http://rag-api:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 1h;        # sockets stay open; the API pings every 25 s
        proxy_send_timeout 1h;
    }

    location /api/ {
        proxy_pass http://rag-api:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_buffering off;          # answers stream word by word (SSE)
    }

    location / {
        proxy_pass http://rag-web:3000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
}

# ---------------------------------------------------------------------
if [ "${1:-}" = "--remote" ]; then remote_part; else local_part; fi
