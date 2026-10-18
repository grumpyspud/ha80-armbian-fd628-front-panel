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
   Write letter masks geometrically, never by letter name: an 'E' written as
   A|D|E|F|G is bit-identical to '3'.
2. Do not assume the vendor config's 5-digit ABOX grid mapping (digits on grids 1-4,
   icons on grid 0). Establish the real digit/icon byte positions empirically on your
   own panel; the layout below is for a 4-digit + icons panel.

Adjust CHIP and PIN_* for your board. See the accompanying guide.
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
    "a": A | B | C | E | F | G,
    "b": C | D | E | F | G,
    "B": C | D | E | F | G,
    "C": A | B | C | D,
    "c": A | B | C | D,
    "d": B | C | D | E | G,
    "D": B | C | D | E | G,
    "E": A | B | C | D | G,
    "e": A | B | C | D | G,
    "F": C | D | E | G,
    "G": A | B | C | D | F,
    "H": B | C | E | F | G,
    "h": B | C | E | F | G,
    "K": B | C | E | F | G,
    "L": B | C | D,
    "N": B | C | E | F,
    "n": C | E | G,
    "o": A | B | C | D | E | F,
    "P": C | D | E | F | G,
    "R": C | D | E | F | G,
    "r": E | G,
    "S": A | C | D | F | G,
    "t": D | E | F | G,
    "U": A | B | C | E | F,
    "u": A | B | F,
    "V": B | C | E | F,
    "X": B | C | E | F | G,
    "y": B | C | D | F | G,
    "Z": A | B | D | E | G,
    " ": 0,
    "-": G,
    "_": A,
    "=": A | G,
    "'": E,
    "\u00b0": A | B | C | G,
    "\u00df": A | B | C | D | E | F | G,
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


if __name__ == "__main__":
    # Blink test: prove the wiring before anything else. Everything on, everything off.
    import sys

    panel = FD628(brightness=7)
    print("blink test - every segment and icon should flash. Ctrl-C to stop.")
    try:
        while True:
            panel.write_ram([0xFF] * RAM_SIZE)
            print("all ON")
            time.sleep(2)
            panel.write_ram([0x00] * RAM_SIZE)
            print("all OFF")
            time.sleep(2)
    except KeyboardInterrupt:
        panel.write_ram([0x00] * RAM_SIZE)
        panel.close()
        sys.exit(0)
