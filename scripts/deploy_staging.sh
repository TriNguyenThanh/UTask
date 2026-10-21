#!/usr/bin/env bash
# Run on the staging host. Runtime values arrive on stdin, never as secret arguments.
set -euo pipefail
workdir=${1:?Provide staging workdir}
input_names=(registry_token registry registry_user image_prefix image_tag service_names migration_names gateway_names infrastructure_names gateway_service)
unset "${input_names[@]}"
while IFS='=' read -r name value; do
  [[ -n "$name" && " ${input_names[*]} " == *" $name "* ]] || { echo 'Invalid deploy input name' >&2; exit 1; }
  printf -v "$name" '%s' "$value"
done
for variable in "${input_names[@]}"; do
  [[ -v "$variable" ]] || { echo "Missing deploy input: $variable" >&2; exit 1; }
done

cd "$workdir"
test -s .env || { echo "Missing staging .env on server" >&2; exit 1; }
test -s staging-images.json || { echo 'Missing pinned release images' >&2; exit 1; }
export UTASK_IMAGE_PREFIX="$image_prefix" UTASK_IMAGE_TAG="$image_tag"
read -r -a services <<< "$service_names"
unset COMPOSE_PROFILES
compose=(docker compose --env-file .env -f docker-compose.staging.yml -f staging-images.json)
# CLI --profile replaces COMPOSE_PROFILES, so carry the server's Kafka choice
# into the explicit application profiles without sourcing or printing .env.
compose_environment=$("${compose[@]}" config --environment < /dev/null)
profiles=()
while IFS='=' read -r name value; do
  if [[ "$name" == COMPOSE_PROFILES && ",$value," == *,kafka,* ]]; then
    profiles+=(--profile kafka)
  fi
done <<< "$compose_environment"
unset compose_environment
for service in "${services[@]}"; do
  [[ "$service" =~ ^[a-z][a-z0-9-]*-service$ ]] || { echo "Invalid deploy service name" >&2; exit 1; }
  profiles+=(--profile "$service")
done
compose+=("${profiles[@]}")
"${compose[@]}" config --quiet
printf '%s\n' "$registry_token" | docker login "$registry" --username "$registry_user" --password-stdin
unset registry_token
trap 'docker logout "$registry" >/dev/null 2>&1 || true' EXIT
"${compose[@]}" pull --quiet
# Keep the current config intact until the candidate and apps are ready.
nginx_config="$workdir/infra/nginx/nginx.deployment.conf"
nginx_active="$workdir/infra/nginx/nginx.conf"
test -s "$nginx_config" || { echo 'Missing uploaded Nginx configuration' >&2; exit 1; }
"${compose[@]}" run --rm --no-deps --interactive=false -v "$nginx_config:/etc/nginx/nginx.conf:ro" "$gateway_service" nginx -t < /dev/null
read -r -a infrastructure <<< "$infrastructure_names"
runtime_names=$("${compose[@]}" config --services < /dev/null)
active_infrastructure=()
for name in "${infrastructure[@]}"; do
  if [[ $'\n'"$runtime_names"$'\n' == *$'\n'"$name"$'\n'* ]]; then
    active_infrastructure+=("$name")
  fi
done
infrastructure=("${active_infrastructure[@]}")
if (( ${#infrastructure[@]} )); then
  "${compose[@]}" up -d --no-build --wait --wait-timeout 120 "${infrastructure[@]}" < /dev/null
fi
if [[ " $service_names " == *" ai-service "* ]]; then
  # Existing PostgreSQL volumes do not rerun entrypoint initialization. Provision
  # declared databases idempotently before applying the AI schema migration.
  "${compose[@]}" exec -T --interactive=false postgres /bin/sh /docker-entrypoint-initdb.d/init-databases.sh < /dev/null
  "${compose[@]}" run --rm --no-deps --interactive=false ai-service /app/.venv/bin/alembic upgrade head < /dev/null
fi
for service in "${services[@]}"; do
  if [[ " $migration_names " == *" $service "* ]]; then
    "${compose[@]}" run --rm --no-deps --interactive=false "$service" /app/.venv/bin/python manage.py migrate --noinput < /dev/null
  fi
done
runtime_services=()
while IFS= read -r runtime_service; do
  if [[ "$runtime_service" != "$gateway_service" ]]; then
    runtime_services+=("$runtime_service")
  fi
done <<< "$runtime_names"

# Every active runtime is explicit here; database readiness and migrations were
# gated above. Compose dependencies wait for API readiness during manual startup.
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 120 "${runtime_services[@]}" < /dev/null
if [[ -f "$nginx_active" ]]; then
  cat "$nginx_config" > "$nginx_active"
else
  install -m 644 -- "$nginx_config" "$nginx_active"
fi
# Compose applies changed image/ports/mounts; unchanged containers keep running.
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 120 "$gateway_service" < /dev/null
"${compose[@]}" exec -T --interactive=false "$gateway_service" nginx -t < /dev/null
"${compose[@]}" exec -T --interactive=false "$gateway_service" nginx -s reload < /dev/null
for service in "${services[@]}"; do
  if [[ " $migration_names " == *" $service "* ]]; then
    "${compose[@]}" exec -T --interactive=false "$service" /app/.venv/bin/python manage.py migrate --check < /dev/null
  fi
done
read -r -a gateway_paths <<< "$gateway_names"
gateway_check=$(cat <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

path = sys.argv[1]
url = 'http://' + sys.argv[2] + path
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(1, 4):
    print(f'Gateway health: {path} (attempt {attempt}/3)', flush=True)
    try:
        request = urllib.request.Request(url, headers={'Host': sys.argv[2], 'Accept': 'application/json'})
        with opener.open(request, timeout=5) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError('Unexpected HTTP status or redirect')
            payload = json.loads(response.read(65536))
        if not isinstance(payload, dict) or payload.get('success') is False:
            raise ValueError('Unexpected readiness response')
        data = payload.get('data', payload)
        if not isinstance(data, dict) or data.get('status') != 'ok':
            raise ValueError('Backend is not ready')
        break
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f'Gateway health failed: {path} ({type(error).__name__})', file=sys.stderr)
        if attempt == 3:
            sys.exit(1)
        time.sleep(2)
PY
)
for health_path in "${gateway_paths[@]}"; do
  "${compose[@]}" exec -T --interactive=false "${services[0]}" /app/.venv/bin/python -c "$gateway_check" "$health_path" "$gateway_service" < /dev/null
done
"${compose[@]}" ps
