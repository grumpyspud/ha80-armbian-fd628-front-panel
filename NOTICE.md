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
| `YAopenvfD.conf`, `YAopenvfD.service`, `config-vfd.yaml` | Vendor configuration text files. |
| `dts/openvfd-node.dts` | Decompiled device tree excerpt (facts about the hardware). |

Only text config and data files are included — no compiled vendor binaries.
Everything in this repository still works without them.

No vendor software is executed by this project, and no vendor firmware image is
redistributed here.
