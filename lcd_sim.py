"""Terminal simulator for the stubbed 16x2 LCD + analog button shield.

Runs an unmodified challenge module (original_py, your_version_py,
your_version_2p, ...) against a fake LiquidCrystal that keeps a real
character buffer and paints it in the terminal, plus a fake analogRead
that turns keyboard presses into keypad-shield voltages.

Usage:
    python lcd_sim.py your_version_2p
    python lcd_sim.py original_py

Keys:
    up / w      -- "UP" button    (~0 counts)
    down / s    -- "DOWN" button  (~130 counts)
    left / a    -- "LEFT" button  (~305 counts)
    right / d   -- "RIGHT" button (~480 counts)
    enter       -- "SELECT"       (~720 counts)
    q / ctrl-c  -- quit
"""

import importlib
import os
import sys
import time

import libs_py


# Voltage-divider counts produced by a typical DFRobot-style LCD keypad
# shield. evaluateButton() in the challenge code only distinguishes the
# first two, but the rest are here so mis-thresholding is visible.
BUTTON_COUNTS = {
    "up": 0,
    "down": 130,
    "left": 305,
    "right": 480,
    "select": 720,
}
NO_BUTTON = 1023

# Rendered stand-ins for createChar() glyph slots, picked by inspecting
# the bitmap so up/down arrows come out looking like up/down arrows.
FALLBACK_GLYPHS = "@#*+=%&$"
UNDEFINED_GLYPH = "¿"  # inverted question mark: written but never defined


def _glyph_for(bitmap, slot):
    """Guess a printable stand-in for an 8-row 5-bit custom character."""
    rows = list(bitmap) + [0] * 8
    top = sum(bin(r).count("1") for r in rows[:4])
    bottom = sum(bin(r).count("1") for r in rows[4:8])
    if top > bottom:
        return "^"
    if bottom > top:
        return "v"
    return FALLBACK_GLYPHS[slot % len(FALLBACK_GLYPHS)]


class Console:
    """Minimal ANSI screen painter with a Windows-safe VT enable."""

    def __init__(self):
        if os.name == "nt":
            os.system("")  # flips on VT processing in legacy conhost
        sys.stdout.write("\x1b[2J\x1b[?25l")
        sys.stdout.flush()

    def paint(self, lines):
        sys.stdout.write("\x1b[H")
        sys.stdout.write("\n".join(line + "\x1b[K" for line in lines))
        sys.stdout.write("\x1b[0J")
        sys.stdout.flush()

    def close(self):
        sys.stdout.write("\x1b[?25h\n")
        sys.stdout.flush()


class Keyboard:
    """Non-blocking single-key reader. Returns a BUTTON_COUNTS key or None."""

    def __init__(self):
        self._posix = os.name != "nt"
        if self._posix:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)

    def poll(self):
        if self._posix:
            return self._poll_posix()
        return self._poll_windows()

    def _poll_windows(self):
        import msvcrt

        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # extended scancode prefix
            code = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code)
        return self._map_ascii(ch)

    def _poll_posix(self):
        import select

        if not select.select([sys.stdin], [], [], 0)[0]:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if select.select([sys.stdin], [], [], 0.01)[0]:
                sys.stdin.read(1)  # '['
                code = sys.stdin.read(1)
                return {"A": "up", "B": "down", "D": "left", "C": "right"}.get(code)
            return None
        return self._map_ascii(ch)

    @staticmethod
    def _map_ascii(ch):
        low = ch.lower()
        if low == "q" or ch == "\x03":
            raise KeyboardInterrupt
        return {
            "w": "up",
            "s": "down",
            "a": "left",
            "d": "right",
            "\r": "select",
            "\n": "select",
        }.get(low)

    def close(self):
        if self._posix:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)


class Simulator:
    """Owns the character buffer, the warning log and the redraw loop."""

    def __init__(self, cols=16, rows=2, poll_interval=0.01):
        self.cols = cols
        self.rows = rows
        self.poll_interval = poll_interval
        self.buffer = [[" "] * cols for _ in range(rows)]
        self.cursor = (0, 0)
        self.custom_chars = {}
        self.warnings = []
        self.calls = 0
        self.pending_button = None
        self.dirty = True
        self.console = Console()
        self.keyboard = Keyboard()

    # -- warnings ------------------------------------------------------

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)
            self.dirty = True

    # -- buffer writes -------------------------------------------------

    def clear(self):
        self.buffer = [[" "] * self.cols for _ in range(self.rows)]
        self.cursor = (0, 0)
        self.dirty = True

    def set_cursor(self, col, row):
        if not (0 <= row < self.rows):
            self.warn("setCursor(%d, %d): row out of range 0..%d"
                      % (col, row, self.rows - 1))
        if not (0 <= col < self.cols):
            self.warn("setCursor(%d, %d): col out of range 0..%d"
                      % (col, row, self.cols - 1))
        self.cursor = (col, row)

    def put(self, text):
        col, row = self.cursor
        if not (0 <= row < self.rows):
            self.warn("print(%r) at row %d: dropped, off-screen" % (text, row))
            return
        clipped = False
        for ch in str(text):
            if col >= self.cols:
                clipped = True
                break
            self.buffer[row][col] = ch
            col += 1
        if clipped:
            self.warn("print(%r) truncated at col %d" % (text, self.cols))
        self.cursor = (col, row)
        self.dirty = True

    def define_char(self, slot, bitmap):
        self.custom_chars[slot] = _glyph_for(bitmap, slot)
        self.dirty = True

    def write_char(self, value):
        if value in self.custom_chars:
            self.put(self.custom_chars[value])
        elif 32 <= value < 127:
            self.put(chr(value))
        else:
            self.warn("write(%r): no createChar() ever defined slot %r"
                      % (value, value))
            self.put(UNDEFINED_GLYPH)

    # -- input ---------------------------------------------------------

    def read_analog(self, pin):
        """Called from the module's hot loop; doubles as the frame tick."""
        self.calls += 1
        if self.dirty:
            self.render()
        time.sleep(self.poll_interval)

        pressed = self.keyboard.poll()
        if pressed is not None:
            self.pending_button = pressed
        if pin != 0:
            self.warn("analogRead(%r): only pin 0 is wired to the keypad" % pin)

        if self.pending_button is None:
            return NO_BUTTON
        counts = BUTTON_COUNTS[self.pending_button]
        self.pending_button = None  # one press == one reported sample
        self.dirty = True
        return counts

    # -- output --------------------------------------------------------

    def render(self):
        top = "+" + "-" * (self.cols + 2) + "+"
        lines = ["", "  " + top]
        for row in self.buffer:
            lines.append("  | " + "".join(row) + " |")
        lines.append("  " + top)
        lines.append("")
        lines.append("  arrows/wasd = buttons   enter = select   q = quit")
        lines.append("  analogRead calls: %d" % self.calls)
        lines.append("")
        if self.warnings:
            lines.append("  API warnings:")
            for message in self.warnings[-8:]:
                lines.append("    ! " + message)
        else:
            lines.append("  API warnings: none")
        self.console.paint(lines)
        self.dirty = False

    def close(self):
        self.render()
        self.keyboard.close()
        self.console.close()


def make_lcd_class(sim):
    class SimulatedLiquidCrystal:
        def __init__(self, *pins):
            sim.pins = pins

        def begin(self, cols, rows):
            sim.cols, sim.rows = cols, rows
            sim.clear()

        def clear(self):
            sim.clear()

        def setCursor(self, col, row):
            sim.set_cursor(col, row)

        def print(self, text):
            sim.put(text)

        def write(self, byte):
            sim.write_char(byte)

        def createChar(self, num, data):
            sim.define_char(num, data)

    return SimulatedLiquidCrystal


def run(module_name):
    sim = Simulator()
    libs_py.LiquidCrystal = make_lcd_class(sim)
    libs_py.analogRead = sim.read_analog
    try:
        importlib.import_module(module_name)  # module calls main() on import
    except KeyboardInterrupt:
        pass
    finally:
        sim.close()
        print("stopped: %s" % module_name)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "your_version_2p")
