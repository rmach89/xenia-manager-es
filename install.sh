#!/bin/bash
# Xenia Manager installer for Batocera and HippOS
# https://github.com/rmach89/xenia-manager-es  -  MIT License
#
#   curl -fsSL https://raw.githubusercontent.com/rmach89/xenia-manager-es/main/install.sh | bash
#
# Options (environment variables):
#   XM_REF=v1.0.0   install a specific tag or branch (default: main)
#
# Running it again updates an existing install and keeps your profiles.

set -euo pipefail

REPO="rmach89/xenia-manager-es"
REF="${XM_REF:-main}"
USERDATA="/userdata"
APP_DIR="${USERDATA}/system/xenia-manager"
DATA_DIR="${USERDATA}/system/configs/xenia-manager"
INBOX_DIR="${USERDATA}/xbox360-content"
APPS_DIR="${USERDATA}/system/.local/share/applications"
PORTS_DIR="${USERDATA}/roms/ports"
PORT_SCRIPT="Xenia Manager.sh"

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

# ---- platform ----------------------------------------------------------------
if [ -d /usr/lib/hippos ] || [ -x /usr/bin/hippos ]; then
    OS="hippos"; OS_LABEL="HippOS"
elif [ -d /usr/share/batocera ] || [ -x /usr/bin/batocera-version ]; then
    OS="batocera"; OS_LABEL="Batocera"
else
    die "This installer is for Batocera or HippOS. No supported system detected."
fi
[ -d "${USERDATA}" ] && [ -w "${USERDATA}" ] || die "${USERDATA} is not writable."

say "Installing Xenia Manager on ${OS_LABEL}"

command -v python3 >/dev/null 2>&1 || die "python3 was not found."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "Python 3.11 or newer is needed (found $(python3 -V 2>&1))."
if ! python3 -c 'import pygame' >/dev/null 2>&1; then
    warn "pygame is missing: the manager window won't open, but launch integration still works."
fi

xenia_found=0
for p in /usr/xenia /usr/xenia-canary /usr/bin/xenia-edge /opt/emulators/xenia /opt/emulators/xenia-canary /opt/emulators/xenia-edge; do
    [ -e "$p" ] && xenia_found=1
done
[ "${xenia_found}" -eq 1 ] || warn "No Xenia build found on this system. Xenia Manager uses the Xenia that ships with ${OS_LABEL}."

# ---- fetch -------------------------------------------------------------------
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

if [ -n "${SCRIPT_DIR}" ] && [ -d "${SCRIPT_DIR}/app/xenia_manager" ]; then
    SRC="${SCRIPT_DIR}"
    say "Using local files in ${SRC}"
else
    URL="https://github.com/${REPO}/archive/${REF}.tar.gz"
    say "Downloading ${REPO} (${REF})"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${URL}" -o "${TMP}/src.tar.gz" || die "Download failed: ${URL}"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "${URL}" -O "${TMP}/src.tar.gz" || die "Download failed: ${URL}"
    else
        die "Neither curl nor wget is available."
    fi
    tar -xzf "${TMP}/src.tar.gz" -C "${TMP}"
    SRC="$(dirname "$(find "${TMP}" -maxdepth 3 -type d -name xenia_manager -path '*/app/*' | head -n1)")"
    SRC="$(dirname "${SRC}")"
    [ -d "${SRC}/app/xenia_manager" ] || die "Downloaded archive looks wrong."
fi

# ---- program files -----------------------------------------------------------
say "Copying program files to ${APP_DIR}"
if [ -d "${APP_DIR}" ] && [ -x "${APP_DIR}/bin/xenia-manager" ]; then
    "${APP_DIR}/bin/xenia-manager" recover >/dev/null 2>&1 || true
fi
rm -rf "${APP_DIR}.new"
mkdir -p "${APP_DIR}.new"
cp -r "${SRC}/app/xenia_manager" "${SRC}/app/bin" "${SRC}/assets" "${APP_DIR}.new/"
cp "${SRC}/uninstall.sh" "${SRC}/LICENSE" "${SRC}/CREDITS.md" "${SRC}/README.md" "${APP_DIR}.new/"
mkdir -p "${APP_DIR}.new/integration"
cp "${SRC}/integration/"*.sh "${APP_DIR}.new/integration/"
find "${APP_DIR}.new" -name '__pycache__' -type d -prune -exec rm -rf {} +
chmod +x "${APP_DIR}.new/bin/xenia-manager" "${APP_DIR}.new/uninstall.sh" "${APP_DIR}.new/integration/"*.sh
VERSION="$(PYTHONPATH="${APP_DIR}.new" python3 -c 'import xenia_manager; print(xenia_manager.__version__)')"
echo "${VERSION} (${REF})" >"${APP_DIR}.new/VERSION"
rm -rf "${APP_DIR}"
mv "${APP_DIR}.new" "${APP_DIR}"

XM="${APP_DIR}/bin/xenia-manager"
ICON="${APP_DIR}/assets/icon.png"
mkdir -p "${DATA_DIR}" "${INBOX_DIR}"
cat >"${INBOX_DIR}/README.txt" <<'EOF'
Xenia Manager drop folder
-------------------------
Copy Xbox 360 DLC and title update packages here (any sub-folder is fine).
Then open Xenia Manager > "Install from drop folder", or a game's
"Title updates" / "DLC" page. Installed files are moved into Xenia.
EOF

pyx() { PYTHONPATH="${APP_DIR}" python3 -m xenia_manager.integration "$@"; }

# ---- launch integration ------------------------------------------------------
if [ "${OS}" = "batocera" ]; then
    say "Adding the game-start hook (/userdata/system/scripts)"
    mkdir -p "${USERDATA}/system/scripts"
    cp "${APP_DIR}/integration/batocera-gamestart.sh" "${USERDATA}/system/scripts/xenia-manager.sh"
    chmod +x "${USERDATA}/system/scripts/xenia-manager.sh"
else
    say "Adding the launch watcher service"
    mkdir -p "${USERDATA}/system/services"
    cp "${APP_DIR}/integration/hippos-service.sh" "${USERDATA}/system/services/xenia_manager"
    chmod +x "${USERDATA}/system/services/xenia_manager"
    if command -v hippos-services >/dev/null 2>&1; then
        hippos-services enable xenia_manager >/dev/null 2>&1 || true
        hippos-services stop xenia_manager >/dev/null 2>&1 || true
        hippos-services start xenia_manager >/dev/null 2>&1 || true
    else
        "${USERDATA}/system/services/xenia_manager" stop || true
        "${USERDATA}/system/services/xenia_manager" start || true
        warn "hippos-services not found; started the watcher for this session only."
    fi
fi

# ---- menus -------------------------------------------------------------------
say "Adding desktop (F1) menu entries"
mkdir -p "${APPS_DIR}"
cat >"${APPS_DIR}/xenia-manager.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Xenia Manager
Comment=DLC, title updates, patches, per-game settings and saves for Xenia
Exec=${XM} ui
Icon=${ICON}
Terminal=false
Categories=Game;batocera.linux;
EOF
cat >"${APPS_DIR}/xenia-manager-uninstall.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Xenia Manager Uninstaller
Comment=Remove Xenia Manager
Exec=${XM} ui --uninstall
Icon=${ICON}
Terminal=false
Categories=Game;batocera.linux;
EOF
chmod +x "${APPS_DIR}/xenia-manager.desktop" "${APPS_DIR}/xenia-manager-uninstall.desktop"

DESC="Manage Xbox 360 DLC, title updates, patches, per-game settings and saves. Changes apply when you start a game from EmulationStation."
if [ "${OS}" = "batocera" ]; then
    say "Adding Big Screen mode to Ports"
    mkdir -p "${PORTS_DIR}/images"
    cat >"${PORTS_DIR}/${PORT_SCRIPT}" <<EOF
#!/bin/bash
# Xenia Manager - Big Screen mode (controller friendly)
exec "${XM}" ui --bigscreen
EOF
    chmod +x "${PORTS_DIR}/${PORT_SCRIPT}"
    cp "${APP_DIR}/assets/boxart.png" "${PORTS_DIR}/images/xenia-manager.png"
    pyx gamelist-add "${PORTS_DIR}/gamelist.xml" "./${PORT_SCRIPT}" "Xenia Manager" "${DESC}" "./images/xenia-manager.png" \
        || warn "Could not update the Ports game list (the entry still appears after a rescan)."
else
    say "Adding Big Screen mode to the Desktop shortcuts list"
    mkdir -p "${USERDATA}/Desktop"
    cat >"${USERDATA}/Desktop/xenia-manager.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Xenia Manager
Comment=${DESC}
Exec=${XM} ui --bigscreen
Icon=${ICON}
Terminal=false
Categories=Game;
EOF
    chmod +x "${USERDATA}/Desktop/xenia-manager.desktop"
fi

if command -v curl >/dev/null 2>&1; then
    curl -fs -m 3 http://127.0.0.1:1234/reloadgames >/dev/null 2>&1 || true
fi

say "Xenia Manager ${VERSION} installed."
cat <<EOF

  Open it:
    - EmulationStation: $( [ "${OS}" = "batocera" ] && echo "Ports > Xenia Manager" || echo "Desktop Shortcuts > Xenia Manager" ) (Big Screen mode)
    - Desktop (F1):     Applications > Xenia Manager
  Drop DLC / title updates in: ${INBOX_DIR}
  Uninstall: Xenia Manager > Uninstall, the "Xenia Manager Uninstaller" desktop entry,
             or: bash ${APP_DIR}/uninstall.sh

  Start each Xenia build once from EmulationStation so it creates its config.
EOF
