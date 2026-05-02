#!/bin/sh
set -eu

mkdir -p /data
mkdir -p /opt/relay-bin

if [ ! -x /opt/relay-bin/xray ]; then
  cp /opt/bundled-bin/xray /opt/relay-bin/xray
  chmod +x /opt/relay-bin/xray
fi

if [ ! -x /opt/relay-bin/sing-box ]; then
  cp /opt/bundled-bin/sing-box /opt/relay-bin/sing-box
  chmod +x /opt/relay-bin/sing-box
fi

exec python /app/app.py
