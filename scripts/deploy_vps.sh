#!/usr/bin/env bash
# Deploy Agentic PMO to the VPS. Prepared, not yet run.
#
# What it does, in order: records the commit it is replacing (the rollback
# target), pulls master, installs requirements into the service venv, restores
# www-data ownership of the tree (SQLite writes into data/, and the unit runs as
# www-data), restarts the unit, then proves the new code is live by reading the
# version out of /api/health and logging in with the credentials already stored
# on the box.
#
# It never prints a password: the login is performed on the server and only the
# HTTP status and role come back.
set -euo pipefail

BOX="${BOX:-root@187.127.179.153}"
APP="/var/www/agentic-pmo/app"
EXPECT_VERSION="${EXPECT_VERSION:-}"

echo "== before =="
ssh "$BOX" "curl -s localhost:8000/api/health | head -c 200; echo"

echo "== deploying =="
ssh "$BOX" "bash -s" <<REMOTE
set -euo pipefail
cd $APP
git config --global --add safe.directory $APP 2>/dev/null || true
PREV=\$(git rev-parse --short HEAD)
echo "rollback target: \$PREV"
git fetch origin master --quiet
git pull --ff-only origin master
.venv/bin/pip install -q -r backend/requirements.txt
chown -R www-data:www-data .
systemctl restart agentic-pmo
sleep 6
systemctl is-active agentic-pmo
curl -s localhost:8000/api/health | head -c 240; echo
REMOTE

echo "== after: version and login =="
ssh "$BOX" "bash -s" <<'REMOTE'
set -euo pipefail
cd /var/www/agentic-pmo/app
UP=$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/api/health)
echo "health HTTP $UP"
# The credentials file the first deployment wrote stays mode 600 on the box.
if [ -f /root/agenticpmo-credentials.txt ]; then
  USER_LINE=$(grep -iE '^ *(admin[_ ]?username|username)' /root/agenticpmo-credentials.txt | head -1 | sed 's/^[^:=]*[:=] *//')
  PASS_LINE=$(grep -iE '^ *(admin[_ ]?password|password)' /root/agenticpmo-credentials.txt | head -1 | sed 's/^[^:=]*[:=] *//')
  CODE=$(curl -s -o /tmp/login.json -w '%{http_code}' -X POST localhost:8000/api/auth/login \
    -H 'Content-Type: application/json' \
    --data "$(python3 -c "import json,sys;print(json.dumps({'identifier':sys.argv[1],'password':sys.argv[2]}))" "$USER_LINE" "$PASS_LINE")")
  echo "login HTTP $CODE"
  if [ "$CODE" = "200" ]; then
    TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/login.json'))['token'])")
    echo "me: $(curl -s localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN" | head -c 160)"
    echo "admin users: $(curl -s -o /dev/null -w '%{http_code}' localhost:8000/api/admin/users -H "Authorization: Bearer $TOKEN")"
  fi
  rm -f /tmp/login.json
else
  echo "no credentials file on the box — verify login by hand"
fi
REMOTE

echo
echo "Public check:"
curl -s -o /dev/null -w '  https://agenticpmo.tech/ -> %{http_code}\n' --max-time 15 https://agenticpmo.tech/
curl -s --max-time 15 https://agenticpmo.tech/api/health | head -c 200; echo

if [ -n "$EXPECT_VERSION" ]; then
  LIVE=$(curl -s --max-time 15 https://agenticpmo.tech/api/health | python3 -c 'import sys,json;print(json.load(sys.stdin).get("version",""))' 2>/dev/null || echo "")
  if [ "$LIVE" != "$EXPECT_VERSION" ]; then
    echo "WARNING: live version is '$LIVE', expected '$EXPECT_VERSION' — investigate before reporting success."
    exit 3
  fi
  echo "version confirmed: $LIVE"
fi

echo
echo "Rollback, if needed:  ssh $BOX 'cd $APP && git checkout <rollback target> && chown -R www-data:www-data . && systemctl restart agentic-pmo'"
