#!/usr/bin/env bash
# Mobile Use: set up the hub, the MCP server, and (when a phone is plugged in) the app.
#
#   curl -fsSL https://raw.githubusercontent.com/anonymous-namo-1/mobile-use/main/install.sh | bash
#
# A branch other than main (the branch name is not in the script bytes):
#   curl -fsSL https://github.com/anonymous-namo-1/mobile-use/raw/refs/heads/<branch>/install.sh \
#     | MOBILE_USE_BRANCH=<branch> bash
#
# Safe to run again. It never runs `adb kill-server` or `adb disconnect`, and it never
# passes -s to adb (the adb server may be shared with other tools).
set -euo pipefail

REPO="${MOBILE_USE_REPO:-https://github.com/anonymous-namo-1/mobile-use.git}"
DIR="${MOBILE_USE_DIR:-$HOME/mobile-use}"
BRANCH="${MOBILE_USE_BRANCH:-main}"

log() { printf '==> %s\n' "$*" >&2; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

if [ "$(uname -s)" != "Linux" ]; then
  die "This installer supports Linux. On macOS, follow docs/SETUP.md."
fi

SUDO=""
if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  SUDO="sudo"
fi

have() { command -v "$1" >/dev/null 2>&1; }

venv_works() {
  python3 -m venv /tmp/mobile-use-venv-probe >/dev/null 2>&1
}

install_packages() {
  local need_pkgs=0
  if ! have git || ! have python3 || ! venv_works; then
    need_pkgs=1
  fi
  if ! have adb; then
    need_pkgs=1
  fi
  rm -rf /tmp/mobile-use-venv-probe
  if [ "$need_pkgs" -eq 0 ]; then
    log "git, Python, and adb are already installed"
    return
  fi
  if [ -z "$SUDO" ]; then
    die "Need sudo to install git, python3-venv, and adb. Install them, then run this again."
  fi
  if have apt-get; then
    log "Installing git, Python, and adb"
    $SUDO apt-get update
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
      python3 python3-venv python3-pip git ca-certificates android-tools-adb
  elif have dnf; then
    log "Installing git, Python, and adb"
    $SUDO dnf install -y python3 python3-pip git ca-certificates android-tools
  else
    die "Install git, python3-venv, and adb, then run this again."
  fi
  rm -rf /tmp/mobile-use-venv-probe
  venv_works || die "python3 -m venv still fails after installing python3-venv"
  rm -rf /tmp/mobile-use-venv-probe
}

clone_or_update() {
  if [ -d "$DIR/.git" ]; then
    log "Updating $DIR ($BRANCH)"
    git -C "$DIR" fetch origin "$BRANCH"
    git -C "$DIR" checkout "$BRANCH"
    git -C "$DIR" pull --ff-only origin "$BRANCH"
  elif [ -e "$DIR" ]; then
    die "$DIR exists and is not a git checkout. Set MOBILE_USE_DIR to a new path and run this again."
  else
    log "Cloning $REPO ($BRANCH) into $DIR"
    git clone --branch "$BRANCH" -- "$REPO" "$DIR"
  fi
}

setup_python() {
  log "Installing the hub and MCP server dependencies"
  python3 -m venv "$DIR/server/.venv"
  "$DIR/server/.venv/bin/pip" install -q -r "$DIR/server/requirements.txt"
  # Creates server/hub.key the first time. Later runs leave the existing key alone.
  (cd "$DIR/server" && "$DIR/server/.venv/bin/python" -c "import hub; hub.key()")
  chmod 600 "$DIR/server/hub.key"
  # phonectl is invoked as a command; hub.py is started with python, so leave its mode alone
  # (chmod on a tracked file makes the next update look dirty).
  chmod +x "$DIR/server/phonectl" "$DIR/app/build.sh"
  log "Hub key is at $DIR/server/hub.key (keep it private; it was not printed)"
}

install_phone_command() {
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$DIR/server/phonectl" "$HOME/.local/bin/phone"
  if [ -n "$SUDO" ]; then
    $SUDO ln -sfn "$DIR/server/phonectl" /usr/local/bin/phone
  fi
  log "The \`phone\` command points at this checkout"
}

write_unit() {
  local dest="$1" user_line="$2" wanted="$3"
  cat > "$dest" <<EOF
[Unit]
Description=Mobile Use hub (the phone connects here over Tailscale)
After=network-online.target
Wants=network-online.target

[Service]
${user_line}WorkingDirectory=$DIR/server
ExecStart=$DIR/server/.venv/bin/python $DIR/server/hub.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=$wanted
EOF
}

setup_service() {
  if ! have tailscale || ! tailscale ip -4 >/dev/null 2>&1; then
    warn "Tailscale has no IPv4 yet. After 'sudo tailscale up', run this script again to start the hub."
    return
  fi
  if [ -n "$SUDO" ] && have systemctl && [ -d /run/systemd/system ]; then
    local unit="/etc/systemd/system/phone-hub.service"
    local tmp
    tmp="$(mktemp)"
    write_unit "$tmp" "User=$USER
" "multi-user.target"
    $SUDO cp "$tmp" "$unit"
    rm -f "$tmp"
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable phone-hub
    $SUDO systemctl restart phone-hub
    log "Hub service is running (systemctl status phone-hub)"
    return
  fi
  if have systemctl && [ -d /run/systemd/system ]; then
    mkdir -p "$HOME/.config/systemd/user"
    write_unit "$HOME/.config/systemd/user/phone-hub.service" "" "default.target"
    systemctl --user daemon-reload
    systemctl --user enable phone-hub
    systemctl --user restart phone-hub || warn "Could not start the user service. You may need: loginctl enable-linger $USER"
    log "Hub user service installed"
    return
  fi
  warn "systemd is not available. Start the hub yourself:"
  warn "  $DIR/server/.venv/bin/python $DIR/server/hub.py"
}

apk_path() {
  if [ -n "${ANDROID_HOME:-}" ] && [ -x "${ANDROID_HOME}/build-tools/34.0.0/aapt2" ] && have javac; then
    log "Building the Android app"
    (cd "$DIR/app" && ./build.sh >&2)
    printf '%s\n' "$DIR/app/build/mobile-use.apk"
    return
  fi
  log "Using the prebuilt app (dist/mobile-use.apk)"
  if ! (cd "$DIR/dist" && sha256sum -c mobile-use.apk.sha256 >&2); then
    die "dist/mobile-use.apk failed its checksum. Build it with app/build.sh instead of installing it."
  fi
  printf '%s\n' "$DIR/dist/mobile-use.apk"
}

install_apk_if_device() {
  local apk count
  apk="$(apk_path | tail -n 1)"
  if ! have adb; then
    warn "adb is not installed, so the app was not installed on a phone."
    return
  fi
  # Plain `adb`, never -s, and never kill-server or disconnect: the server may be shared.
  count="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" { n++ } END { print n+0 }')"
  if [ "$count" -eq 0 ]; then
    log "No phone in 'adb devices' yet. Connect one and run this script again; it will install the app."
    return
  fi
  if [ "$count" -ne 1 ]; then
    warn "$count phones are connected. Connect only the one you want, then run this again."
    warn "This installer does not pick a device with adb -s."
    return
  fi
  log "Installing Mobile Use on the connected phone"
  adb install -r "$apk"
  adb shell pm grant dev.mobileuse.agent android.permission.POST_NOTIFICATIONS \
    || warn "Could not grant notifications. Allow them on the phone if Android asks."
  if have tailscale && hostip="$(tailscale ip -4 2>/dev/null | head -n 1)" && [ -n "$hostip" ]; then
    # The key is passed to adb and is not printed.
    adb shell am broadcast -a dev.mobileuse.agent.CONFIG -n dev.mobileuse.agent/.ConfigReceiver \
      --es host "$hostip" --ei port 8765 --es key "$(cat "$DIR/server/hub.key")" >/dev/null
    log "Sent the hub address to the phone. The key was not printed."
  else
    warn "Tailscale has no IPv4, so the phone was not given a hub address. Run this script again after 'sudo tailscale up'."
  fi
}

main() {
  install_packages
  clone_or_update
  setup_python
  install_phone_command
  setup_service
  install_apk_if_device
  cat <<EOF

Mobile Use is installed in $DIR.

Still done by you:
  1. Tailscale on this machine and on the phone, same account (sudo tailscale up).
  2. On the phone: Settings → Accessibility → Mobile Use → On.
  3. Tell your agent to use the MCP server:
       $DIR/server/.venv/bin/python $DIR/server/mcp_server.py

Try it: phone status
A blue glow means an agent is on the phone. Stop in the notification halts it.
Paying, sending, deleting, or installing asks you to slide to approve.
EOF
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "$HOME/.local/bin is not on PATH. Open a new shell, or use /usr/local/bin/phone." ;;
  esac
}

main "$@"
