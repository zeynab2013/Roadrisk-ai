#!/bin/sh
set -eu

mkdir -p /var/lib/roadrisk
if [ "$(id -u)" = "0" ]; then
    chown roadrisk:roadrisk /var/lib/roadrisk
    exec runuser --user roadrisk -- "$@"
fi

exec "$@"
