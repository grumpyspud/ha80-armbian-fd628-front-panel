#!/usr/bin/env bash
# Remove everything install.sh installed. The panel keeps showing whatever it was last
# sent (the display latches), so it will freeze on the last frame - harmless.
#
#   sudo ./uninstall.sh
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }
[[ ${EUID:-0} -eq 0 ]] || die "run me as root: sudo ./uninstall.sh"

SERVICE=fd628-panel

echo "==> stopping and disabling $SERVICE"
systemctl disable --now "$SERVICE" 2>/dev/null || true

echo "==> removing files"
rm -f "/etc/systemd/system/$SERVICE.service"
rm -f "/usr/local/bin/$SERVICE"
rm -rf /usr/local/lib/fd628

systemctl daemon-reload
systemctl reset-failed "$SERVICE" 2>/dev/null || true

echo
echo "Removed. The vendor display stack (if this box has one) was not re-enabled:"
echo "  systemctl enable --now YAopenvfD.service   # only works on a vendor kernel"
