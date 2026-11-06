#!/usr/bin/env bash
# Checks one IGNIS address from outside Railway. Exit 0 = healthy; exit 1 = failed.
# Usage: uptime_check.sh <base-url> <check-ingest: true|false>
# A failure must repeat ATTEMPTS times, so a redeploy or a network blip stays quiet.
set -u

BASE_URL="${1:?base url}"
CHECK_INGEST="${2:-false}"
ATTEMPTS="${UPTIME_ATTEMPTS:-3}"
PAUSE="${UPTIME_PAUSE_SECONDS:-60}"

check_once() {
  local body code
  body="$(mktemp)"
  code="$(curl -sS -m 20 -o "$body" -w '%{http_code}' "$BASE_URL/ready" 2>/dev/null || echo 000)"
  if [ "$code" != "200" ] || ! grep -q '"status":"ready"' "$body"; then
    echo "$BASE_URL/ready: HTTP $code"
    rm -f "$body"
    return 1
  fi
  if [ "$CHECK_INGEST" = "true" ]; then
    code="$(curl -sS -m 20 -o "$body" -w '%{http_code}' "$BASE_URL/api/v1/orbital-alerts/sources" 2>/dev/null || echo 000)"
    if [ "$code" != "200" ] || ! "${PYTHON:-python3}" -c 'import json,sys; sys.exit(0 if any(s["source"]=="INPE_QUEIMADAS" and s["state"]=="live" for s in json.load(open(sys.argv[1]))) else 1)' "$body"; then
      echo "$BASE_URL: INPE não está em estado live (HTTP $code)"
      rm -f "$body"
      return 1
    fi
  fi
  rm -f "$body"
  echo "$BASE_URL: ok"
}

for attempt in $(seq 1 "$ATTEMPTS"); do
  check_once && exit 0
  [ "$attempt" -lt "$ATTEMPTS" ] && sleep "$PAUSE"
done
exit 1
