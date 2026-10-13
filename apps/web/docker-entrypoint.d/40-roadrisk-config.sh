#!/bin/sh
set -eu

base="${ROADRISK_PUBLIC_API_BASE_URL:-/api}"
case "$base" in
    /*|http://*|https://*)
        ;;
    *)
        echo "ROADRISK_PUBLIC_API_BASE_URL must be a path or an http(s) URL" >&2
        exit 1
        ;;
esac

leftover=$(printf '%s' "$base" | tr -d 'A-Za-z0-9:/._~?&=%+-')
if [ -n "$leftover" ]; then
    echo "ROADRISK_PUBLIC_API_BASE_URL contains a character that cannot be published" >&2
    exit 1
fi

printf 'window.__ROADRISK_API_BASE_URL__ = "%s";\n' "$base" > /usr/share/nginx/html/config.js
