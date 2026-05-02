#!/bin/sh
set -eu

mkdir -p /data
exec python /app/app.py
