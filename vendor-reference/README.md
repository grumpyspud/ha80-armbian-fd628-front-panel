# vendor-reference — the vendor's own display stack

These files were extracted from the **stock firmware image** of the box this guide was
written for (HA80 / X88 Pro 20, Rockchip RK3566). They are here as **evidence and
reference only**.

> **None of them are required to make the front panel work.** The working solution is
> the userspace driver in the repository root — no kernel module, no daemon, no config
> taken from here. Read these to find *your* board's pins and mapping, then forget them.

They are included so that nobody has to hunt down and extract an old vendor firmware
image to follow this guide — which was the single most annoying part of doing it the
first time.

## What's here

| File | What it is |
|---|---|
| `YAopenvfD.conf` | **The most useful file here.** Holds the GPIO pin numbers, char→grid mapping and icon bit order. |
| `YAopenvfD.service` | Shows *how* the pins are passed: as `modprobe` arguments from that config, not from the device tree. |
| `config-vfd.yaml` | The display's rotation: time 24h → CPU → temp → LAN IP → gateway → date. |
| `dts/openvfd-node.dts` | The device tree node, decompiled from the vendor DTB. Note it has **no GPIO properties at all**. |
| `binaries/openvfd.ko` | The vendor kernel module, built for **6.1.115-haos**. Will not load on a mainline kernel. |
| `binaries/YAopenvfD` | The vendor daemon that feeds the module its display content. |
| `binaries/yaopenvfdctl`, `binaries/OpenVFDService`, `binaries/openvfd_chk` | Supporting vendor userspace tools. |

Licensing and provenance: see [`../NOTICE.md`](../NOTICE.md).

## The pins, as the vendor config states them

```sh
# "This is the OpenVFD module config for HK1 Box (S905X3), but it would probably not
#  work on your box"  -- the comment in the file itself
vfd_gpio_clk='5,2,0'
vfd_gpio_dat='5,11,0'
vfd_gpio_stb='5,12,0'
vfd_chars='4,0,1,2,3'
vfd_dot_bits='0,1,2,3,4,5,6'
vfd_display_type='0x03,0x00,0x00,0x00'
```

Decoded:

- **`5,2,0` is `[bank_table_index, pin, flags]`** — and index 5 is a lookup into a
  *bank-name* table, `{ "periphs-banks", "aobus-banks", "gpio0", "gpio1", "gpio2",
  "gpio3" }`, i.e. the bank **named `gpio3`**. That is why a "bank 5" works on a 5-bank
  SoC, and why numbers copied from an Amlogic config still work on Rockchip:
  **CLK = gpio3 line 2, DAT = gpio3 line 11, STB = gpio3 line 12.**
- **`vfd_chars='4,0,1,2,3'`** = 4 characters mapped to grids **0,1,2,3** — the digit
  layout, and it matches what we measured on hardware.
- **`vfd_dot_bits='0,1,2,3,4,5,6'`** = dot/icon bit order; combined with the type-3 dot
  set (power, ethernet, colon, wifi) these live in the status byte.
- **`vfd_display_type='0x03,...'`** selects that icon/dot set. It is *not* a statement
  that the panel has five digits, even though the driver's internal name for type 3 is
  `DISPLAY_TYPE_5D_7S_ABOX`.

Note the comment: the file warns that it is for a completely different box (an Amlogic
HK1), and it was still correct here. **Config comments lie; the numbers survive because
they go through a name lookup.**

## Extracting these yourself from a vendor image

Back the box up first (you want that anyway), then pull the partitions apart:

```bash
# from a vendor eMMC image / dump
gzip -dc vendor-emmc.img.gz > vendor.img
loop=$(losetup --show -fP vendor.img)          # or use kpartx
lsblk "$loop"

mkdir -p /mnt/vendor-root /mnt/vendor-overlay
mount ${loop}p1 /mnt/vendor-root               # adjust partition numbers to your layout

# the display stack lives here:
#   <root>/usr/lib/modules/<ver>/kernel/drivers/auxdisplay/openvfd/openvfd.ko
#   <root>/usr/bin/YAopenvfD, yaopenvfdctl, openvfd_chk
#   <root>/usr/sbin/OpenVFDService
#   <root>/etc/conf.d/YAopenvfD.conf          <- pins
#   <root>/etc/config/config-vfd.yaml
#   <root>/usr/lib/systemd/system/YAopenvfD.service

grep -rl vfd_gpio /mnt/vendor-root /mnt/vendor-overlay 2>/dev/null

# the device tree node (usually carries no pin information):
dtc -I dtb -O dts -o vendor.dts <root>/boot/dtbs/*.dtb
grep -A6 openvfd vendor.dts

umount /mnt/vendor-root && losetup -d "$loop"
```

`strings` on the module and daemon is also worth a minute — controller names and config
keys appear in plain text.
