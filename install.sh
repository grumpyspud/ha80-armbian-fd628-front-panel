#!/usr/bin/env bash
# Install the FD628 front-panel userspace driver and clock daemon.
#
#   sudo ./install.sh
#
# Run from the repository root. Nothing here needs kernel headers or a kernel module,
# so it survives kernel upgrades.
set -euo pipefail

LIB_DIR=/usr/local/lib/fd628
BIN_DIR=/usr/local/bin
UNIT_DIR=/etc/systemd/system
SERVICE=fd628-panel

die() { echo "error: $*" >&2; exit 1; }

[[ ${EUID:-0} -eq 0 ]] || die "run me as root: sudo ./install.sh"
[[ -f fd628.py && -f fd628-panel && -f fd628-panel.service ]] || \
  die "run me from the repository root (fd628.py, fd628-panel and fd628-panel.service not found)"

# 1. Stop anything that may already own the panel pins, or our request will fail with EBUSY.
if systemctl list-unit-files 2>/dev/null | grep -q '^YAopenvfD\.service'; then
  echo "==> disabling the vendor display service (it would fight us for the pins)"
  systemctl disable --now YAopenvfD.service 2>/dev/null || true
fi
if lsmod 2>/dev/null | grep -q '^openvfd'; then
  echo "==> unloading the vendor kernel module"
  rmmod -f openvfd 2>/dev/null || true
fi

# 2. Userspace GPIO bindings.
if ! python3 -c 'import gpiod' 2>/dev/null; then
  echo "==> installing python3-libgpiod"
  if command -v apt-get >/dev/null; then
    apt-get update -qq && apt-get install -y python3-libgpiod
  else
    die "gpiod python bindings missing and apt-get not available - install libgpiod bindings yourself"
  fi
fi

# 3. Files.
echo "==> installing files"
install -D -m 644 fd628.py                "$LIB_DIR/fd628.py"
install -D -m 755 fd628-panel             "$BIN_DIR/fd628-panel"
install    -m 644 fd628-panel.service     "$UNIT_DIR/$SERVICE.service"

# 4. Service.
echo "==> enabling $SERVICE"
systemctl daemon-reload
systemctl enable --now "$SERVICE"

sleep 2
systemctl --no-pager --lines=6 status "$SERVICE" || true

cat <<'EOF'

Done. If the panel is dark or showing garbage, the pins are wrong for your board:
edit CHIP / PIN_CLK / PIN_DAT / PIN_STB at the top of /usr/local/lib/fd628/fd628.py,
then:  sudo systemctl restart fd628-panel
Follow the journal to see the exact RAM bytes each frame sends:
  sudo journalctl -u fd628-panel -f
EOF
