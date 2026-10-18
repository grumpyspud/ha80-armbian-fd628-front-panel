# NOTICE — third-party material in this repository

## Our work

`fd628.py`, `fd628-panel`, `fd628-panel.service`, `install.sh`, `uninstall.sh`,
`README.md` and the documentation under `vendor-reference/` are original work, MIT
licensed (see `LICENSE`).

## Vendor files under `vendor-reference/`

These were **extracted from the stock firmware of one specific device** (HA80 / X88
Pro 20 TV box) and are included **for reference and interoperability documentation
only**. They are **not required** to use anything in this repository: the working
solution is a userspace driver that never loads or executes any of them.

| File | Notes |
|---|---|
| `binaries/openvfd.ko` | Kernel module built for `6.1.115-haos`. Derived from the GPL-2.0 licensed [`arthur-liberman/linux_openvfd`](https://github.com/arthur-liberman/linux_openvfd) driver; corresponding source is available there. Cannot load on a mainline kernel. |
| `binaries/YAopenvfD`, `binaries/yaopenvfdctl`, `binaries/OpenVFDService`, `binaries/openvfd_chk` | Vendor userspace binaries. Copyright belongs to the device vendor and/or upstream authors; no license is supplied with them in the firmware. |
| `YAopenvfD.conf`, `YAopenvfD.service`, `config-vfd.yaml` | Vendor configuration text files. |
| `dts/openvfd-node.dts` | Decompiled device tree excerpt (facts about the hardware). |

**Read before publishing.** The configuration and device tree files are plain data and
are the genuinely useful part. The compiled binaries are redistributed without an
accompanying license grant from their vendor — review whether that is acceptable for
your distribution, and if in doubt delete `vendor-reference/binaries/`, keeping only the
config and device tree files plus the extraction instructions in
`vendor-reference/README.md`. Everything in this repository still works without them.

No vendor software is executed by this project, and no vendor firmware image is
redistributed here.
