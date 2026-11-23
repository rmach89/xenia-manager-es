#!/bin/bash
# Xenia Manager uninstaller - https://github.com/rmach89/xenia-manager-es
#
#   bash /userdata/system/xenia-manager/uninstall.sh [--purge] [--yes]
#
#   --purge  also delete profiles, caches and downloaded patches
#   --yes    don't ask for confirmation
#
# Also removes Xenia Netplay (installed by Xenia Manager); its saves are shared
# with your other Xenia builds and are kept.
# Never touched: your games, saves, Xenia itself, save backups
# (/userdata/saves/xenia-manager) and the drop folder (/userdata/xbox360-content).

set -u

USERDATA="/userdata"
APP_DIR="${USERDATA}/system/xenia-manager"
DATA_DIR="${USERDATA}/system/configs/xenia-manager"
APPS_DIR="${USERDATA}/system/.local/share/applications"
PORTS_DIR="${USERDATA}/roms/ports"
PORT_SCRIPT="Xenia Manager.sh"

PURGE=0
YES=0
for a in "$@"; do
    case "$a" in
        --purge) PURGE=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    esac
done

if [ "${YES}" -ne 1 ] && [ -t 0 ]; then
    printf 'Remove Xenia Manager%s? [y/N] ' "$([ ${PURGE} -eq 1 ] && echo ' and its profiles')"
    read -r ans
    case "${ans}" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 0 ;; esac
fi

pyx() {
    [ -d "${APP_DIR}/xenia_manager" ] || return 0
    PYTHONPATH="${APP_DIR}" python3 -m xenia_manager "$@" >/dev/null 2>&1 || true
}
pyi() {
    [ -d "${APP_DIR}/xenia_manager" ] || return 0
    PYTHONPATH="${APP_DIR}" python3 -m xenia_manager.integration "$@" >/dev/null 2>&1 || true
}

echo "==> Undoing any settings left by an interrupted game"
pyx recover

echo "==> Removing Xenia Netplay and any Xbox 360 games set to use it"
pyx netplay remove

echo "==> Removing links and the xenia_manager service"
SERVICE="${USERDATA}/system/services/xenia_manager"
if command -v batocera-services >/dev/null 2>&1; then
    batocera-services stop xenia_manager >/dev/null 2>&1 || true
    batocera-services disable xenia_manager >/dev/null 2>&1 || true
fi
if command -v hippos-services >/dev/null 2>&1; then
    hippos-services stop xenia_manager >/dev/null 2>&1 || true
    hippos-services disable xenia_manager >/dev/null 2>&1 || true
fi
if [ -f "${APP_DIR}/integration/service.sh" ]; then
    bash "${APP_DIR}/integration/service.sh" unlink >/dev/null 2>&1 || true
fi
rm -f "${SERVICE}"
pkill -f "^python3 -m xenia_manager watch" >/dev/null 2>&1 || true
# files from versions before 1.2 (copied instead of linked)
rm -f "${USERDATA}/system/scripts/xenia-manager.sh" \
      "${APPS_DIR}/xenia-manager.desktop" "${APPS_DIR}/xenia-manager-uninstall.desktop" \
      "${USERDATA}/Desktop/xenia-manager.desktop"
pyi gamelist-remove "${PORTS_DIR}/gamelist.xml" "./${PORT_SCRIPT}"
rm -f "${PORTS_DIR}/${PORT_SCRIPT}" "${PORTS_DIR}/images/xenia-manager.png"

if [ "${PURGE}" -eq 1 ]; then
    echo "==> Removing per-game Xenia build choices from batocera.conf"
    pyi clear-emulator-choices
fi

echo "==> Removing program files"
rm -rf "${APP_DIR}"

if [ "${PURGE}" -eq 1 ]; then
    if [ -d "${DATA_DIR}/disabled-content" ] && [ -n "$(ls -A "${DATA_DIR}/disabled-content" 2>/dev/null)" ]; then
        mkdir -p "${USERDATA}/saves/xenia-manager"
        rm -rf "${USERDATA}/saves/xenia-manager/disabled-content"
        mv "${DATA_DIR}/disabled-content" "${USERDATA}/saves/xenia-manager/disabled-content"
        echo "    Switched-off DLC / title updates moved to ${USERDATA}/saves/xenia-manager/disabled-content"
    fi
    rm -rf "${DATA_DIR}"
    echo "==> Profiles and caches deleted"
else
    echo "    Profiles kept in ${DATA_DIR} (reinstall to use them again)"
fi

if command -v curl >/dev/null 2>&1; then
    curl -fs -m 3 http://127.0.0.1:1234/reloadgames >/dev/null 2>&1 || true
fi

echo "==> Xenia Manager removed."
echo "    Save backups (if any) are still in ${USERDATA}/saves/xenia-manager"
exit 0
