#!/bin/bash
# Bring the Training Hub back up after a reboot or a crash.
#   bash start-hub.sh
APP="/Users/yerik/_apple_lib/_peg_ProgEnvGit/a0ds_CLIENTS/JhonWard/_landing_page/_MandA_AUG_3/app"
cd "$APP" || exit 1

pgrep -f "caffeinate -dimsu" >/dev/null || { nohup caffeinate -dimsu >/dev/null 2>&1 </dev/null & disown; echo "keep-awake  started"; }
pgrep -f "server.py"          >/dev/null || { nohup ./.venv/bin/python server.py > /tmp/hub-server.log 2>&1 </dev/null & disown; echo "app server  started"; }
pgrep -f "cloudflared tunnel run jw" >/dev/null || { nohup cloudflared tunnel run jw > /tmp/hub-tunnel.log 2>&1 </dev/null & disown; echo "tunnel      started"; }

sleep 4
echo
printf "local  : %s\n" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/)"
printf "public : %s  https://jw.caitryapps.com\n" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 https://jw.caitryapps.com/)"
