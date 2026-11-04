#!/usr/bin/env bash
# IGNIS — local human-validation stack (docs/IGNIS/HUMAN-VALIDATION-GUIDE.md).
#
#   deploy/local/validate.sh up              build, migrate, IBGE, accounts, ingest, health
#   deploy/local/validate.sh ingest          one live round (INPE; FIRMS if NASA_FIRMS_MAP_KEY)
#   deploy/local/validate.sh ingest-fixture  historical INPE sample (no network, marked fixture)
#   deploy/local/validate.sh status          health, sources and row counts
#   deploy/local/validate.sh credentials     print the local accounts
#   deploy/local/validate.sh e2e [args]      Playwright suite of the web repo against this stack
#   deploy/local/validate.sh stop            stop containers, keep data
#   deploy/local/validate.sh reset           stop and delete ONLY this stack's volume
#
# Requires Docker (Compose v2), bash and curl. The frontend repository is
# expected next to this one (../ignis-fire-watch) or at $IGNIS_WEB_DIR.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HERE/compose.yml")
STATE="$HERE/.validation.env"   # generated, git-ignored
DB_SECRET="$HERE/.validation-db-secret"   # generated, git-ignored (Compose secret)
API=http://localhost:8000
WEB=http://localhost:8080

refuse_remote_targets() {
    # This stack is local only: never run it with deploy credentials around.
    local var
    for var in $(compgen -e); do
        case "$var" in
            RAILWAY_*|DATABASE_URL)
                echo "Recusado: a variável $var está definida neste shell. Abra um shell limpo." >&2
                exit 2 ;;
            *) ;;
        esac
    done
    if [[ "${APP_ENV:-}" == "production" || "${APP_ENV:-}" == "staging" ]]; then
        echo "Recusado: APP_ENV=$APP_ENV neste shell." >&2
        exit 2
    fi
}

random_secret() {
    # 32 random bytes, URL-safe characters only.
    head -c 32 /dev/urandom | base64 | tr -d '/+=\n' | cut -c1-40
}

account_secret() {
    # Random, plus a separator and a digit so the API password policy always holds.
    printf '%s-%s-9' "$(random_secret | cut -c1-6)" "$(random_secret | cut -c1-18)"
}

load_state() {
    if [[ ! -f "$STATE" ]]; then
        echo "==> Gerando segredos locais em $STATE (fora do Git)"
        umask 077
        {
            echo "IGNIS_LOCAL_DB_PASSWORD=$(random_secret)"
            echo "IGNIS_LOCAL_JWT_SECRET=$(random_secret)"
            for role in ADMIN GESTOR CAMPO; do
                echo "IGNIS_VALIDATION_PASSWORD_${role}=$(account_secret)"
            done
        } > "$STATE"
    fi
    set -a
    # shellcheck disable=SC1090
    source "$STATE"
    set +a
    # The database password reaches PostGIS as a Compose secret file and the API
    # as a full URL assembled here, so no credential pattern lives in compose.yml.
    if [[ ! -f "$DB_SECRET" ]]; then
        (umask 077 && printf '%s' "$IGNIS_LOCAL_DB_PASSWORD" > "$DB_SECRET")
    fi
    IGNIS_LOCAL_DATABASE_URL="$(printf '%s://%s:%s@%s/%s' \
        postgresql+asyncpg ignis "$IGNIS_LOCAL_DB_PASSWORD" db:5432 ignis_validation)"
    export IGNIS_LOCAL_DATABASE_URL
}

wait_http() {
    local url=$1 label=$2
    for _ in $(seq 1 90); do
        if curl -fsS -o /dev/null "$url"; then
            echo "    $label ok ($url)"
            return 0
        fi
        sleep 2
    done
    echo "    $label NÃO respondeu ($url)" >&2
    return 1
}

accounts() {
    "${COMPOSE[@]}" run --rm --no-deps \
        -e IGNIS_VALIDATION_PASSWORD_ADMIN -e IGNIS_VALIDATION_PASSWORD_GESTOR \
        -e IGNIS_VALIDATION_PASSWORD_CAMPO \
        --entrypoint python api -m seed.validation_accounts
}

ingest_live() {
    echo "==> Ingestão real (INPE; NASA FIRMS só com NASA_FIRMS_MAP_KEY)"
    "${COMPOSE[@]}" --profile tools run --rm ingest | tail -1 | tee "$HERE/.last-ingest.json"
}

ingest_fixture() {
    echo "==> Ingestão da amostra histórica do INPE (03/11/2026, marcada como fixture)"
    "${COMPOSE[@]}" --profile tools run --rm --entrypoint python ingest \
        -m app.orbital.worker --inpe-fixture data/samples/inpe/focos_diario_br_20261103.csv \
        | tail -1
}

status() {
    echo "==> API"
    curl -fsS "$API/ready" && echo
    echo "==> Fontes"
    curl -fsS "$API/api/v1/orbital-alerts/sources" | python3 -c '
import json, sys
for s in json.load(sys.stdin):
    print(f"    {s[\"label\"]:<26} {s[\"state\"]:<15} origem={s[\"origin\"]} última ingestão={s[\"last_success_at\"]} observação mais recente={s[\"latest_observation_at\"]}")
' 2>/dev/null || curl -fsS "$API/api/v1/orbital-alerts/sources"
    echo "==> Banco (contagens)"
    "${COMPOSE[@]}" exec -T db psql -U ignis -d ignis_validation -tAc \
        "SELECT 'municípios=' || count(*) FILTER (WHERE level='municipality') FROM jurisdictions" \
        -c "SELECT 'detecções=' || count(*) FROM orbital_detections" \
        -c "SELECT 'execuções=' || count(*) FROM ingestion_runs" \
        -c "SELECT 'banco=' || current_database() || ' (container db da pilha ignis-validation)'"
}

credentials() {
    load_state
    cat <<EOF
Contas locais (somente nesta instalação):
  admin   admin.validacao@example.org   $IGNIS_VALIDATION_PASSWORD_ADMIN
  gestor  gestor.validacao@example.org  $IGNIS_VALIDATION_PASSWORD_GESTOR
  campo   campo.validacao@example.org   $IGNIS_VALIDATION_PASSWORD_CAMPO
EOF
}

cmd=${1:-up}
refuse_remote_targets
case "$cmd" in
    up)
        load_state
        echo "==> Construindo imagens (API e web)"
        "${COMPOSE[@]}" build migrate web
        echo "==> Banco, migrations, malha IBGE e API"
        "${COMPOSE[@]}" up -d db migrate api
        wait_http "$API/ready" "API"
        accounts
        # IGNIS_INGEST: auto (live, fixture if INPE fails) | live | fixture (CI: deterministic)
        case "${IGNIS_INGEST:-auto}" in
            fixture) ingest_fixture ;;
            live) ingest_live ;;
            *)
                if ! ingest_live || ! grep -q '"INPE_QUEIMADAS", "product": "FOCOS_DIARIO_BR", "run_id": "[^"]*", "status": "ok"' "$HERE/.last-ingest.json"; then
                    echo "    INPE indisponível agora: usando a amostra histórica documentada."
                    ingest_fixture
                fi ;;
        esac
        "${COMPOSE[@]}" up -d web
        wait_http "$WEB/healthz" "Web"
        status
        echo
        credentials
        echo
        echo "Abra $WEB  (API: $API/docs)"
        ;;
    ingest) load_state; ingest_live ;;
    ingest-fixture) load_state; ingest_fixture ;;
    status) load_state; status ;;
    credentials) credentials ;;
    e2e)
        load_state
        WEB_DIR="${IGNIS_WEB_DIR:-$HERE/../../../ignis-fire-watch}"
        echo "==> Playwright contra $WEB (API $API) — dados reais do PostGIS desta pilha"
        (
            cd "$WEB_DIR"
            export IGNIS_WEB_URL=$WEB IGNIS_API_URL=$API
            export IGNIS_E2E_PASSWORD_ADMIN=$IGNIS_VALIDATION_PASSWORD_ADMIN
            export IGNIS_E2E_PASSWORD_GESTOR=$IGNIS_VALIDATION_PASSWORD_GESTOR
            export IGNIS_E2E_PASSWORD_CAMPO=$IGNIS_VALIDATION_PASSWORD_CAMPO
            ./node_modules/.bin/playwright test "${@:2}"
        )
        ;;
    stop) load_state; "${COMPOSE[@]}" stop ;;
    reset)
        load_state
        echo "==> Removendo containers e o volume ignis-validation_pgdata (somente desta pilha)"
        "${COMPOSE[@]}" --profile tools down --volumes --remove-orphans
        rm -f "$STATE" "$DB_SECRET" "$HERE/.last-ingest.json"
        ;;
    *) sed -n '2,12p' "$0"; exit 64 ;;
esac
