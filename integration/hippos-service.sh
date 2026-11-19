#!/bin/bash
# Xenia Manager - HippOS service
# Installed to /userdata/system/services/xenia_manager
# Managed with: hippos-services enable|disable|start|stop xenia_manager
#
# HippOS has no game start hook, so this small watcher notices Xbox 360
# launches and applies each game's profile before Xenia reads its config.

APP_DIR="/userdata/system/xenia-manager"
DATA_DIR="/userdata/system/configs/xenia-manager"
PIDFILE="/tmp/xenia-manager-watch.pid"

running() {
    [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null
}

case "$1" in
    start)
        running && exit 0
        mkdir -p "${DATA_DIR}"
        setsid env PYTHONPATH="${APP_DIR}" PYTHONDONTWRITEBYTECODE=1 \
            python3 -m xenia_manager watch </dev/null >>"${DATA_DIR}/watch.out" 2>&1 &
        echo $! >"${PIDFILE}"
        ;;
    stop)
        if running; then
            kill "$(cat "${PIDFILE}")" 2>/dev/null
        fi
        rm -f "${PIDFILE}"
        ;;
    status)
        if running; then echo "running"; else echo "stopped"; exit 1; fi
        ;;
    *)
        echo "usage: $0 start|stop|status"
        exit 1
        ;;
esac
exit 0
