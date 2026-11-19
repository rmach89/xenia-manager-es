#!/bin/bash
# Xenia Manager - Batocera game start hook
# Installed to /userdata/system/scripts/xenia-manager.sh
# Batocera calls: <script> gameStart|gameStop <system> <emulator> <core> <rom>
#
# On Xbox 360 launches it starts a short-lived helper that waits for Batocera
# to write Xenia's config, applies this game's profile, and undoes it when
# the game exits. It returns immediately so the launch is never delayed.

[ "$1" = "gameStart" ] || exit 0
[ "$2" = "xbox360" ] || exit 0

APP_DIR="/userdata/system/xenia-manager"
DATA_DIR="/userdata/system/configs/xenia-manager"
[ -d "${APP_DIR}/xenia_manager" ] || exit 0
mkdir -p "${DATA_DIR}"

setsid env PYTHONPATH="${APP_DIR}" PYTHONDONTWRITEBYTECODE=1 \
    python3 -m xenia_manager hook --emulator "$3" --core "$4" --rom "$5" --pid "$PPID" \
    </dev/null >>"${DATA_DIR}/hook.out" 2>&1 &

exit 0
