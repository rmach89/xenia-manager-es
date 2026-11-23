#!/bin/bash
# Xenia Manager service - https://github.com/rmach89/xenia-manager-es
# Installed to /userdata/system/services/xenia_manager
#   Batocera: batocera-services enable|start|stop xenia_manager  (or Main menu > System settings > Services)
#   HippOS:   hippos-services  enable|start|stop xenia_manager
#
# start   link Xenia Manager into the system (all links live on /userdata,
#         nothing in /usr is changed), and on HippOS start the launch watcher
# stop    stop the HippOS launch watcher (links are left in place)
# unlink  remove every link (used by the uninstaller)
# status  show what is linked / running

APP_DIR="/userdata/system/xenia-manager"
DATA_DIR="/userdata/system/configs/xenia-manager"
INTEG="${APP_DIR}/integration"
PIDFILE="/tmp/xenia-manager-watch.pid"
export HOME="/userdata/system"

if [ -d /usr/lib/hippos ] || [ -x /usr/bin/hippos ]; then OS=hippos; else OS=batocera; fi

user_site() {
    python3 -c 'import site; print(site.getusersitepackages())' 2>/dev/null
}

# "link target source": replace target with a symlink to source
link() {
    mkdir -p "$(dirname "$1")"
    if [ -e "$1" ] && [ ! -L "$1" ]; then rm -rf "$1"; fi
    ln -sfn "$2" "$1"
}

# remove target only if it is a link into our app folder
unlink_ours() {
    if [ -L "$1" ] && case "$(readlink "$1")" in "${APP_DIR}"/*) true ;; *) false ;; esac; then
        rm -f "$1"
    fi
}

links() {
    # target|source
    echo "/userdata/system/.local/share/applications/xenia-manager.desktop|${INTEG}/desktop/xenia-manager.desktop"
    echo "/userdata/system/.local/share/applications/xenia-manager-uninstall.desktop|${INTEG}/desktop/xenia-manager-uninstall.desktop"
    if [ "${OS}" = batocera ]; then
        echo "/userdata/system/scripts/xenia-manager.sh|${INTEG}/batocera-gamestart.sh"
        echo "/userdata/roms/ports/Xenia Manager.sh|${INTEG}/ports-bigscreen.sh"
        echo "/userdata/roms/ports/images/xenia-manager.png|${APP_DIR}/assets/boxart.png"
        site="$(user_site)"
        if [ -n "${site}" ]; then
            echo "${site}/xenia_manager_netplay.py|${INTEG}/batocera/xenia_manager_netplay.py"
            echo "${site}/xenia_manager_netplay-1.0.0.dist-info|${INTEG}/batocera/xenia_manager_netplay-1.0.0.dist-info"
        fi
    else
        echo "/userdata/Desktop/xenia-manager.desktop|${INTEG}/desktop/xenia-manager-bigscreen.desktop"
    fi
}

do_link() {
    [ -d "${APP_DIR}/xenia_manager" ] || { echo "Xenia Manager is not installed"; return 1; }
    mkdir -p "${DATA_DIR}"
    links | while IFS='|' read -r target source; do
        link "${target}" "${source}"
    done
}

do_unlink() {
    links | while IFS='|' read -r target source; do
        unlink_ours "${target}"
    done
    # the user site path depends on the Python version; catch older ones too
    for f in /userdata/system/.local/lib/python3*/site-packages/xenia_manager_netplay*; do
        unlink_ours "$f"
    done
}

watcher_running() {
    [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null
}

start_watcher() {
    watcher_running && return 0
    setsid env PYTHONPATH="${APP_DIR}" PYTHONDONTWRITEBYTECODE=1 \
        python3 -m xenia_manager watch </dev/null >>"${DATA_DIR}/watch.out" 2>&1 &
    echo $! >"${PIDFILE}"
}

stop_watcher() {
    watcher_running && kill "$(cat "${PIDFILE}")" 2>/dev/null
    rm -f "${PIDFILE}"
}

case "$1" in
    start)
        do_link
        PYTHONPATH="${APP_DIR}" python3 -m xenia_manager recover >/dev/null 2>&1
        [ "${OS}" = hippos ] && start_watcher
        ;;
    stop)
        stop_watcher
        ;;
    restart)
        stop_watcher; do_link; [ "${OS}" = hippos ] && start_watcher
        ;;
    unlink)
        stop_watcher; do_unlink
        ;;
    status)
        links | while IFS='|' read -r target source; do
            if [ -L "${target}" ]; then echo "linked   ${target}"; else echo "missing  ${target}"; fi
        done
        if [ "${OS}" = hippos ]; then
            if watcher_running; then echo "watcher  running"; else echo "watcher  stopped"; fi
        fi
        ;;
    *)
        echo "usage: $0 start|stop|restart|unlink|status"
        exit 1
        ;;
esac
exit 0
