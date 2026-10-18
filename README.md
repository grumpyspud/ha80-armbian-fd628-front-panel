# Driving the front-panel display on an RK3566 TV box from userspace (FD628)

A complete, working method for the little 4-digit display on the front of cheap
Android TV boxes — the one that shows the clock and a couple of status LEDs. No
kernel module, no kernel headers, nothing that breaks on a kernel upgrade.

Written after getting it working on an **AVATTO HA80** (sold as the **X88 Pro 20**,
Rockchip RK3566, board string `ax88pro20`) running **Armbian mainline (6.18)**. The
same method applies to other boxes with an FD628-class panel.

If you only want the answer, jump to [Quick port](#quick-port-to-another-box). If you
want to know how the numbers were derived — including the trick for finding the pins
in a vendor firmware image — read on.

---

## TL;DR

- The panel is an **FD628**: 3-wire (CLK/DAT/STB) shift-register display driver, 4
  seven-segment digits plus a row of icons.
- The vendor's `openvfd.ko` is built for *their* kernel and will not load on mainline,
  and there is no in-tree driver. **Drive it from userspace instead** — `libgpiod`
  bit-banging a ~1.6 kHz software SPI. Nothing to rebuild, ever, and instantly
  reversible.
- Pins on this board: **CLK = gpiochip3 line 2, DAT = gpiochip3 line 11,
  STB = gpiochip3 line 12.**
- RAM is 7 grids x 2 bytes = 14 bytes. On this panel **digits are bytes 0/2/4/6 and the
  status icons are byte 8** — matching the vendor's own `vfd_chars='4,0,1,2,3'` (4 digits
  mapped to grids 0–3).
- Segment bits follow the controller datasheet's own lettering, which is **inverted**
  versus the textbook a–g convention. Write masks geometrically, never by letter.
- Send each frame **twice** and refresh every couple of seconds, or a partially latched
  frame leaves the tail of the panel showing stale content forever.

---

## What's in this repo

| File | Purpose | Installs to |
|---|---|---|
| `fd628.py` | the userspace driver (+ a built-in blink test: `python3 fd628.py`) | `/usr/local/lib/fd628/fd628.py` |
| `fd628-panel` | clock daemon (time + link icons) | `/usr/local/bin/fd628-panel` (mode 0755) |
| `fd628-panel.service` | systemd unit, `Restart=always` | `/etc/systemd/system/fd628-panel.service` |
| `install.sh` | does the above, installs `python3-libgpiod`, enables the service | — |
| `uninstall.sh` | removes everything it installed | — |
| `vendor-reference/` | the vendor's own files, **for reference only** — see `vendor-reference/README.md` | nowhere |

Quick start on a board whose pins you already know:

```bash
sudo ./install.sh
# then, if your pins differ from this board's, edit CHIP / PIN_CLK / PIN_DAT / PIN_STB:
sudo nano /usr/local/lib/fd628/fd628.py
sudo systemctl restart fd628-panel
```

Doing it by hand instead:

```bash
sudo apt install python3-libgpiod
sudo install -D -m 644 fd628.py                  /usr/local/lib/fd628/fd628.py
sudo install -D -m 755 fd628-panel               /usr/local/bin/fd628-panel
sudo install -m 644 fd628-panel.service          /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now fd628-panel
```

**None of the `vendor-reference/` files are needed to make this work** — the working
solution is entirely the userspace driver above. They are included because they are the
evidence for the pin numbers and the digit mapping, and because nobody should have to
find and extract an old vendor firmware image to follow this guide. If you are reusing
this repo, read them, then ignore them.

---

## 1. Why the vendor's approach doesn't survive

On the stock Android/HAOS image the display is driven by a stack like this:

```
vendor kernel module : openvfd.ko        (built for 6.1.115-haos)
userspace daemon     : YAopenvfD  (+ OpenVFDService)
config               : /etc/config/config-vfd.yaml, /etc/conf.d/YAopenvfD.conf
device tree          : an `openvfd` node, usually with no GPIO properties
```

Three reasons not to try to reuse it:

1. **`vermagic` mismatch.** The module is built against the vendor kernel version. On a
   current mainline kernel it will refuse to load, and rebuilding it needs headers that
   match the *running* kernel — which a rolling distribution's repo will not reliably
   give you.
2. **The pins are not in the device tree.** The `openvfd` DT node typically carries no
   GPIO properties at all; the pins are supplied from userspace config (either as
   module parameters or through the daemon's config file).
3. **You don't need it.** The protocol is simple enough to bit-bang. A userspace driver
   cannot be broken by a kernel update, needs no headers, and is one `systemctl stop`
   away from being gone.

---

## 2. Identifying what's actually on the panel

Look at the display: 4 seven-segment digits and a small row of icons (power, ethernet,
wifi, and often a colon between the middle digits) is the classic **FD628** layout.

Distinguish the families before you start, because the protocol differs:

| Part | Wires | Note |
|---|---|---|
| FD628 (and PT6964-class) | 3 (CLK, DAT, **STB**) | what this guide covers |
| FD650 / HBS588-class | 2 (CLK, DAT) | no strobe pin; different framing |

The quickest way to tell is the vendor config: **if it sets a strobe pin
(`vfd_gpio_stb`), it is a 3-wire part.**

### Mine the vendor firmware

Back the eMMC up first (you want this anyway), then extract the old system and look for:

```
usr/lib/modules/*/kernel/drivers/auxdisplay/openvfd/openvfd.ko
usr/bin/YAopenvfD
usr/sbin/OpenVFDService
etc/conf.d/YAopenvfD.conf
etc/config/config-vfd.yaml          <- often holds the real pin numbers
etc/modprobe.d/*.conf
```

`strings` on the module and the daemon is worth doing — controller names, icon names
and config keys all show up in plain text.

Expect the config file to be **boilerplate copied from a different vendor's box**. Ours
contained a comment naming an Amlogic HK1 while sitting on a Rockchip board — and the
pin numbers in it were still correct, for the reason in the next section.

---

## 3. Finding the pins — the part that trips everyone up

Our vendor config looked like this:

```
vfd_gpio_clk='5,2,0'
vfd_gpio_dat='5,11,0'
vfd_gpio_stb='5,12,0'
vfd_gpio_protocol='0,0'
vfd_dot_bits='0,1,2,3,4,5,6'
```

`5,2,0` is `[bank_table_index, pin, flags]` — and the **first field is an index into a
table of GPIO *bank names*, not a bank number**:

```c
/* from the openvfd driver's bank table */
{ "periphs-banks", "aobus-banks", "gpio0", "gpio1", "gpio2", "gpio3" }
```

Index **5 = the bank named `gpio3`**. On a Rockchip SoC the gpiochips carry the same
names, so the value resolves directly: **CLK = gpio3 line 2, DAT = gpio3 line 11,
STB = gpio3 line 12** — i.e. `/dev/gpiochip3` lines 2, 11, 12.

> **Why "bank 5" is the giveaway.** A 5-bank SoC cannot have a bank 5, so a config
> value like `5,2,0` is a strong hint that the first field indexes a *name table*
> rather than addressing a bank directly. Check the driver's table before concluding
> the config is nonsense.

Confirm the lines exist and are unclaimed:

```bash
gpioinfo gpiochip3 | grep -E 'line +(2|11|12):'
cat /sys/kernel/debug/gpio        # make sure nothing else owns them
```

### If you have no vendor config

1. `gpioinfo` every chip and shortlist lines with no consumer and no name.
2. Write the **all-segments-on / all-off blink test** (below) and try candidate
   triples, or the same two pins for a 2-wire part. The blink test is the fastest
   confirmation there is — when the pins are right the whole panel flashes.
3. Prefer pins that are not used by anything else: check
   `/sys/kernel/debug/gpio` and the board's device tree for the same lines.

### The blink test (do this first, always)

Before writing any character table, prove the wiring by turning *everything* on, then
off, repeatedly:

- send the init sequence, then write `0xFF` to all 14 RAM bytes → every segment and
  icon lights;
- write `0x00` → everything dark.

If the panel blinks, your pins, protocol and framing are correct and everything after
this is just bookkeeping. If it does nothing, stop and re-check the pins — do not
start debugging character tables.

---

## 4. The wire protocol

Three-wire software SPI, **LSB first**, idle high:

```
CLK idles HIGH, STB idles HIGH

start : STB LOW
bit   : CLK LOW -> set DAT -> CLK HIGH          (least significant bit first)
stop  : CLK HIGH -> STB HIGH -> DAT HIGH
```

Speed is irrelevant — this is a static latch, not a fast bus. We run ~0.2 ms per
half-bit (~1.6 kHz), which is far below the chip's limit and gives a ~75 ms full frame.
Do not update faster than a few Hz; there is no point and it only risks timing bugs.

### Commands

Each command is its own start/stop frame:

| Byte | Meaning |
|---|---|
| `0x03` | 7-digit mode (send at init) |
| `0x40` | address-increment mode |
| `0xC0 \| addr` | write RAM starting at `addr` |
| `0x80 \| 0x08 \| level` | display ON + brightness (`level` 0–7) |

So a full refresh is: `0x40` frame, then a `0xC0` frame carrying the RAM bytes.

---

## 5. RAM layout, and the trap in the vendor config

The RAM is **7 grids x 2 bytes = 14 bytes**, low byte first within each grid, written
from address 0.

**Read `vfd_chars` from the vendor config first — it is the authoritative digit mapping.**
Ours said `vfd_chars='4,0,1,2,3'`: *4 characters mapped to grids 0, 1, 2, 3*, which is
exactly what we measured on hardware. Do **not** read the display *type* byte as a digit
count — `vfd_display_type='0x03,0x00,0x00,0x00'` selects the icon/dot set (type 3 =
power/LAN/colon/wifi), and the driver's internal name for that type,
`DISPLAY_TYPE_5D_7S_ABOX`, is misleading: it describes the dot layout, not a 5-digit
panel. The icons' grid is not stated anywhere in the config and has to be found on
hardware.

```
byte 0 = digit 1        byte 2 = digit 2        byte 4 = digit 3
byte 6 = digit 4        byte 8 = status icons   (bytes 1,3,5,7,9 = high bytes, unused)
```

### How to establish the layout on an unknown panel

You cannot see the panel if the box is headless — so design **one** test that carries
distinguishable content in every candidate slot, and ask someone to read it back:

- put digits (`1234`) in one candidate set of bytes, and icons in another;
- their report tells you the whole mapping in a single round trip.

Ours came back as `[odd glyph][1][2][3]` with the icons lit — which revealed *both*
that the digit grids were shifted by one (digits are grids 0–3, not 1–4) *and* that the
icons live on grid 4, because the byte we had written as the fourth digit lit them.

Use content that is unambiguous: digits that look different from each other, and
several icons at once so a missing bit is obvious.

### Segment bits

**Read this twice.** The controller datasheet's segment letters are *inverted* relative
to the textbook a–g convention — in the datasheet, `A` is the **bottom** segment and
`D` is the **top**:

```
D (top)        = 0x01        A (bottom)     = 0x08
E (upper-right)= 0x02        B (lower-left) = 0x10
F (lower-right)= 0x04        C (upper-left) = 0x20
G (middle)     = 0x40        dp             = 0x80
```

Digits verified on real hardware: `1`=0x06, `2`=0x5B, `3`=0x4F, `4`=0x66.

**Write every letter mask geometrically, never by letter name.** Because the letters
are inverted, transcribing a table you found online produces glyphs that still light
up but are wrong — e.g. an `E` written as `A|D|E|F|G` is *bit-identical to `3`*, so a
label like `NES` renders as `||35` and looks like a hardware fault rather than a table
error. Correct masks for letters that commonly appear in labels:

```
E = A|B|C|D|G     F = C|D|E|G     G = A|B|C|D|F
P = C|D|E|F|G     U = A|B|C|E|F
```

Ask yourself which segments a human would *see*, then encode those.

### Icon bits (byte 8)

```
power = 0x04      eth = 0x08      colon = 0x10
wifi  = 0x20|0x40     (two bits: "wifi high" and "wifi low" in the driver's terms)
```

The colon is an **icon bit, not a character**. Render a clock as four *digits*
(`strftime("%H%M")`) and light the colon bit; building `"%H:%M"` and truncating to four
characters blanks a digit and gives nonsense like `1 :48` instead of `21:48`.

---

## 6. Reliability: frames can latch partially

A single frame write can land **only partially**: the first bytes update and the tail of
the panel keeps the previous frame's content. Symptom we hit in the field — a game label
whose last two digits and status icons stayed on the clock's values, while the first two
digits updated correctly.

Two cheap defences, both worth having:

1. **Send each RAM payload twice** in one update, so a clipped first pass is completed
   by the second.
2. **Rewrite the current frame every couple of seconds even when nothing changed**, so a
   partial latch heals itself instead of staying wrong until the next state change.

A daemon that writes *only* on state change can be permanently wrong after a single bad
frame. If you are debugging by asking someone what the panel shows, **log the exact RAM
bytes you write on every state change** — comparing those bytes against the description
localises the fault to the write path in one round trip.

---

## 7. The driver

`fd628.py` — protocol, character table and a `show()` that takes text plus an icon
bitmask. Adjust `CHIP`, `PIN_*` for your board.

```python
#!/usr/bin/env python3
"""fd628.py - userspace driver for an FD628 front-panel display.

  wire protocol : 3-wire software SPI, LSB-first.
                  STB LOW = start; per bit: CLK LOW -> DAT -> CLK HIGH;
                  CLK HIGH + STB HIGH + DAT HIGH = stop.
  commands      : 0x03 = 7-digit mode
                  0x40 = address increment mode
                  0xC0|addr = write RAM from addr
                  0x80|0x08|level = display ON + brightness (level 0-7)
  RAM           : 7 grids x 2 bytes (14 bytes, low byte first per grid)
                  byte 0 = digit 1, byte 2 = digit 2, byte 4 = digit 3,
                  byte 6 = digit 4, byte 8 = status icons
  segment bits  : D(top)=0x01 E(upper-right)=0x02 F(lower-right)=0x04
                  A(bottom)=0x08 B(lower-left)=0x10 C(upper-left)=0x20
                  G(middle)=0x40 dp=0x80
  icon bits     : power=0x04 eth=0x08 colon=0x10 wifi=0x20|0x40

TWO THINGS NOT TO "FIX":
1. The segment letters follow the controller datasheet's own table, where 'A' is the
   BOTTOM segment and 'D' is the TOP - the reverse of the textbook a-g convention.
2. Do not assume the vendor config's 5-digit ABOX grid mapping; establish the real
   digit/icon byte positions empirically on your panel.
"""

import time

import gpiod
from gpiod.line import Direction, Value

CHIP = "/dev/gpiochip3"
PIN_CLK, PIN_DAT, PIN_STB = 2, 11, 12
HALF_BIT = 0.0002

RAM_SIZE = 14
DIGIT_BYTES = (0, 2, 4, 6)
ICON_BYTE = 8

A, B, C, D, E, F, G, DP = 0x08, 0x10, 0x20, 0x01, 0x02, 0x04, 0x40, 0x80

SEGMENTS = {
    "0": A | B | C | D | E | F,
    "1": E | F,
    "2": A | B | D | E | G,
    "3": A | D | E | F | G,
    "4": C | E | F | G,
    "5": A | C | D | F | G,
    "6": A | B | C | D | F | G,
    "7": D | E | F,
    "8": A | B | C | D | E | F | G,
    "9": A | C | D | E | F | G,
    "A": A | B | C | E | F | G,
    "b": C | D | E | F | G,
    "C": A | B | C | D,
    "d": B | C | D | E | G,
    "E": A | B | C | D | G,
    "F": C | D | E | G,
    "G": A | B | C | D | F,
    "H": B | C | E | F | G,
    "L": B | C | D,
    "N": B | C | E | F,
    "n": C | E | G,
    "o": A | B | C | D | E | F,
    "P": C | D | E | F | G,
    "r": E | G,
    "S": A | C | D | F | G,
    "t": D | E | F | G,
    "U": A | B | C | E | F,
    "u": A | B | F,
    "y": B | C | D | F | G,
    " ": 0,
    "-": G,
}

ICON_POWER = 0x04
ICON_ETH = 0x08
ICON_COLON = 0x10
ICON_WIFI_HI = 0x20
ICON_WIFI_LO = 0x40
ICON_WIFI = ICON_WIFI_HI | ICON_WIFI_LO


class FD628:
    """Drives the panel. Hold one instance for the lifetime of your daemon."""

    def __init__(self, brightness=5):
        self.brightness = brightness & 0x07
        self.lines = gpiod.request_lines(
            CHIP,
            consumer="fd628-panel",
            config={(PIN_CLK, PIN_DAT, PIN_STB): gpiod.LineSettings(
                direction=Direction.OUTPUT, output_value=Value.ACTIVE)},
        )
        self._init_chip()

    def _w(self, line, val):
        self.lines.set_value(line, Value.ACTIVE if val else Value.INACTIVE)

    def _shift(self, value):
        for i in range(8):
            self._w(PIN_CLK, 0)
            time.sleep(HALF_BIT)
            self._w(PIN_DAT, (value >> i) & 1)
            time.sleep(HALF_BIT)
            self._w(PIN_CLK, 1)
            time.sleep(HALF_BIT)

    def _frame(self, first, rest=()):
        self._w(PIN_STB, 0)
        time.sleep(HALF_BIT)
        self._shift(first)
        for byte in rest:
            self._shift(byte)
        self._w(PIN_CLK, 1)
        self._w(PIN_STB, 1)
        self._w(PIN_DAT, 1)
        time.sleep(HALF_BIT)

    def _init_chip(self):
        self._frame(0x03)                                  # 7-digit mode
        self._frame(0x80 | 0x08 | self.brightness)         # display on + brightness
        self.write_ram([0] * RAM_SIZE)

    def write_ram(self, ram):
        """ram: 14 bytes in shift order (grid0 low, grid0 high, grid1 low, ...).

        Sent TWICE: a frame that latches only partially leaves the tail of the panel
        showing the previous frame, and the repeat lands the tail even when the first
        pass is clipped.
        """
        if len(ram) != RAM_SIZE:
            raise ValueError(f"expected {RAM_SIZE} bytes, got {len(ram)}")
        for _ in range(2):
            self._frame(0x40)                              # address increment mode
            self._frame(0xC0, ram)                         # write from address 0

    def show(self, text, icons=0, dots=None):
        """text: up to 4 characters, right-aligned. icons: bitmask. dots: per-digit dp."""
        ram = [0] * RAM_SIZE
        ram[ICON_BYTE] = icons & 0xFF
        chars = str(text).rjust(4)[-4:]
        for index, byte_index in enumerate(DIGIT_BYTES):
            mask = SEGMENTS.get(chars[index], 0)
            if dots and dots[index]:
                mask |= DP
            ram[byte_index] = mask
        self.write_ram(ram)
        return ram

    def close(self):
        self.lines.release()
```

Minimal use:

```python
from fd628 import FD628, ICON_POWER, ICON_ETH, ICON_COLON, ICON_WIFI

panel = FD628(brightness=5)
panel.show("1234", icons=ICON_POWER | ICON_ETH)   # prove digits + icons
panel.show("2150", icons=ICON_POWER | ICON_COLON) # clock, colon lit
```

---

## 8. A clock daemon

What we actually run: `boot`/`rdy` at startup, then the time with a blinking colon,
plus power always on and the ethernet/wifi icon lit to match the live link.

Note the deliberate restraint — the first version also displayed the running system
(`NES`, `PSX`) while a game was playing. On hardware it read worse than it looked on
paper, because four segments cannot render a legible label. **A panel this small is
good for a clock and link lights and not much else**; decide content with the panel in
front of you, not on paper.

```python
#!/usr/bin/env python3
"""Front-panel clock: time + link icons. Runs as root under systemd."""

import os
import sys
import time

sys.path.insert(0, "/usr/local/lib/fd628")

from fd628 import FD628, ICON_COLON, ICON_ETH, ICON_POWER, ICON_WIFI

BRIGHTNESS = int(os.environ.get("PANEL_BRIGHTNESS", "5"))
TICK = 0.5
REFRESH = 2.0
BOOT_HOLD = 4.0
READY_HOLD = 2.0


def read_str(path, default=""):
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return default


def link_up(*prefixes):
    """True if any interface starting with those prefixes has carrier."""
    try:
        names = os.listdir("/sys/class/net")
    except OSError:
        return False
    for name in names:
        if name.startswith(prefixes) and read_str(f"/sys/class/net/{name}/carrier") == "1":
            return True
    return False


def status_icons():
    icons = ICON_POWER
    if link_up("end", "eth"):
        icons |= ICON_ETH
    if link_up("wlan"):
        icons |= ICON_WIFI
    return icons


def main():
    panel = FD628(brightness=BRIGHTNESS)

    panel.show("boot", icons=ICON_POWER)
    time.sleep(BOOT_HOLD)
    panel.show("rdy", icons=status_icons())
    time.sleep(READY_HOLD)

    last_state = None
    last_write = 0.0
    while True:
        try:
            # Four DIGITS plus the colon ICON - never a ':' character in the text.
            colon = (time.time() % 2) < 1.0
            text = time.strftime("%H%M")
            icons = status_icons() | (ICON_COLON if colon else 0)
            state = (text, icons)

            # Rewrite on change, and on a slow timer so a partial latch heals itself.
            if state != last_state or (time.time() - last_write) >= REFRESH:
                ram = panel.show(text, icons=icons)
                if state != last_state:
                    print("frame %r icons=0x%02x ram=%s"
                          % (text, icons, " ".join("%02x" % b for b in ram)),
                          flush=True)
                last_state = state
                last_write = time.time()

            time.sleep(TICK)
        except Exception as exc:                  # never die on a transient error
            print(f"panel loop error: {exc}", file=sys.stderr, flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
```

`/etc/systemd/system/fd628-panel.service`:

```ini
[Unit]
Description=Front-panel display (FD628 userspace driver)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/fd628-panel
Restart=always
RestartSec=3
Environment=PANEL_BRIGHTNESS=5

[Install]
WantedBy=multi-user.target
```

Install and start:

```bash
sudo apt install python3-libgpiod          # or: pip install gpiod
sudo install -D -m 644 fd628.py      /usr/local/lib/fd628/fd628.py
sudo install -D -m 755 fd628-panel   /usr/local/bin/fd628-panel
sudo install -m 644 fd628-panel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fd628-panel
sudo journalctl -u fd628-panel -f          # prints each frame it writes
```

Brightness is `0`–`7` via `PANEL_BRIGHTNESS`. Runs as root because it needs the GPIO
character device; if you prefer, run as a user in the `gpio` group instead.

---

## 9. Quick port to another box

1. **Back up the eMMC** before anything else. You will want the vendor image for
   reference, and it is your only way back.
2. **Find the controller and pins**: look for `openvfd.ko`, `YAopenvfD`,
   `config-vfd.yaml`, `YAopenvfD.conf` in the vendor image. Decode the pin fields
   through the driver's bank-name table (see section 3) — do not assume the first
   number is a bank.
3. **Prove the wiring with the blink test** (all `0xFF` / all `0x00`). Nothing else
   matters until the panel blinks.
4. **Establish the grid layout** with one test that puts digits and icons in different
   candidate byte sets, and have someone read the panel back.
5. **Verify the segment order** with `1234` — if the digits are right, your bit
   assignments are right.
6. **Verify the icons** one bit at a time (or all at once, then narrow down).
7. **Add the reliability measures** (double write + periodic refresh) before you trust
   it, or a single bad frame will leave the display wrong indefinitely.
8. **Ship it as a service** with `Restart=always`.

---

## 10. Pitfalls that cost real time

- **`pkill -f <script-name>` kills your own SSH session.** The pattern matches the
  remote shell whose command line contains that name. Kill an explicit PID instead,
  obtained from a `/proc/*/cmdline` scan or a pattern that cannot match the invoking
  shell.
- **Never trust the vendor config's comments** — they are frequently copied from a
  different vendor's box (ours said Amlogic HK1 on a Rockchip board). The *numbers* can
  still be right, because they go through a name lookup.
- **Do not infer the layout from the display *type* name or the driver's defaults.**
  Read `vfd_chars` (the digit→grid map) from the vendor config, then confirm it on
  hardware — and note the icons' grid appears nowhere in the config at all.
- **The segment letters are inverted** versus the textbook convention. Letter-based
  transcription silently produces wrong-but-lit glyphs (`E` == `3`).
- **The colon is an icon bit, not a character.** `"%H:%M"` truncation blanks a digit.
- **A frame can latch partially**, and a state-change-only writer then stays wrong
  forever. Double-write and refresh on a timer.
- **Check `/sys/kernel/debug/gpio` before driving lines**, so you are not fighting
  another driver for the same pins.
- **Watch for a line already claimed** — `gpiod.request_lines` failing with `EBUSY`
  usually means a stale process still holds it, not that your pins are wrong.

---

## 11. References

- [`arthur-liberman/linux_openvfd`](https://github.com/arthur-liberman/linux_openvfd) —
  the kernel module and daemon the vendor stack is based on. Its
  `driver/openvfd_drv.c`, `driver/controllers/fd628.c`, `driver/protocols/spi_sw.c`,
  `seg7.c` and `fd628.h` are what the protocol, segment table and icon sets here were
  derived from. Reading it is the single highest-value step for a new panel.
- The FD628 datasheet for the command set and RAM organisation (the lettering used in
  this document matches the datasheet's own segment table).
- `libgpiod` documentation for the userspace GPIO API.

Tested on: AVATTO HA80 / X88 Pro 20 (Rockchip RK3566), Armbian mainline 6.18,
FD628 panel, 4 digits + power/ethernet/wifi/colon icons.

*Corrections and additional board pinouts welcome — if you get another box working,
add its pins and layout here.*
