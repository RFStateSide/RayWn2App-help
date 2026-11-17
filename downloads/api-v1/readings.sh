#!/bin/sh
# Copyright (C) 2026 RF StateSide LLC; SPDX-License-Identifier: LGPL-3.0-only
# POSIX shell + curl; no token on curl's command line and no redirect following.
set -eu
: "${RAYWN2_API_URL:?Set an HTTPS origin such as https://station.example:47828}"
: "${RAYWN2_API_TOKEN:?Supply your token privately}"
case "$RAYWN2_API_URL" in https://*) ;; *) echo 'HTTPS required' >&2; exit 2;; esac
case "$RAYWN2_API_TOKEN" in *[!a-f0-9]*|'') echo 'Invalid token format' >&2; exit 2;; esac
[ "${#RAYWN2_API_TOKEN}" -eq 64 ] || { echo 'Invalid token length' >&2; exit 2; }
umask 077
headers=$(mktemp)
response=$(mktemp)
trap 'rm -f "$headers" "$response"' EXIT HUP INT TERM
printf 'Authorization: Bearer %s\n' "$RAYWN2_API_TOKEN" > "$headers"
# The private temporary header file is removed on exit. Do not enable shell tracing.
if [ -n "${RAYWN2_API_CA:-}" ]; then
  status=$(curl --http1.1 --proto '=https' --silent --show-error --fail --connect-timeout 3 --max-time 8 \
    --cacert "$RAYWN2_API_CA" --header "@$headers" --header 'Accept: application/json' \
    --output "$response" --write-out '%{http_code}' \
    --get --data-urlencode "device=${RAYWN2_API_DEVICE:?Set the exact granted device identity}" \
    "${RAYWN2_API_URL%/}/api/v1/readings")
else
  status=$(curl --http1.1 --proto '=https' --silent --show-error --fail --connect-timeout 3 --max-time 8 \
    --header "@$headers" --header 'Accept: application/json' \
    --output "$response" --write-out '%{http_code}' \
    --get --data-urlencode "device=${RAYWN2_API_DEVICE:?Set the exact granted device identity}" \
    "${RAYWN2_API_URL%/}/api/v1/readings")
fi

[ "$status" = 200 ] || { echo "API returned HTTP $status" >&2; exit 1; }
cat "$response"
