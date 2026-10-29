#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARACHNE - a cinematic ASCII horror spider for your terminal (Windows and Mac)
=============================================================================

ON WINDOWS
  1. Install Python 3.8 or newer from https://www.python.org/downloads/
     During setup, tick "Add python.exe to PATH".
  2. Save this file as  spider.py  in any folder (your Desktop is fine).
  3. Open that folder in File Explorer, click in the address bar, type  cmd
     and press Enter: a Command Prompt opens directly in that folder.
  4. Type   python spider.py   and press Enter   (if that fails:  py spider.py)
  5. Maximise the window (in Windows Terminal press F11) and turn off the lights.

ON A MAC
  1. Open the Terminal app (Cmd + Space, type "Terminal", Enter).
  2. Type  python3 --version  and press Enter. If macOS offers to install the
     "command line developer tools", accept (or install Python from python.org).
  3. Type  python3  followed by a space, drag spider.py from Finder into the
     Terminal window, and press Enter.
  4. Full screen: Ctrl + Cmd + F. Also works in iTerm2.

KEYS
  Q, Esc or Ctrl+C   quit (your terminal is restored)
  Space              play the next sequence right away

OPTIONS
  --demo        play every sequence back to back
  --scene NAME  start with one sequence: descent, eyes, swarm, glass, mother,
                cocoon or heartbeat
  --no-flash    no red screen flashes (use this if you are sensitive to flashing light)
  --fps 30      smoother, uses a little more CPU (default 20)
  --seed 7      replay the same "random" show
  e.g.   python3 spider.py --demo        or        python spider.py --scene eyes

THE SEQUENCES
  descent    it lowers itself from the ceiling on a thread, turning slowly, then drops
  eyes       lights out: dozens of red eyes open in the dark... then it is right there
  swarm      small spiders pour in from every edge and crawl over everything
  glass      it hits the screen so hard the glass cracks
  mother     something enormous crawls past in the background
  cocoon     a web is spun across the whole screen; it waits at the centre, then tears through
  heartbeat  it stares at you, a heartbeat speeds up, silence... then it jumps
  ...plus its own behaviour: crawling, pausing, twitching, rearing up, lunging,
  vanishing into the dark, and a climax every couple of minutes.

NOTES
  * Windows 10/11 (classic CMD or Windows Terminal), macOS Terminal/iTerm2, Linux.
  * Standard library only. Purely visual: it never reads or writes files, runs
    commands or touches other programs. Colours, cursor and the previous screen
    content are restored when it exits.
  * Contains occasional brief red flashes unless started with --no-flash.
"""

import argparse
import atexit
import math
import os
import random
import shutil
import signal
import sys
import time

# ----------------------------------------------------------------------------
# Palette (xterm-256): strictly black, greys/white and blood red
# ----------------------------------------------------------------------------
BLACK = 16
BLANK = BLACK | (BLACK << 8)        # a cell colour is stored as  fg | (bg << 8)
REDS = (52, 88, 124, 160, 196)      # dried blood ... fresh blood
WEB_OLD, WEB_NEW, WEB_DIM = 236, 240, 234
FLASH = BLACK | (88 << 8)           # black silhouettes on blood red

RAMP = ".:-=+*#%@"                  # body shading, dark to bright
GLITCH = "#$%&@!?/\\|<>[]{}=+*~^;:"
NOISE = ".,:;'`-_~"

WHISPERS = [
    "IT KNOWS YOU ARE HERE.",
    "DON'T MOVE. IT HUNTS WHAT MOVES.",
    "EIGHT EYES. ALL OF THEM ON YOU.",
    "THE WEB IS EVERYWHERE NOW.",
    "DID YOU FEEL SOMETHING ON YOUR NECK?",
    "IT WAS NEVER JUST ONE.",
    "IT HAS BEEN WATCHING YOU FOR A LONG TIME.",
    "SOMETHING IS CRAWLING BEHIND THE GLASS.",
    "IT IS HUNGRY.",
    "STAY VERY STILL.",
    "IT CAN HEAR YOU BREATHING.",
    "YOU LEFT THE DOOR OPEN.",
]
STRIKE_LINES = ["DON'T MOVE.", "TOO CLOSE.", "GOT YOU.", "LOOK AT ME."]
VANISH_LINES = ["WHERE DID IT GO?", "DON'T BLINK.", "IT'S STILL IN HERE.", "BEHIND YOU."]
INTRO_LINE = "something is in here with you..."
CLIMAX_LINE = "IT FOUND YOU."
OUTRO_LINE = "you escaped.  for now."

# ----------------------------------------------------------------------------
# The 3D scene. World units: x to the right (1 unit = 2 text columns), y along
# the floor towards the viewer, z up. The camera looks down at the floor.
# ----------------------------------------------------------------------------
PHI = math.radians(48.0)
SINP, COSP = math.sin(PHI), math.cos(PHI)
_l = (-0.55, 0.38, 0.75)
LIGHT = tuple(v / math.sqrt(sum(x * x for x in _l)) for v in _l)   # from the top-left, in front

# Spider anatomy in its own frame: x forward, y to its side, z up (unscaled units)
BODY = (  # part, centre, radii
    ("abdomen", (-5.4, 0.0, 2.75), (4.7, 3.4, 2.9)),
    ("ceph", (2.4, 0.0, 1.95), (2.9, 2.3, 1.55)),
    ("pedicel", (-0.75, 0.0, 2.1), (1.0, 0.75, 0.7)),
    ("spinneret", (-10.0, 0.0, 2.5), (0.8, 0.55, 0.55)),
)
PIVOT = (-0.5, 0.0, 2.0)            # the body rears up around this point
LEGS = [  # hip (x, |y|, z), resting foot on the floor (x, |y|), femur, tibia, metatarsus
    ((3.7, 1.0, 1.8), (11.5, 6.8), 6.2, 6.6, 2.3),
    ((3.0, 1.6, 1.8), (5.0, 9.4), 5.4, 5.8, 2.1),
    ((2.1, 1.85, 1.8), (-3.2, 9.4), 5.2, 5.6, 2.1),
    ((1.2, 1.6, 1.8), (-9.6, 7.2), 6.4, 6.9, 2.3),
]
STRIDE, LIFT = 2.0, 1.8
EYES = [  # position on the head (x, |y|), radius, brightness. The big front pair last.
    ((3.7, 1.45), 0.26, 0.62), ((4.75, 1.25), 0.26, 0.72),
    ((4.4, 0.72), 0.30, 0.85), ((5.0, 0.5), 0.40, 1.0),
]
CHELICERA = [(5.0, 0.55, 1.4), (5.85, 0.62, 0.85)]
FANG = [(5.85, 0.62, 0.85), (6.15, 0.42, 0.35), (5.9, 0.18, 0.04)]
PALP = [(4.9, 1.15, 1.35), (6.7, 1.75, 2.0), (7.7, 1.45, 0.25)]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def angle_diff(a, b):
    return (a - b + math.pi) % (2.0 * math.pi) - math.pi


def hash2(x, y):
    """Cheap repeatable noise in [0, 1] for two integers."""
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def grey(g, fade=1.0):
    """A grey from the 232-255 ramp, darkened towards black by `fade`."""
    return int(232 + (clamp(g, 232, 255) - 232) * fade)


def red(level):
    return REDS[int(clamp(level, 0.0, 0.999) * len(REDS))]


def proj(p):
    """World point -> (column, row, depth). Larger depth = closer to the viewer."""
    return p[0] * 2.0, p[1] * SINP - p[2] * COSP, p[1] * COSP + p[2] * SINP


def slope_char(dc, dr):
    """Pick - \\ | / for a line, given its direction in screen cells."""
    a = math.degrees(math.atan2(dr * 2.0, dc)) % 180.0  # rows are ~2x taller than columns
    if a < 22.0 or a >= 158.0:
        return "-"
    if a < 68.0:
        return "\\"
    if a < 112.0:
        return "|"
    return "/"


def joint_char(a, j, b):
    """An angular joint glyph pointing the way the joint j bends (screen points)."""
    dx = j[0] - (a[0] + b[0]) / 2.0
    dy = (j[1] - (a[1] + b[1]) / 2.0) * 2.0
    if abs(dy) >= abs(dx):
        return "^" if dy < 0 else "v"
    return "<" if dx < 0 else ">"


def gait(phi):
    """Foot offset along the body (-0.5..0.5) and lift (0..1) for a gait phase."""
    phi %= 1.0
    if phi < 0.5:                       # stance: the foot is planted, the body passes over it
        return 0.5 - 2.0 * phi, 0.0
    u = (phi - 0.5) * 2.0               # swing: the foot is lifted and brought forward
    return -0.5 + smooth(u), math.sin(math.pi * u)


def ik_up(a, b, l1, l2):
    """Two-bone inverse kinematics in 3D: the knee between a and b, bent upwards."""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1e-6
    e1 = (dx / d, dy / d, dz / d)
    d = clamp(d, abs(l1 - l2) + 1e-3, l1 + l2 - 1e-3)
    along = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
    h = math.sqrt(max(0.0, l1 * l1 - along * along))
    ux, uy, uz = -e1[2] * e1[0], -e1[2] * e1[1], 1.0 - e1[2] * e1[2]   # "up", made perpendicular
    n = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
    return (a[0] + e1[0] * along + ux / n * h,
            a[1] + e1[1] * along + uy / n * h,
            a[2] + e1[2] * along + uz / n * h)


def weave(W, H, cx, cy, R, angles, ends, ring, rings):
    """Rasterise an orb web: spokes first, then the spiral, each cell tagged with
    the moment (0..1) it gets spun. Coordinates: x in body units (2 columns), y in rows."""
    pts = {}

    def stroke(x0, y0, x1, y1, o0, o1):
        dc, dr = (x1 - x0) * 2.0, y1 - y0
        g = slope_char(dc, dr)
        n = int(max(abs(dc), abs(dr))) + 1
        for i in range(n + 1):
            f = i / n
            c = int(math.floor((x0 + (x1 - x0) * f) * 2.0 + 0.5))
            r = int(math.floor(y0 + (y1 - y0) * f + 0.5))
            if 0 <= c < W and 0 <= r < H:
                o = o0 + (o1 - o0) * f
                if (r, c) not in pts or pts[(r, c)][0] > o:
                    pts[(r, c)] = (o, g)

    n = len(angles)
    for i, (a, L) in enumerate(zip(angles, ends)):
        stroke(cx, cy, cx + math.cos(a) * L, cy + math.sin(a) * L, 0.01 * i, 0.38 + 0.01 * i)
    pairs = list(zip(range(n), list(range(1, n)) + ([0] if ring else [])))
    for j in range(1, rings + 1):
        f = (j / rings) ** 0.9
        base = 0.4 + 0.58 * (1.0 - j / rings)
        for i, (a, b) in enumerate(pairs):
            r1, r2 = min(f * R, ends[a]), min(f * R, ends[b])
            x1, y1 = cx + math.cos(angles[a]) * r1, cy + math.sin(angles[a]) * r1
            x2, y2 = cx + math.cos(angles[b]) * r2, cy + math.sin(angles[b]) * r2
            mx, my = lerp((x1 + x2) / 2, cx, 0.07), lerp((y1 + y2) / 2, cy, 0.07)   # threads sag
            o = base + 0.004 * i
            stroke(x1, y1, mx, my, o, o)
            stroke(mx, my, x2, y2, o, o)
    return sorted((o, r, c, g) for (r, c), (o, g) in pts.items())


# ----------------------------------------------------------------------------
# Character canvas
# ----------------------------------------------------------------------------
class Canvas:
    __slots__ = ("W", "H", "ch", "co")

    def __init__(self, W, H, ch=None, co=None):
        self.W, self.H = W, H
        self.ch = ch if ch is not None else [[" "] * W for _ in range(H)]
        self.co = co if co is not None else [[BLANK] * W for _ in range(H)]

    def copy(self):
        return Canvas(self.W, self.H, [r[:] for r in self.ch], [r[:] for r in self.co])

    def put(self, c, r, ch, fg, bg=BLACK):
        if 0 <= r < self.H and 0 <= c < self.W:
            self.ch[r][c] = ch
            self.co[r][c] = fg | (bg << 8)

    def line(self, x0, y0, x1, y1, fg, ch=None, step=1, bg=BLACK):
        dc, dr = x1 - x0, y1 - y0
        g = ch or slope_char(dc, dr)
        n = int(max(abs(dc), abs(dr))) + 1
        W, H, rows_ch, rows_co, col = self.W, self.H, self.ch, self.co, fg | (bg << 8)
        for i in range(0, n + 1, step):
            f = i / n
            c = int(math.floor(x0 + dc * f + 0.5))
            r = int(math.floor(y0 + dr * f + 0.5))
            if 0 <= r < H and 0 <= c < W:
                rows_ch[r][c] = g
                rows_co[r][c] = col


def zline(zb, W, H, p, q, fg, ch=None):
    """A 3D segment drawn into a depth buffer (nearest wins)."""
    c0, r0, d0 = proj(p)
    c1, r1, d1 = proj(q)
    dc, dr = c1 - c0, r1 - r0
    g = ch or slope_char(dc, dr)
    n = int(max(abs(dc), abs(dr))) + 1
    for i in range(n + 1):
        f = i / n
        c = int(math.floor(c0 + dc * f + 0.5))
        r = int(math.floor(r0 + dr * f + 0.5))
        if 0 <= r < H and 0 <= c < W:
            d = d0 + (d1 - d0) * f
            key = r * W + c
            old = zb.get(key)
            if old is None or d > old[0]:
                zb[key] = (d, g, fg)


# ----------------------------------------------------------------------------
# Terminal: VT mode, alternate screen, diff rendering, keys, clean restore
# ----------------------------------------------------------------------------
class Terminal:
    def __init__(self):
        self.out = sys.stdout
        self.prev = None
        self.restored = True
        self.win_mode = None
        self.unix_attr = None

    def start(self):
        self.restored = False
        if os.name == "nt":
            self._windows_vt(True)
        else:
            self._unix_keys(True)
        try:
            self.out.reconfigure(errors="replace")
        except Exception:
            pass
        # alternate screen, hidden cursor, black background
        self.write("\033[?1049h\033[?25l\033[0m\033[48;5;16m\033[2J\033[H")

    def restore(self):
        if self.restored:
            return
        self.restored = True
        try:
            self.write("\033[0m\033[2J\033[H\033[?25h\033[?1049l\033[0m")
        except Exception:
            pass
        if os.name == "nt":
            self._windows_vt(False)
        else:
            self._unix_keys(False)

    def write(self, s):
        self.out.write(s)
        self.out.flush()

    def size(self):
        cols, rows = shutil.get_terminal_size((100, 30))
        return max(10, cols), max(5, rows)

    def invalidate(self):
        self.prev = None
        self.write("\033[0m\033[48;5;16m\033[2J")

    def present(self, cv):
        """Write only the cells that changed since the previous frame."""
        out, prev, cur = [], self.prev, -1
        corner = (cv.H - 1) * cv.W + cv.W - 1      # writing there would scroll the screen
        for r in range(cv.H):
            rch, rco = cv.ch[r], cv.co[r]
            if prev is not None and rch == prev[0][r] and rco == prev[1][r]:
                continue
            pch = prev[0][r] if prev is not None else None
            pco = prev[1][r] if prev is not None else None
            last = -2
            for c in range(cv.W):
                ch, co = rch[c], rco[c]
                if pch is not None and ch == pch[c] and co == pco[c]:
                    continue
                if r * cv.W + c == corner:
                    continue
                if c != last + 1:
                    out.append("\033[%d;%dH" % (r + 1, c + 1))
                if co != cur:
                    out.append("\033[38;5;%d;48;5;%dm" % (co & 255, co >> 8))
                    cur = co
                out.append(ch)
                last = c
        if out:
            self.write("".join(out))
        self.prev = (cv.ch, cv.co)

    def key(self):
        try:
            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    k = msvcrt.getwch()
                    if k in ("\x00", "\xe0"):     # arrows, F-keys: ignore
                        msvcrt.getwch()
                        return ""
                    return k
            elif self.unix_attr is not None:
                import select
                if select.select([sys.stdin], [], [], 0)[0]:
                    return os.read(sys.stdin.fileno(), 64).decode("utf-8", "ignore")
        except Exception:
            pass
        return ""

    def _windows_vt(self, enable):
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = wintypes.HANDLE
            k32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            k32.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            h = k32.GetStdHandle(-11)
            if enable:
                mode = wintypes.DWORD()
                if k32.GetConsoleMode(h, ctypes.byref(mode)):
                    self.win_mode = mode.value
                    k32.SetConsoleMode(h, mode.value | 0x0001 | 0x0004)  # processed output + VT
            elif self.win_mode is not None:
                k32.SetConsoleMode(h, self.win_mode)
        except Exception:
            pass

    def _unix_keys(self, enable):
        try:
            import termios
            import tty
            if enable and sys.stdin.isatty():
                fd = sys.stdin.fileno()
                self.unix_attr = (fd, termios.tcgetattr(fd))
                tty.setcbreak(fd)                 # keys without Enter, Ctrl+C still works
            elif not enable and self.unix_attr is not None:
                termios.tcsetattr(self.unix_attr[0], termios.TCSADRAIN, self.unix_attr[1])
                self.unix_attr = None
        except Exception:
            self.unix_attr = None


# ----------------------------------------------------------------------------
# The spider
# ----------------------------------------------------------------------------
class Spider:
    def __init__(self, world=None, k=1.0):
        self.w = world
        self.k = world.scale if world else k
        self.wx, self.wy = world.center() if world else (0.0, 0.0)   # position on the floor
        self.heading = 0.0 if random.random() < 0.5 else math.pi
        self.tilt = 0.0          # extra sideways twist of the body
        self.pitch = 0.0         # the front of the body rears up
        self.rear = 0.0          # front legs raised in a threat display (0..1)
        self.zoom = 1.0
        self.phase = random.random()
        self.bob = 0.0
        self.alt = 0.0           # height above the floor (hanging on a thread)
        self.curl = 0.0          # legs folded against the body (0..1)
        self.fade = 0.0
        self.eyes = 0.0
        self.flicker = 1.0
        self.blink_until = 0.0
        self.jx = self.jy = 0.0
        self.leg_jit = [[0.0, 0.0, 0.0] for _ in range(8)]
        self.speed_mult = 1.0
        self.target = None
        self.last_lunge = 0.0
        self.last_vanish = 0.0
        self.last_rear = 0.0
        self.drips = []
        self.t = 0.0
        self.state, self.st, self.data = "emerge", 0.0, {"slow": True}

    # ---- geometry ------------------------------------------------------------
    def frame(self):
        th = self.heading + self.tilt
        return (self.k * self.zoom, math.cos(th), math.sin(th), math.cos(self.pitch),
                math.sin(self.pitch), self.wx + self.jx, self.wy + self.jy, self.bob, self.alt)

    @staticmethod
    def to_world(p, T):
        """A point of the body (its own frame, unscaled) -> world."""
        k, ct, st, cp, sp, gx, gy, bob, alt = T
        px, pz = p[0] - PIVOT[0], p[2] - PIVOT[2]
        x = PIVOT[0] + px * cp - pz * sp
        z = PIVOT[2] + px * sp + pz * cp + bob + alt
        return gx + (x * ct - p[1] * st) * k, gy + (x * st + p[1] * ct) * k, z * k

    @staticmethod
    def on_floor(fx, fy, fz, T):
        k, ct, st, _, _, gx, gy, _, alt = T
        return gx + (fx * ct - fy * st) * k, gy + (fx * st + fy * ct) * k, (fz + alt) * k

    def unit_map(self, T, centre, radii):
        """Affine map: world point -> coordinates on the unit sphere of one body part."""
        k, ct, st, cp, sp, gx, gy, bob, alt = T

        def inv(P):
            wx, wy, wz = (P[0] - gx) / k, (P[1] - gy) / k, P[2] / k - bob - alt
            x2, y = wx * ct + wy * st, wy * ct - wx * st
            px, pz = x2 - PIVOT[0], wz - PIVOT[2]
            x, z = PIVOT[0] + px * cp + pz * sp, PIVOT[2] - px * sp + pz * cp
            return ((x - centre[0]) / radii[0], (y - centre[1]) / radii[1], (z - centre[2]) / radii[2])

        o = inv((0.0, 0.0, 0.0))
        axes = [tuple(a - b for a, b in zip(inv(e), o)) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        return o, axes[0], axes[1], axes[2]

    def leg_chains(self, T):
        k = T[0]
        chains = []
        for i, ((hx, hy, hz), (rx, ry), l1, l2, l3) in enumerate(LEGS):
            for s in (-1, 1):
                right = 1 if s > 0 else 0
                off, lift = gait(self.phase + 0.5 * ((i + right) % 2))   # alternating tetrapod gait
                jx, jy, jz = self.leg_jit[2 * i + right]
                fx, fy, fz = rx + off * STRIDE + jx, s * (ry + jy), lift * LIFT + jz
                if self.curl > 0.0:          # legs folded against the body
                    c = self.curl
                    fx = lerp(fx, hx + (1.6 if i < 2 else -1.6), 0.55 * c)
                    fy = s * lerp(abs(fy), hy + 2.6, 0.6 * c)
                    fz = lerp(fz, hz + 1.4, c)
                up = self.rear * (1.0 if i == 0 else 0.45 if i == 1 else 0.0)
                if up > 0.0:                 # threat display: front legs rise and claw the air
                    fx += 2.8 * up
                    fy *= 1.0 - 0.22 * up
                    fz += up * (7.0 + 0.9 * math.sin(self.t * 7.0 + i * 2.0 + s))
                hip = self.to_world((hx, s * hy, hz), T)
                foot = self.on_floor(fx, fy, max(0.0, fz), T)
                hdx, hdy = foot[0] - hip[0], foot[1] - hip[1]
                hd = math.hypot(hdx, hdy) or 1.0
                # the ankle sits above the claw, slightly inwards
                ankle = (foot[0] - hdx / hd * 0.35 * l3 * k, foot[1] - hdy / hd * 0.35 * l3 * k,
                         foot[2] + 0.94 * l3 * k)
                knee = ik_up(hip, ankle, l1 * k, l2 * k)
                chains.append((hip, knee, ankle, foot, lift > 0.25 or up > 0.3))
        return chains

    def extent(self):
        """Screen extent (row/column offsets) around the floor point, over a few poses."""
        saved = (self.heading, self.phase, self.wx, self.wy, self.zoom, self.pitch, self.rear)
        rows, cols = [], []
        for heading in (0.0, math.pi / 4, math.pi / 2):
            for phase in (0.0, 0.25):
                self.heading, self.phase, self.wx, self.wy = heading, phase, 0.0, 0.0
                self.zoom, self.pitch, self.rear = 1.0, 0.0, 0.0
                T = self.frame()
                pts = [p for chain in self.leg_chains(T) for p in chain[:4]]
                pts += [self.to_world((x, y, z), T) for x in (-10.8, 5.3) for y in (-3.4, 3.4) for z in (0, 5.7)]
                for p in pts:
                    c, r, _ = proj(p)
                    rows.append(r)
                    cols.append(c)
        self.heading, self.phase, self.wx, self.wy, self.zoom, self.pitch, self.rear = saved
        return min(rows), max(rows), min(cols), max(cols)

    # ---- behaviour -------------------------------------------------------
    def go(self, state, **data):
        self.state, self.st, self.data = state, 0.0, data

    def pick_target(self):
        x0, x1, y0, y1 = self.w.bounds()
        mid = (x0 + x1) / 2.0
        if self.wx < mid:
            tx = random.uniform(lerp(mid, x1, 0.55), x1)
        else:
            tx = random.uniform(x0, lerp(x0, mid, 0.45))
        self.target = (tx, random.uniform(y0, y1))

    def teleport(self):
        x0, x1, y0, y1 = self.w.bounds()
        self.wx, self.wy = random.uniform(x0, x1), random.uniform(y0, y1)
        self.heading = random.choice((0.0, math.pi)) + random.uniform(-0.4, 0.4)
        self.target = None
        self.tilt = self.pitch = self.rear = self.alt = self.curl = 0.0

    def twitch_legs(self, amount):
        for idx in random.sample(range(8), random.randint(2, 4)):
            self.leg_jit[idx] = [random.uniform(-amount, amount), random.uniform(-amount, amount) * 0.6,
                                 random.uniform(0.0, amount * 1.4)]

    def interrupt(self, t, I):
        choices = [("pause", 0.5), ("twitch", 0.15 + 0.25 * I), ("tilt", 0.15), ("dash", 0.3 * I)]
        if t - self.last_rear > 12.0:
            choices.append(("rear", 0.12 + 0.12 * I))
        if t - self.last_lunge > 9.0 - 4.0 * I:
            choices.append(("lunge", 0.05 + 0.3 * I))
        if t - self.last_vanish > 17.0 - 6.0 * I:
            choices.append(("vanish", 0.06 + 0.1 * I))
        total = sum(w for _, w in choices)
        pick = random.uniform(0.0, total)
        for name, w in choices:
            pick -= w
            if pick <= 0:
                break
        if name == "lunge":
            self.last_lunge = t
        elif name == "vanish":
            self.last_vanish = t
        elif name == "rear":
            self.last_rear = t
        self.go(name)

    def update(self, dt, t, I):
        self.t = t
        self.st += dt
        # eyes: nervous flicker, rare blinks
        if random.random() < (0.9 + 2.5 * I) * dt:
            self.flicker = random.uniform(0.2, 0.8)
        else:
            self.flicker = min(1.0, self.flicker + dt * 5.0)
        if random.random() < 0.05 * dt:
            self.blink_until = t + 0.13
        if t < self.blink_until:
            self.flicker = 0.0
        # twitches fade out, jitter settles
        settle = max(0.0, 1.0 - dt * 9.0)
        for j in self.leg_jit:
            j[0] *= settle
            j[1] *= settle
            j[2] *= settle
        self.jx *= settle
        self.jy *= settle
        getattr(self, "_" + self.state)(dt, t, I)
        self.bob = 0.12 * math.sin(self.phase * 4.0 * math.pi)
        self._drips(dt, t)

    def _move_towards_target(self, dt, I):
        if self.target is None:
            self.pick_target()
        tx, ty = self.target
        dx, dy = tx - self.wx, ty - self.wy
        dist = math.hypot(dx, dy)
        if dist < 0.6 * self.k:
            self.target = None
            return "arrived"
        diff = angle_diff(math.atan2(dy, dx), self.heading)
        if abs(diff) > 1.75:
            return "turn"
        turn = clamp(diff, -1.4 * dt, 1.4 * dt)
        self.heading += turn
        speed = (0.9 + 2.8 * I) * self.k * self.speed_mult
        step = min(dist, speed * dt)
        self.wx += math.cos(self.heading) * step
        self.wy += math.sin(self.heading) * step
        self.phase += step / (2.0 * STRIDE * self.k) + abs(turn) * 0.4
        return None

    def _settle_pose(self, dt):
        f = min(1.0, dt * 4.0)
        self.pitch += (0.0 - self.pitch) * f
        self.rear += (0.0 - self.rear) * f

    def _held(self, dt, t, I):
        pass                                     # a scene is pulling the strings

    def _emerge(self, dt, t, I):
        # it faces you: the eyes open in the darkness first, blink, then the body appears
        if "faced" not in self.data:
            self.data["faced"] = True
            self.heading = math.pi / 2.0 + random.uniform(-0.35, 0.35)
        e0, b0 = (2.6, 4.8) if self.data.get("slow") else (0.6, 1.8)
        self.eyes = smooth((self.st - e0) / 0.9)
        if e0 + 1.1 < self.st < e0 + 1.25 or e0 + 1.6 < self.st < e0 + 1.7:
            self.flicker = 0.0
        self.fade = smooth((self.st - b0) / 1.6)
        if self.st > b0 + 1.8:
            self.go("crawl")

    def _crawl(self, dt, t, I):
        self._settle_pose(dt)
        result = self._move_towards_target(dt, I)
        if result == "turn":
            self.go("turn")
        elif result == "arrived":
            self.go("pause" if random.random() < 0.75 else "crawl")
        elif random.random() < (0.16 + 0.3 * I) * dt:
            self.interrupt(t, I)

    def _dash(self, dt, t, I):
        # a sudden burst of speed ... then it freezes
        self.speed_mult = 2.8
        result = self._move_towards_target(dt, I)
        if result or self.st > self.data.setdefault("dur", random.uniform(0.45, 0.9)):
            self.speed_mult = 1.0
            self.go("pause", dur=random.uniform(0.35, 1.1))

    def _turn(self, dt, t, I):
        self._settle_pose(dt)
        if self.target is None:
            self.pick_target()
        diff = angle_diff(math.atan2(self.target[1] - self.wy, self.target[0] - self.wx), self.heading)
        rate = 1.3 + 1.6 * I
        turn = clamp(diff, -rate * dt, rate * dt)
        self.heading += turn
        self.phase += abs(turn) * 0.9
        if abs(diff) < 0.08:
            self.go("crawl")

    def _pause(self, dt, t, I):
        self._settle_pose(dt)
        dur = self.data.setdefault("dur", random.uniform(1.0, 3.4) * (1.2 - 0.65 * I) + 0.25)
        if I > 0.3:                              # it trembles while it waits
            a = 0.25 * I
            self.jx, self.jy = random.uniform(-a, a), random.uniform(-a, a) * 0.5
        if random.random() < (0.4 + 1.2 * I) * dt:
            self.twitch_legs(0.7)
        if self.st > dur:
            self.go("crawl")

    def _twitch(self, dt, t, I):
        dur = self.data.setdefault("dur", random.uniform(0.25, 0.6))
        if random.random() < 0.6:
            self.twitch_legs(1.4)
        self.heading += random.uniform(-0.07, 0.07)
        self.jx, self.jy = random.uniform(-0.35, 0.35), random.uniform(-0.2, 0.2)
        if self.st > dur:
            self.go("pause", dur=random.uniform(0.3, 1.2))

    def _tilt(self, dt, t, I):
        ang = self.data.setdefault("ang", random.choice((-1, 1)) * random.uniform(0.18, 0.35))
        st = self.st
        if st < 0.35:
            self.tilt = ang * smooth(st / 0.35)
        elif st < 0.95:
            self.tilt = ang
        elif st < 1.4:
            self.tilt = ang * (1.0 - smooth((st - 0.95) / 0.45))
        else:
            self.heading += self.tilt
            self.tilt = 0.0
            self.go("crawl")
        self.phase += dt * 0.2

    def _rear(self, dt, t, I):
        # it rears up, front legs raised, fangs bared
        hold = self.data.setdefault("hold", random.uniform(1.0, 2.2))
        st = self.st
        if st < 0.55:
            p = smooth(st / 0.55)
        elif st < 0.55 + hold:
            p = 1.0
            if random.random() < 1.5 * dt:
                self.twitch_legs(0.6)
        else:
            p = 1.0 - smooth((st - 0.55 - hold) / 0.6)
            if p <= 0.0:
                self.go("pause", dur=random.uniform(0.3, 1.0))
        self.pitch, self.rear = 0.32 * p, p
        self.flicker = max(self.flicker, 0.6 * p)

    def _lunge(self, dt, t, I):
        d = self.data
        climax = bool(d.get("climax"))
        if "ox" not in d:
            cx, cy = self.w.center()
            d.update(ox=self.wx, oy=self.wy, oh=self.heading, hit=False,
                     z=(2.5 if climax else 1.7 + 0.5 * I),
                     face=self.heading + angle_diff(math.pi / 2.0, self.heading),
                     sx=lerp(self.wx, cx, 0.8), sy=lerp(self.wy, cy, 0.8) + 1.5 * self.k)
        st = self.st
        if st < 0.45:                                  # it turns to face you and rears up
            p = smooth(st / 0.45)
            self.heading = lerp(d["oh"], d["face"], p)
            self.pitch, self.rear = 0.25 * p, 0.7 * p
            self.phase += dt * 1.5
        elif st < 0.75:                                # draws back, eyes burning
            p = smooth((st - 0.45) / 0.3)
            self.zoom = 1.0 - 0.07 * p
            self.wy = d["oy"] - 1.2 * self.k * p
            self.jx = random.uniform(-0.12, 0.12) * p
            self.flicker = 1.0
        elif st < 0.93:                                # strike
            p = ease_out((st - 0.75) / 0.18)
            self.zoom = lerp(0.93, d["z"], p)
            self.wx = lerp(d["ox"], d["sx"], p)
            self.wy = lerp(d["oy"] - 1.2 * self.k, d["sy"], p)
            self.pitch, self.rear = lerp(0.25, 0.42, p), lerp(0.7, 1.0, p)
            self.flicker = 1.0
            if not d["hit"]:
                d["hit"] = True
                head = proj(self.to_world((5.4, 0.0, 1.9), self.frame()))
                self.w.on_strike(t, climax, d.get("kind"), head)
        elif st < (2.2 if climax else 1.45):           # it holds, inches from the glass
            self.flicker = max(self.flicker, 0.7)
            self.jx, self.jy = random.uniform(-0.25, 0.25), random.uniform(-0.15, 0.15)
            if random.random() < 0.3:
                self.twitch_legs(0.9)
        elif climax:
            self.go("blackout")
        elif st < 2.25:                                # and slowly withdraws
            p = smooth((st - 1.45) / 0.8)
            self.zoom = lerp(d["z"], 1.0, p)
            self.wx, self.wy = lerp(d["sx"], d["ox"], p), lerp(d["sy"], d["oy"], p)
            self.pitch, self.rear = 0.42 * (1 - p), 1.0 - p
            self.phase -= dt * 0.8
        else:
            self.zoom = 1.0
            self.go("pause", dur=random.uniform(0.6, 1.4))

    def _vanish(self, dt, t, I):
        d, st = self.data, self.st
        wait = d.setdefault("wait", random.uniform(0.6, 1.8))
        self._settle_pose(dt)
        self.w.dark_target = 0.6
        if st < 1.0:                                   # the body sinks into the dark...
            self.fade = 1.0 - smooth(st)
            if not d.get("said") and random.random() < 0.5:
                self.w.say(random.choice(VANISH_LINES), t + 0.6)
            d["said"] = True
        elif st < 2.0:                                 # ...only the eyes remain
            self.fade = 0.0
            if 1.3 < st < 1.42 or 1.62 < st < 1.72:
                self.flicker = 0.0
        elif st < 2.4:
            self.eyes = 1.0 - smooth((st - 2.0) / 0.4)
        elif st < 2.4 + wait:
            self.eyes = 0.0
            if not d.get("moved"):
                d["moved"] = True
                self.teleport()
        elif st < 3.1 + wait:                          # eyes open somewhere else
            self.eyes = smooth((st - 2.4 - wait) / 0.6)
        elif st < 4.2 + wait:
            self.fade = smooth((st - 3.1 - wait) / 1.1)
            self.w.dark_target = 0.0
        else:
            self.fade, self.eyes = 1.0, 1.0
            self.go("crawl")

    def _blackout(self, dt, t, I):
        st = self.st
        self.zoom, self.pitch, self.rear = 1.0, 0.0, 0.0
        self.fade = 0.0
        self.eyes = 0.0 if st > 0.15 else self.eyes
        self.w.dark_target = 1.0
        if st > 2.8:
            self.w.reset_tension(t)
            self.teleport()
            self.w.dark_target = 0.0
            self.go("emerge")

    def _drips(self, dt, t):
        # venom gathers on the fangs and falls
        visible = self.fade > 0.6 and self.zoom < 1.2 and self.rear < 0.3
        rate = 0.5 if self.state == "pause" else 0.15
        if visible and random.random() < rate * dt:
            c, r, _ = proj(self.to_world((FANG[-1][0], random.choice((-1, 1)) * FANG[-1][1], FANG[-1][2]),
                                         self.frame()))
            self.drips.append([c, r, t])
        for drop in self.drips:
            drop[1] += dt * 5.0
        self.drips = [d for d in self.drips if t - d[2] < 0.8]

    # ---- drawing ---------------------------------------------------------
    def render(self, cv, t):
        fade = self.fade
        eyes = self.eyes * self.flicker
        W, H = cv.W, cv.H
        for x, y, t0 in self.drips:
            age = t - t0
            cv.put(int(x), int(y), "." if age < 0.45 else ",", red(0.85 - age * 0.9))
        if fade < 0.04 and eyes < 0.04:
            return
        T = self.frame()
        k = T[0]
        zb = {}
        face = []
        if fade >= 0.04:
            chains = self.leg_chains(T)
            if fade > 0.45 and self.alt < 2.5:
                self.shadows(cv, T, chains, fade)
            centre = proj(self.to_world((0.0, 0.0, 2.0), T))[2]
            for hip, knee, ankle, foot, lifted in chains:
                near = int(clamp((proj(knee)[2] - centre) / (5.0 * k), -1.0, 1.0) * 4)   # depth cue
                lift = 2 if lifted else 0
                zline(zb, W, H, hip, knee, grey(250 + near + lift, fade))
                zline(zb, W, H, knee, ankle, grey(248 + near + lift, fade))
                zline(zb, W, H, ankle, foot, grey(243 + near, fade))
                ph, pk, pa, pf = proj(hip), proj(knee), proj(ankle), proj(foot)
                for p, g, shade in ((pk, joint_char(ph, pk, pa), 255), (pa, joint_char(pk, pa, pf), 250)):
                    c, r = int(p[0] + 0.5), int(p[1] + 0.5)
                    if 0 <= c < W and 0 <= r < H:
                        old = zb.get(r * W + c)
                        if old is None or p[2] + 0.3 >= old[0]:
                            zb[r * W + c] = (p[2] + 0.3, g, grey(shade + near, fade))
            face = self.raster_body(zb, W, H, T, fade)
            for s in (-1, 1):                          # pedipalps, chelicerae, fangs
                p = [self.to_world((x, s * y, z), T) for x, y, z in PALP]
                zline(zb, W, H, p[0], p[1], grey(247, fade))
                zline(zb, W, H, p[1], p[2], grey(244, fade))
                p = [self.to_world((x, s * y, z), T) for x, y, z in CHELICERA]
                zline(zb, W, H, p[0], p[1], grey(253, fade))
                p = [self.to_world((x, s * y, z), T) for x, y, z in FANG]
                zline(zb, W, H, p[0], p[1], red(0.75 * fade + 0.1))
                zline(zb, W, H, p[1], p[2], red(0.95 * fade + 0.04))
        # the eyes: on the head's surface, visible only if nothing is in front of them
        if eyes >= 0.04:
            _, ccy, ccz = BODY[1][1]
            ccx = BODY[1][1][0]
            rx, ry, rz = BODY[1][2]
            glow = []
            for (ex, ey), rad, power in EYES:
                for s in (-1, 1):
                    q = 1.0 - ((ex - ccx) / rx) ** 2 - (ey / ry) ** 2
                    ez = ccz + rz * math.sqrt(max(0.0, q)) + 0.06
                    c, r, d = proj(self.to_world((ex, s * ey, ez), T))
                    key = int(r) * W + int(c)
                    old = zb.get(key)
                    if old is not None and d < old[0] - 0.45 * k:
                        continue                       # hidden behind the head or a leg
                    lvl = eyes * power
                    if power >= 1.0:
                        glow.append((c, r))
                    if rad * k >= 0.7:                 # close up: real round eyes
                        erx, ery = rad * k * 2.6, rad * k * 1.3
                        for rr in range(int(r - ery) - 1, int(r + ery) + 2):
                            for cc in range(int(c - erx) - 1, int(c + erx) + 2):
                                dd = ((cc + 0.5 - c) / erx) ** 2 + ((rr + 0.5 - r) / ery) ** 2
                                if dd <= 1.0 and 0 <= cc < W and 0 <= rr < H:
                                    g = "@" if dd < 0.3 else "O" if dd < 0.7 else "o"
                                    zb[rr * W + cc] = (d + 1.0, g, red(lvl * (1.0 - 0.3 * dd)), 0)
                    elif 0 <= int(c) < W and 0 <= int(r) < H:
                        big = power >= 1.0
                        g = ("O" if k >= 1.2 else "o") if big else ("o" if k >= 1.2 else ".")
                        zb[key] = (d + 1.0, g, red(lvl), 52 if big and lvl > 0.8 else BLACK)
            if glow and fade >= 0.04:                  # red light spilling over the face
                tint = red(eyes * 0.42)
                lim = (1.1 * k) ** 2
                for key in face:
                    cell = zb.get(key)
                    if cell is None or len(cell) > 3:
                        continue
                    r, c = divmod(key, W)
                    for gc, gr in glow:
                        if ((c - gc) * 0.5) ** 2 + (r - gr) ** 2 < lim:
                            zb[key] = (cell[0], cell[1], tint)
                            break
        rows_ch, rows_co = cv.ch, cv.co
        for key, cell in zb.items():
            r, c = divmod(key, W)
            rows_ch[r][c] = cell[1]
            rows_co[r][c] = cell[2] | ((cell[3] if len(cell) > 3 else BLACK) << 8)

    def shadows(self, cv, T, chains, fade):
        """Shadows on the floor, cast away from the light."""
        k, ct, st, _, _, gx, gy, _, _ = T
        sh = grey(234, fade)
        sx, sy = -LIGHT[0] / LIGHT[2], -LIGHT[1] / LIGHT[2]
        h = 2.4 * k
        for _, centre, radii in BODY[:2]:
            fx = gx + (centre[0] * ct - centre[1] * st) * k + sx * h
            fy = gy + (centre[0] * st + centre[1] * ct) * k + sy * h
            rxw, ryw = radii[0] * k, radii[1] * k
            R = max(rxw, ryw)
            for r in range(max(0, int((fy - R) * SINP)), min(cv.H, int((fy + R) * SINP) + 2)):
                Y = (r + 0.5) / SINP - fy
                for c in range(max(0, int((fx - R) * 2)), min(cv.W, int((fx + R) * 2) + 2)):
                    X = (c + 0.5) * 0.5 - fx
                    lx, ly = X * ct + Y * st, Y * ct - X * st
                    if (lx / rxw) ** 2 + (ly / ryw) ** 2 <= 1.0:
                        cv.put(c, r, ".", sh)
        for chain in chains:
            pts = [proj((p[0] + sx * p[2], p[1] + sy * p[2], 0.0)) for p in chain[:4]]
            for a, b in zip(pts, pts[1:]):
                cv.line(a[0], a[1], b[0], b[1], sh, ".", 2)

    def raster_body(self, zb, W, H, T, fade):
        """Ray-trace the body (four lit ellipsoids) into the depth buffer."""
        k, ct, st, cp, sp = T[:5]
        LX, LY, LZ = LIGHT
        bristle = grey(242, fade)
        face = []
        for part, centre, radii in BODY:
            o, ex, ey, ez = self.unit_map(T, centre, radii)
            qv = [COSP * ey[i] + SINP * ez[i] for i in range(3)]        # the viewing ray
            qr = [SINP * ey[i] - COSP * ez[i] for i in range(3)]        # one screen row down
            A = qv[0] * qv[0] + qv[1] * qv[1] + qv[2] * qv[2]
            box = [proj(self.to_world((centre[0] + a * radii[0] * 1.2, centre[1] + b * radii[1] * 1.2,
                                       centre[2] + c * radii[2] * 1.2), T))
                   for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]
            c0 = max(0, int(min(p[0] for p in box)))
            c1 = min(W - 1, int(max(p[0] for p in box)) + 1)
            r0 = max(0, int(min(p[1] for p in box)))
            r1 = min(H - 1, int(max(p[1] for p in box)) + 1)
            hairy = part == "abdomen"
            rx_, ry_, rz_ = radii
            for r in range(r0, r1 + 1):
                fr = r + 0.5
                bx, by, bz = o[0] + fr * qr[0], o[1] + fr * qr[1], o[2] + fr * qr[2]
                for c in range(c0, c1 + 1):
                    fc = (c + 0.5) * 0.5
                    x0, y0, z0 = bx + fc * ex[0], by + fc * ex[1], bz + fc * ex[2]
                    qb = x0 * qv[0] + y0 * qv[1] + z0 * qv[2]
                    qq = x0 * x0 + y0 * y0 + z0 * z0
                    disc = qb * qb - A * (qq - 1.0)
                    key = r * W + c
                    if disc < 0.0:
                        # just outside the silhouette: coarse bristles
                        if hairy and qq - qb * qb / A < 1.3 and hash2(c * 7 + int(o[0] * 13), r * 5) < 0.2:
                            tt = -qb / A
                            old = zb.get(key)
                            if old is None or tt > old[0]:
                                zb[key] = (tt, "'" if (r % 2) else ",", bristle)
                        continue
                    tt = (-qb + math.sqrt(disc)) / A
                    old = zb.get(key)
                    if old is not None and old[0] >= tt:
                        continue
                    hx, hy, hz = x0 + tt * qv[0], y0 + tt * qv[1], z0 + tt * qv[2]
                    nx, ny, nz = hx / rx_, hy / ry_, hz / rz_
                    x2, z2 = nx * cp - nz * sp, nx * sp + nz * cp
                    wnx, wny = x2 * ct - ny * st, x2 * st + ny * ct
                    b = (wnx * LX + wny * LY + z2 * LZ) / (math.sqrt(wnx * wnx + wny * wny + z2 * z2) or 1.0)
                    b = 0.1 + 0.9 * clamp(b, 0.0, 1.0)
                    tex = hash2(int(hx * 11.0) + 60, int(hy * 11.0 + hz * 7.0) + 60)
                    if part == "abdomen":             # segment rings, dorsal chevrons, hair
                        if (hx + 0.25 * hy * hy) * 2.8 % 1.0 < 0.13:
                            b *= 0.42
                        if hz > 0.15 and abs(hy) < 0.34 * (1.0 - hx * hx) and \
                                (hx * 3.2 - abs(hy) * 2.6) % 1.0 < 0.42:
                            b *= 0.55
                        b *= 0.8 + 0.32 * tex
                    elif part == "ceph":              # central pit, radial grooves, dark face
                        if hz > 0.9:
                            b *= 0.5
                        elif hz > 0.35 and abs(math.sin(math.atan2(hy, hx) * 4.0)) < 0.22:
                            b *= 0.72
                        if hx > 0.55:
                            b *= 0.7
                        b *= 0.88 + 0.2 * tex
                        face.append(key)
                    else:
                        b *= 0.6
                    b = clamp(b, 0.0, 1.0)
                    g = grey(236 + int(b * 19.0), fade)
                    if g >= 234:
                        zb[key] = (tt, "@" if b > 0.9 else RAMP[int(b * 8.99)], g)
        return face


# ----------------------------------------------------------------------------
# Little spiders in the background
# ----------------------------------------------------------------------------
SMALL = ["/\\(oo)/\\", "\\/(oo)\\/"]


class Critter:
    def __init__(self, world):
        W, H = world.W, world.H
        self.alive = True
        self.wait = 0.0
        if random.random() < 0.45:                     # comes down from the ceiling on a thread
            self.mode = "drop"
            self.x = random.randint(2, max(3, W - 10))
            self.y = -1.0
            self.depth = random.uniform(H * 0.15, H * 0.55)
            self.vy = random.uniform(3.0, 6.0)
            self.hang = random.uniform(1.0, 4.0)
        else:                                           # scuttles along the top or bottom
            self.mode = "walk"
            self.dir = random.choice((-1, 1))
            self.x = -9.0 if self.dir > 0 else W + 1.0
            band = random.random() < 0.5
            self.y = random.randint(1, max(1, H // 5)) if band else random.randint(H - H // 5 - 1, H - 2)
            self.vx = self.dir * random.uniform(3.0, 8.0)
        self.W, self.H = W, H

    def update(self, dt):
        if self.mode == "drop":
            if self.vy > 0 and self.y >= self.depth:
                self.hang -= dt
                if self.hang <= 0:
                    self.vy = -random.uniform(4.0, 8.0)
                return
            self.y += self.vy * dt
            if self.y < -2:
                self.alive = False
        else:
            if self.wait > 0:
                self.wait -= dt
                return
            if random.random() < 0.35 * dt:            # it freezes... then carries on
                self.wait = random.uniform(0.4, 1.6)
            self.x += self.vx * dt
            if self.x < -12 or self.x > self.W + 12:
                self.alive = False

    def draw(self, cv, t):
        moving = (self.mode == "walk" and self.wait <= 0) or (self.mode == "drop" and self.y < self.depth)
        sprite = SMALL[int(t * 8) % 2] if moving else SMALL[0]
        x, y = int(self.x), int(self.y)
        if self.mode == "drop":
            for r in range(0, y):
                cv.put(x + 4, r, "|", 237)
        for i, ch in enumerate(sprite):
            cv.put(x + i, y, ch, 88 if ch == "o" else 243 if ch in "()" else 240)


# ----------------------------------------------------------------------------
# Ominous text, typed one letter at a time
# ----------------------------------------------------------------------------
class Message:
    def __init__(self, text, t0, W, H, row=None, speed=None, hold=2.8, color=196, spaced=None):
        if spaced is None:
            spaced = len(text) * 2 + 6 < W and text.isupper()
        self.text = (" ".join(text) if spaced else text)[: max(1, W - 2)]
        self.t0 = t0
        self.speed = speed or (24.0 if spaced else 14.0)
        self.hold = hold
        self.color = color
        self.row = row if row is not None else random.choice((H - 3, 1, H - 4, 2))
        self.col = max(1, (W - len(self.text)) // 2)
        self.typed = t0 + len(self.text) / self.speed
        self.drop = [random.random() for _ in self.text]

    def done(self, t):
        return t > self.typed + self.hold + 1.4

    def draw(self, cv, t, I):
        if t < self.t0:
            return
        n = min(len(self.text), int((t - self.t0) * self.speed))
        gone = (t - self.typed - self.hold) / 1.4
        for i in range(n):
            ch = self.text[i]
            if ch == " ":
                continue
            col = self.color
            if gone > 0:                                # the letters bleed away
                if self.drop[i] < gone:
                    continue
                col = red(0.75 - gone * 0.7)
            elif random.random() < 0.01 + 0.03 * I:     # and glitch while they are there
                ch = random.choice(GLITCH)
                col = 231 if random.random() < 0.35 else 160
            cv.put(self.col + i, self.row, ch, col)
        if n < len(self.text) and int(t * 8) % 2 == 0:
            cv.put(self.col + n, self.row, "_", self.color)



# ----------------------------------------------------------------------------
# Cinematic sequences. Each one takes control of the spider for a while.
# ----------------------------------------------------------------------------
class Scene:
    def __init__(self, world, t):
        self.w, self.t0, self.sp = world, t, world.spider

    def update(self, t, dt):
        """Advance the scene; return False when it is over."""
        return False

    def back(self, cv, t):
        """Drawn behind the spider."""

    def front(self, cv, t):
        """Drawn in front of the spider."""

    def sink(self, st, dur=0.8):
        """The spider melts into the dark at the start of a scene."""
        if not hasattr(self, "f0"):
            self.f0, self.e0 = self.sp.fade, self.sp.eyes
        p = smooth(st / dur)
        self.sp.fade, self.sp.eyes = self.f0 * (1.0 - p), self.e0 * (1.0 - p)


class Descent(Scene):
    """It lowers itself from the ceiling on a thread, slowly turning, then drops."""

    def __init__(self, world, t):
        super().__init__(world, t)
        self.sp.go("held")
        self.anchor = self.cut = None
        world.dark_target = 0.3
        world.say(random.choice(("LOOK UP.", "IT'S RIGHT ABOVE YOU.", "SOMETHING IS COMING DOWN.")), t + 1.2)

    def update(self, t, dt):
        sp, w, st = self.sp, self.w, t - self.t0
        if st < 0.8:
            self.sink(st)
            return True
        k = sp.k
        if self.anchor is None:                    # high above the screen, legs folded
            x0, x1, y0, y1 = w.bounds()
            sp.wx = random.uniform(lerp(x0, x1, 0.15), lerp(x0, x1, 0.85))
            sp.wy = (y0 + y1) / 2.0
            sp.zoom, sp.pitch, sp.rear, sp.tilt = 1.0, 0.0, 0.0, 0.0
            sp.heading = random.uniform(0.0, 2.0 * math.pi)
            self.top = (sp.wy * SINP + 16.0 * k) / (k * COSP)
            self.hang = max(0.0, (sp.wy * SINP - w.H * 0.42) / (k * COSP) - 2.5)
            self.anchor = sp.wx
            sp.curl, sp.fade, sp.eyes, sp.alt = 1.0, 1.0, 1.0, self.top
        if st < 6.0:                               # down it comes, turning on its thread
            p = (st - 0.8) / 5.2
            sp.alt = lerp(self.top, self.hang, ease_out(p))
            sp.heading += 0.55 * dt * (1.0 - 0.6 * p)
            sp.wx = self.anchor + 0.6 * k * math.sin(st * 1.3) * (1.0 - p)
        elif st < 7.8:                             # it hangs there, legs twitching
            sp.alt = self.hang + 0.12 * math.sin(st * 2.2)
            sp.heading += 0.12 * dt
            if random.random() < 2.0 * dt:
                sp.twitch_legs(0.6)
        elif st < 8.15:                            # and drops
            p = (st - 7.8) / 0.35
            sp.alt = self.hang * (1.0 - p * p)
        else:
            if self.cut is None:
                self.cut = t
                self.cut_row = proj(sp.to_world((-6.5, 0.0, 5.4), sp.frame()))[1]
                sp.alt = 0.0
                w.shake(t, 0.25, 1)
            sp.curl = 1.0 - smooth((t - self.cut) / 0.45)
            if t - self.cut > 0.5 and sp.state == "held":
                sp.curl = 0.0
                sp.go("pause", dur=random.uniform(0.6, 1.2))
            if t - self.cut > 2.0:
                w.dark_target = 0.0
                return False
        return True

    def back(self, cv, t):
        if self.anchor is None:
            return
        ac = self.anchor * 2.0
        if self.cut is None:
            c, r, _ = proj(self.sp.to_world((-6.5, 0.0, 5.4), self.sp.frame()))
            cv.line(ac, -1.0, c, r, 247)
        else:                                      # the loose thread is reeled back up
            age = t - self.cut
            cv.line(ac, -1.0, ac, self.cut_row * max(0.0, 1.0 - age / 1.2), grey(246 - int(age * 6)))


EYE_PATTERNS = (
    ((0, 0, "o"), (2, 0, "o")),
    ((0, 0, "o"), (2, 0, "o")),
    ((0, 0, "O"), (3, 0, "O")),
    ((0, 0, "o"), (2, 0, "o"), (-1, -1, "."), (3, -1, ".")),
    ((0, 0, "O"), (3, 0, "O"), (1, -1, "o"), (2, -1, "o"), (-2, -1, "."), (5, -1, "."), (-1, 0, "."), (4, 0, ".")),
)


class Eyes(Scene):
    """Lights out. Dozens of red eyes open in the dark... then it is right in front of you."""

    def __init__(self, world, t):
        super().__init__(world, t)
        self.sp.go("held")
        W, H = world.W, world.H
        n = int(16 + 22 * world.intensity)
        self.watchers = [[random.randint(4, W - 8), random.randint(2, H - 2), random.choice(EYE_PATTERNS),
                          t + 1.0 + 4.2 * (i / n) ** 0.7 + random.uniform(0.0, 0.3), random.uniform(0.45, 1.0)]
                         for i in range(n)]
        self.shown = False
        world.dark_target = 1.0
        world.say("THEY ARE ALL AWAKE NOW.", t + 2.0, row=H - 3)

    def update(self, t, dt):
        sp, w, st = self.sp, self.w, t - self.t0
        if st < 0.8:
            self.sink(st)
            return True
        if st < 7.0:                               # watched ... then silence
            return True
        if not self.shown:                         # and it is right here
            self.shown = True
            sp.wx, sp.wy = w.center()
            sp.heading, sp.zoom, sp.rear, sp.pitch = math.pi / 2.0, 1.35, 0.7, 0.28
            sp.fade = sp.eyes = sp.flicker = 1.0
            w.flash(t)
            w.shake(t, 0.6, 2)
            w.glitch("tear", t, 0.15)
            w.dark_target = 0.0
        if st < 7.6:
            sp.jx, sp.jy = random.uniform(-0.25, 0.25), random.uniform(-0.12, 0.12)
        p = smooth((st - 7.6) / 0.9)
        sp.zoom, sp.rear, sp.pitch = lerp(1.35, 1.0, p), 0.7 * (1.0 - p), 0.28 * (1.0 - p)
        if st > 8.6:
            sp.go("pause", dur=1.0)
            return False
        return True

    def front(self, cv, t):
        st = t - self.t0
        if not 0.8 < st < 6.2:
            return
        for x, y, pattern, opened, lvl in self.watchers:
            age = t - opened
            if age < 0 or random.random() < 0.03:     # not yet open / blinking
                continue
            opening = age < 0.25
            for dx, dy, ch in pattern:
                cv.put(x + dx, y + dy, "." if opening else ch, red(lvl * (0.55 if opening else 1.0)))


TINY = ["/o\\", "\\o/"]


class Swarm(Scene):
    """They pour in from every edge, crawl over everything, then flee."""

    def __init__(self, world, t):
        super().__init__(world, t)
        self.sp.go("pause", dur=9.5)               # the big one freezes and lets them come
        W, H = world.W, world.H
        self.bugs = []
        for _ in range(int(45 + 45 * world.intensity)):
            x, y = random.choice(((random.uniform(0, W), -1.0), (random.uniform(0, W), float(H)),
                                  (-4.0, random.uniform(0, H)), (W + 2.0, random.uniform(0, H))))
            self.bugs.append({"x": x, "y": y, "t": t + random.uniform(0.0, 3.2), "wait": 0.0,
                              "tx": random.uniform(2, W - 4), "ty": random.uniform(1, H - 2),
                              "v": random.uniform(9.0, 18.0), "big": random.random() < 0.18, "flee": False})
        world.say(random.choice(("THEY HEARD YOU.", "THEY ARE EVERYWHERE.")), t + 0.6)

    def update(self, t, dt):
        st = t - self.t0
        W, H = self.w.W, self.w.H
        alive = []
        for b in self.bugs:
            if t < b["t"]:
                alive.append(b)
                continue
            if b["wait"] > 0:
                b["wait"] -= dt
                alive.append(b)
                continue
            if st > 6.5 and not b["flee"]:          # and now they run, all at once
                b["flee"] = True
                b["v"] *= 1.7
                b["tx"], b["ty"] = min(((b["x"], -6.0), (b["x"], H + 6.0), (-12.0, b["y"]), (W + 12.0, b["y"])),
                                       key=lambda p: abs(p[0] - b["x"]) / 2.0 + abs(p[1] - b["y"]))
            dx, dy = b["tx"] - b["x"], (b["ty"] - b["y"]) * 2.0
            d = math.hypot(dx, dy)
            if d < 1.0:
                if b["flee"]:
                    continue
                b["tx"] = clamp(b["x"] + random.uniform(-14, 14), 1, W - 4)
                b["ty"] = clamp(b["y"] + random.uniform(-5, 5), 1, H - 2)
                if random.random() < 0.3:
                    b["wait"] = random.uniform(0.2, 0.9)
            else:
                step = min(d, b["v"] * dt)
                b["x"] += dx / d * step + random.uniform(-0.3, 0.3)
                b["y"] += dy / d * step / 2.0
            alive.append(b)
        self.bugs = alive
        return st < 12.0 and (st < 7.0 or bool(self.bugs))

    def front(self, cv, t):
        for i, b in enumerate(self.bugs):
            if t < b["t"]:
                continue
            x, y, moving = int(b["x"]), int(b["y"]), b["wait"] <= 0
            if b["big"]:
                sprite = SMALL[int(t * 8 + i) % 2] if moving else SMALL[0]
                for j, ch in enumerate(sprite):
                    cv.put(x + j, y, ch, 88 if ch == "o" else 244 if ch in "()" else 241)
            else:
                sprite = TINY[int(t * 10 + i) % 2] if moving else TINY[0]
                for j, ch in enumerate(sprite):
                    cv.put(x + j, y, ch, 246 if j == 1 else 240)


class Glass(Scene):
    """It hits the screen so hard the glass cracks."""

    def __init__(self, world, t):
        super().__init__(world, t)
        self.sp.go("lunge", kind="glass")
        self.sp.last_lunge = t
        self.cracks, self.hit, self.at = [], None, None

    def crack(self, t, at):
        self.hit, self.at = t, (at[0], at[1])
        c0, r0 = at[0], at[1]
        speed = 70.0                               # how fast the cracks run (units per second)

        def branch(x, y, a, steps, dist):
            for _ in range(steps):
                L = random.uniform(2.5, 6.0)
                a += random.uniform(-0.45, 0.45)
                nx, ny = x + math.cos(a) * L * 2.0, y + math.sin(a) * L
                self.cracks.append((x, y, nx, ny, dist / speed))
                dist += L
                if random.random() < 0.22 and steps > 2:
                    branch(nx, ny, a + random.choice((-1, 1)) * random.uniform(0.6, 1.1), steps // 2, dist)
                x, y = nx, ny

        n = random.randint(6, 8)
        spokes = [2.0 * math.pi * (i + random.uniform(-0.3, 0.3)) / n for i in range(n)]
        for a in spokes:
            branch(c0, r0, a, random.randint(5, 10), 0.0)
        for rr in (random.uniform(2.5, 3.5), random.uniform(5.5, 7.5)):   # concentric fractures
            ring = [(c0 + math.cos(a) * rr * 2.0 * random.uniform(0.85, 1.15),
                     r0 + math.sin(a) * rr * random.uniform(0.85, 1.15)) for a in spokes]
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                self.cracks.append((x1, y1, x2, y2, rr / speed + 0.04))

    def update(self, t, dt):
        if self.hit is None:
            return t - self.t0 < 6.0
        return t - self.hit < 6.5

    def front(self, cv, t):
        if self.hit is None:
            return
        age = t - self.hit
        fade = 1.0 if age < 4.5 else max(0.0, 1.0 - (age - 4.5) / 2.0)
        edge = 239 if fade > 0.75 else 237 if fade > 0.45 else 235 if fade > 0.2 else BLACK
        for x0, y0, x1, y1, delay in self.cracks:
            if age >= delay:
                g = grey(255 if age - delay < 0.3 else 252, fade)
                if g >= 234:
                    cv.line(x0, y0, x1, y1, g, bg=edge)
        c, r = int(self.at[0]), int(self.at[1])
        if fade > 0.2:
            for dc, dr, ch in ((0, 0, "@"), (-1, 0, "*"), (1, 0, "*"), (0, -1, "*"), (0, 1, "*"), (-2, 0, "#"), (2, 0, "#")):
                cv.put(c + dc, r + dr, ch, grey(255, fade))


class Mother(Scene):
    """Something enormous crawls past in the background. It was never just one."""

    def __init__(self, world, t):
        super().__init__(world, t)
        g = self.g = Spider(world)
        g.go("held")
        g.zoom = 2.5
        g.heading = random.choice((0.0, math.pi))
        wide = world.W / 2.0
        margin = 20.0 * g.k * g.zoom
        x0, x1, y0, y1 = world.bounds()
        g.wy = y0 - world.scale
        g.wx = -margin if g.heading == 0.0 else wide + margin
        self.end = wide + margin if g.heading == 0.0 else -margin
        self.speed = (wide + 2.0 * margin) / 15.0
        g.fade = g.eyes = 0.0
        self.sp.go("pause", dur=3.0)
        world.dark_target = 0.35
        world.say("IT WAS NEVER JUST ONE.", t + 3.0)

    def update(self, t, dt):
        g, sp, st = self.g, self.sp, t - self.t0
        g.update(dt, t, self.w.intensity)
        g.fade = 0.38 * smooth(st / 2.5)
        g.eyes = 0.55 * smooth((st - 1.0) / 2.0)
        step = self.speed * dt
        g.wx += math.cos(g.heading) * step
        g.phase += step / (2.0 * STRIDE * g.k * g.zoom)
        if sp.state == "pause":                    # the small one does not dare to move
            sp.data["dur"] = sp.st + 0.5
            sp.jx, sp.jy = random.uniform(-0.15, 0.15), random.uniform(-0.08, 0.08)
        if (g.wx - self.end) * math.cos(g.heading) > 0:
            self.w.dark_target = 0.0
            return False
        return True

    def back(self, cv, t):
        self.g.render(cv, t)


class Cocoon(Scene):
    """A web is spun across the whole screen. It waits at the centre. Then it tears through."""

    def __init__(self, world, t):
        super().__init__(world, t)
        self.sp.go("held")
        W, H = world.W, world.H
        self.hub = (W / 4.0, H * 0.45)             # x in body units, y in rows
        R = max(W / 2.0, float(H)) * 0.95
        n = 16
        angles = [2.0 * math.pi * (i + random.uniform(-0.15, 0.15)) / n for i in range(n)]
        self.pts = weave(W, H, self.hub[0], self.hub[1], R, angles,
                         [R * random.uniform(0.9, 1.1) for _ in angles], True, max(6, int(R / 2.3)))
        self.rip = None
        self.placed = False
        world.dark_target = 0.45
        world.say("YOU ARE CAUGHT IN IT NOW.", t + 1.2)

    def tear(self, t, at):
        self.rip = (t, at[0], at[1])

    def update(self, t, dt):
        sp, w, st = self.sp, self.w, t - self.t0
        if st < 0.7:
            self.sink(st, 0.7)
            return True
        if st < 5.0:                               # spinning
            return True
        if not self.placed:                        # it is waiting at the centre of the web
            self.placed = True
            sp.wx, sp.wy = self.hub[0], (self.hub[1] + 2.4 * sp.k * COSP) / SINP
            sp.heading, sp.zoom = math.pi / 2.0, 1.0
            sp.pitch = sp.rear = sp.tilt = sp.alt = 0.0
            sp.fade = sp.eyes = 0.0
        if st < 6.4:
            sp.eyes, sp.fade = smooth((st - 5.0) / 0.5), smooth((st - 5.4) / 1.0)
            return True
        if st < 7.4:
            p = smooth((st - 6.4) / 0.5)
            sp.rear, sp.pitch = p, 0.3 * p
            return True
        if sp.state == "held":
            sp.go("lunge", kind="cocoon")
            sp.last_lunge = t
        if self.rip is not None and t - self.rip[0] > 2.5:
            w.dark_target = 0.0
            return False
        return st < 14.0

    def back(self, cv, t):
        p = clamp((t - self.t0 - 0.7) / 4.3, 0.0, 1.0)
        if p <= 0.0:
            return
        rip = self.rip
        age = t - rip[0] if rip else 0.0
        torn = grey(241, max(0.0, 1.0 - age / 2.5))
        for o, r, c, g in self.pts:
            if o > p:
                break
            if rip:                                # ripped apart from the point of impact
                if math.hypot((c - rip[1]) / 2.0, r - rip[2]) < age * 45.0 and hash2(r, c) > 0.12:
                    continue
                if torn < 234:
                    continue
                col = torn
            else:
                col = 247 if p < 1.0 and o > p - 0.05 else 241
            cv.ch[r][c] = g
            cv.co[r][c] = col | (BLACK << 8)


class Heartbeat(Scene):
    """It stops and stares. A heartbeat, faster and faster. Silence. Then it jumps."""

    def __init__(self, world, t):
        super().__init__(world, t)
        sp = self.sp
        sp.go("held")
        self.h0 = sp.heading
        self.face = sp.heading + angle_diff(math.pi / 2.0, sp.heading)
        self.beat = self.pulse = 0.0
        world.dark_target = 0.5
        world.say("DON'T. MOVE.", t + 1.5, hold=4.5, speed=6.0)

    def update(self, t, dt):
        sp, w, st = self.sp, self.w, t - self.t0
        if st < 1.2:                               # it turns to look at you
            sp.heading = lerp(self.h0, self.face, smooth(st / 1.2))
            sp.phase += dt * 0.8
        if st < 7.2:
            bpm = lerp(52.0, 150.0, smooth(st / 7.2))
            self.beat += dt * bpm / 60.0
            ph = self.beat % 1.0
            self.pulse = max(math.exp(-(ph / 0.07) ** 2), 0.65 * math.exp(-((ph - 0.2) / 0.07) ** 2),
                             math.exp(-((ph - 1.0) / 0.07) ** 2))
            sp.zoom = 1.0 + 0.12 * smooth(st / 7.2)   # creeping closer
            sp.flicker = 1.0
            if self.pulse > 0.6:
                sp.jx = random.uniform(-0.08, 0.08)
            return True
        self.pulse = 0.0
        if st < 7.9:                               # silence. darkness.
            sp.fade = sp.eyes = 0.0
            w.dark_target = 1.0
            return True
        sp.wx, sp.wy = w.center()                  # and there it is
        sp.zoom, sp.heading = 1.0, math.pi / 2.0
        sp.fade = sp.eyes = 1.0
        w.dark_target = 0.0
        sp.go("lunge")
        sp.last_lunge = t
        return False

    def front(self, cv, t):
        if self.pulse < 0.04:
            return
        W, H = cv.W, cv.H
        band = 1.0 + 4.0 * self.pulse              # blood pulsing at the edges of your vision
        hot = 88 if self.pulse > 0.55 else 52
        edge = int(band * 2.0) + 1
        for r in range(H):
            row = cv.co[r]
            dr = min(r, H - 1 - r)
            cols = range(W) if dr < band else list(range(min(W, edge))) + list(range(max(0, W - edge), W))
            for c in cols:
                d = min(dr, min(c, W - 1 - c) / 2.0)
                if d < band:
                    row[c] = (row[c] & 255) | ((hot if d < band * 0.45 else 52) << 8)


SCENES = {"descent": Descent, "eyes": Eyes, "swarm": Swarm, "glass": Glass,
          "mother": Mother, "cocoon": Cocoon, "heartbeat": Heartbeat}

# ----------------------------------------------------------------------------
# The world: webs, critters, text, glitches, tension
# ----------------------------------------------------------------------------
class World:
    RAMP_TIME = 140.0          # seconds from calm to the climax

    def __init__(self, W, H, flash=True, demo=False, first=None):
        self.flash_ok = flash
        self.scene = None
        self.demo = demo
        self.queue = list(SCENES) if demo else ([first] if first else [])
        self.next_scene = 9.0 if self.queue else 38.0
        self.recent_scenes = []
        self.want_scene = False
        self.W = self.H = 0
        self.scale = 1.0
        self.ext = (-10.0, 10.0, -20.0, 20.0)
        self.webs, self.critters, self.messages, self.glitches = [], [], [], []
        self.cycle_start = 0.0
        self.intensity = 0.0
        self.climax = False
        self.flashes = []
        self.last_flash = -99.0
        self.shake_until, self.shake_amp = 0.0, 0
        self.dark = self.dark_target = 0.0
        self.next_msg, self.next_glitch, self.next_critter = 18.0, 10.0, 7.0
        self.recent = []
        self.corners = random.sample(range(4), 4)
        self.web_plan = self.plan_webs(0.0)
        self.base, self.base_t, self.base_dim = None, -1.0, None
        self.spider = None
        self.resize(W, H)
        self.spider = Spider(self)
        self.say(INTRO_LINE, 1.2, row=H - 3, speed=11.0, hold=2.6, color=124, spaced=False)

    # ---- geometry ----------------------------------------------------------
    def resize(self, W, H):
        self.W, self.H = W, H
        # as big as the window allows: the whole spider must fit in the height
        probe = Spider(k=1.0)
        top, bottom, left, right = probe.extent()
        k = 0.86 * clamp(min((H - 1.5) / (bottom - top), (W - 2.0) / (right - left) * 1.35), 0.45, 3.6)
        probe.k = k
        self.scale, self.ext = k, probe.extent()
        for web in self.webs:
            web["pts"] = self.raster_web(web)
        self.critters = []
        self.base = None
        if self.spider is not None:
            self.spider.k = self.scale
            x0, x1, y0, y1 = self.bounds()
            self.spider.wx = clamp(self.spider.wx, x0, x1)
            self.spider.wy = clamp(self.spider.wy, y0, y1)
            self.spider.target = None
        for m in self.messages:
            m.row = min(m.row, H - 2)
            m.col = max(1, (W - len(m.text)) // 2)

    def center(self):
        x0, x1, y0, y1 = self.bounds()
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def bounds(self):
        """Where the spider may stand on the floor so that its body stays on screen."""
        top, bottom, left, right = self.ext
        wide = self.W / 2.0
        x0, x1 = 7.0 * self.scale, wide - 7.0 * self.scale
        y0, y1 = (0.3 - top) / SINP, (self.H - 1.3 - bottom) / SINP
        if x0 > x1:
            x0 = x1 = wide / 2.0
        if y0 > y1:
            y0 = y1 = (y0 + y1) / 2.0
        return x0, x1, y0, y1

    # ---- webs ----------------------------------------------------------------
    def plan_webs(self, t):
        self.webs, self.corners, self.base = [], random.sample(range(4), 4), None
        return [(t + 1.0, "corner"), (t + 3.5, "corner"), (t + 18.0, "orb"), (t + 60.0, "corner")]

    def add_web(self, kind, t):
        web = {"kind": kind, "t0": t, "dur": random.uniform(26.0, 40.0), "seed": random.random()}
        if kind == "corner":
            if not self.corners:
                return
            web["corner"] = self.corners.pop()
            web["spokes"] = random.randint(5, 7)
            web["r"] = random.uniform(0.42, 0.56)
        else:
            web["c"] = (random.uniform(0.25, 0.75), random.uniform(0.18, 0.38))
            web["spokes"] = random.randint(10, 13)
            web["r"] = random.uniform(0.22, 0.3)
        web["pts"] = self.raster_web(web)
        self.webs.append(web)
        self.base = None

    def raster_web(self, web):
        wide, H = self.W / 2.0, float(self.H)
        rnd = random.Random(web["seed"])
        size = min(wide, H)
        n = web["spokes"]
        if web["kind"] == "corner":
            corner = web["corner"]
            cx, cy = ((0.0, 0.0), (wide, 0.0), (0.0, H), (wide, H))[corner]
            a0 = (0.0, 90.0, 270.0, 180.0)[corner]
            angles = [math.radians(a0 + 4.0 + 82.0 * i / (n - 1) + rnd.uniform(-3, 3)) for i in range(n)]
            ring = False
        else:
            cx, cy = web["c"][0] * wide, web["c"][1] * H
            angles = [2.0 * math.pi * (i + rnd.uniform(-0.2, 0.2)) / n for i in range(n)]
            ring = True
        R = web["r"] * size
        return weave(self.W, self.H, cx, cy, R, angles, [R * rnd.uniform(0.85, 1.1) for _ in angles],
                     ring, max(3, int(R / 2.5)))

    def background(self, t):
        dim = self.dark > 0.35
        if self.base is not None and t - self.base_t < 0.25 and dim == self.base_dim:
            return self.base
        cv = Canvas(self.W, self.H)
        if self.dark < 0.85:
            for web in self.webs:
                p = clamp((t - web["t0"]) / web["dur"], 0.0, 1.0)
                drawn = []
                for o, r, c, g in web["pts"]:
                    if o > p:
                        break
                    fresh = p < 1.0 and o > p - 0.05
                    cv.ch[r][c] = g
                    cv.co[r][c] = (WEB_DIM if dim else WEB_NEW if fresh else WEB_OLD) | (BLACK << 8)
                    drawn.append((r, c))
                for r, c in random.sample(drawn, min(len(drawn), 3)) if not dim else ():
                    cv.co[r][c] = 243 | (BLACK << 8)          # dew catching the light
        self.base, self.base_t, self.base_dim = cv, t, dim
        return cv

    # ---- events ----------------------------------------------------------------
    def say(self, text, t, **kw):
        self.messages.append(Message(text, t, self.W, self.H, **kw))

    def whisper(self, t):
        options = [m for m in WHISPERS if m not in self.recent] or WHISPERS
        text = random.choice(options)
        self.recent = (self.recent + [text])[-5:]
        self.say(text, t)

    def glitch(self, kind, t, dur):
        g = {"kind": kind, "start": t, "until": t + dur}
        W, H = self.W, self.H
        if kind == "tear":
            g["r0"] = random.randrange(H)
            g["h"] = random.randint(1, 4)
            g["shift"] = random.choice((-1, 1)) * random.randint(2, 10)
        elif kind == "corrupt":
            g["w"], g["h"] = random.randint(6, max(7, W // 4)), random.randint(1, max(2, H // 5))
            g["c0"], g["r0"] = random.randrange(max(1, W - g["w"])), random.randrange(max(1, H - g["h"]))
        self.glitches.append(g)

    def flash(self, t, dur=0.09):
        if self.flash_ok:
            self.flashes.append((t, t + dur))
            self.last_flash = t

    def shake(self, t, dur, amp):
        self.shake_until, self.shake_amp = max(self.shake_until, t + dur), max(1, amp)

    def start_scene(self, t):
        if self.queue:
            name = self.queue.pop(0)
        else:
            name = random.choice([n for n in SCENES if n not in self.recent_scenes])
        self.recent_scenes = (self.recent_scenes + [name])[-3:]
        self.scene = SCENES[name](self, t)

    def on_strike(self, t, big, kind=None, at=None):
        self.shake(t, 1.3 if big else 0.5, 2 if big else 1)
        self.flash(t)
        if kind == "glass" and isinstance(self.scene, Glass):
            self.scene.crack(t, at)
            self.say("IT WANTS OUT.", t + 0.2, speed=26.0, hold=2.2)
        elif kind == "cocoon" and isinstance(self.scene, Cocoon):
            self.scene.tear(t, at)
            self.glitch("tear", t, 0.15)
        elif big:
            self.flash(t + 0.32)
            for i in range(12):
                self.glitch(random.choice(("tear", "corrupt")), t + i * 0.1, 0.12)
            self.say(CLIMAX_LINE, t + 0.15, row=self.H - 3, speed=18.0, hold=2.6)
        else:
            self.glitch("tear", t, 0.15)
            self.glitch("corrupt", t, 0.1)
            if random.random() < 0.55 and not self.messages:
                self.say(random.choice(STRIKE_LINES), t + 0.1, speed=30.0, hold=1.6)

    def reset_tension(self, t):
        self.climax = False
        self.scene = None
        self.cycle_start = t - 0.3 * self.RAMP_TIME
        self.messages = []
        self.web_plan = self.plan_webs(t)          # the webs were torn down in the dark

    # ---- per frame ------------------------------------------------------------
    def update(self, dt, t):
        if not self.climax:
            self.intensity = clamp((t - self.cycle_start) / self.RAMP_TIME, 0.0, 1.0)
        I = self.intensity
        self.dark += (self.dark_target - self.dark) * min(1.0, dt * 3.0)
        while self.web_plan and t >= self.web_plan[0][0]:
            self.add_web(self.web_plan.pop(0)[1], t)
        sp = self.spider
        sp.update(dt, t, I)
        if self.scene is not None:                     # a sequence is playing
            if not self.scene.update(t, dt):
                self.scene = None
                if self.demo and not self.queue:
                    self.queue = list(SCENES)
                self.next_scene = t + (3.0 if self.queue else random.uniform(26.0, 46.0) * (1.15 - 0.5 * I))
        elif sp.state in ("crawl", "pause", "turn") and not self.climax:
            if I >= 1.0 and not self.demo:
                self.climax = True
                sp.go("lunge", climax=True)
            elif self.want_scene or t >= self.next_scene:
                self.want_scene = False
                self.start_scene(t)
        if t >= self.next_critter and t > 8.0:
            if len(self.critters) < 1 + int(4 * I):
                self.critters.append(Critter(self))
            self.next_critter = t + random.uniform(4.0, 10.0) * (1.2 - 0.6 * I)
        for cr in self.critters:
            cr.update(dt)
        self.critters = [cr for cr in self.critters if cr.alive]
        self.messages = [m for m in self.messages if not m.done(t)]
        if t >= self.next_msg:
            if not self.messages and sp.state not in ("emerge", "blackout", "held") \
                    and not self.climax and self.scene is None:
                self.whisper(t)
            self.next_msg = t + random.uniform(13.0, 24.0) * (1.15 - 0.55 * I)
        if t >= self.next_glitch:
            kinds = [("tear", 0.45), ("corrupt", 0.3), ("static", 0.25)]
            if I > 0.3 and t - self.last_flash > 9.0 and self.flash_ok:
                kinds.append(("flash", 0.12))
            pick = random.uniform(0.0, sum(w for _, w in kinds))
            for kind, w in kinds:
                pick -= w
                if pick <= 0:
                    break
            if kind == "flash":
                self.flash(t, 0.07)
            else:
                self.glitch(kind, t, random.uniform(0.06, 0.22))
            if I > 0.6 and random.random() < 0.4:      # glitches start to come in bursts
                self.glitch("tear", t + 0.12, 0.1)
            self.next_glitch = t + random.expovariate(0.05 + 0.45 * I ** 1.5) + 0.3
        self.glitches = [g for g in self.glitches if g["until"] > t]
        self.flashes = [f for f in self.flashes if f[1] > t]

    def compose(self, t):
        W, H, I = self.W, self.H, self.intensity
        cv = self.background(t).copy()
        for _ in range(2 + int(6 * I)):               # dust in the dark
            cv.put(random.randrange(W), random.randrange(H), random.choice(".,'`"), 235)
        if self.scene is not None:
            self.scene.back(cv, t)
        if self.dark < 0.6:
            for cr in self.critters:
                cr.draw(cv, t)
        self.spider.render(cv, t)
        if self.scene is not None:
            self.scene.front(cv, t)
        for m in self.messages:
            m.draw(cv, t, I)
        if t < 12.0:
            hint = "[ Q / Esc / Ctrl+C: escape    SPACE: next scene ]"
            for i, ch in enumerate(hint):
                cv.put(W - len(hint) - 1 + i, H - 1, ch, 239 if t < 10.0 else 236)
        for g in self.glitches:
            if t < g["start"]:                         # scheduled for later
                continue
            kind = g["kind"]
            if kind == "tear":
                s = g["shift"]
                for r in range(g["r0"], min(H, g["r0"] + g["h"])):
                    cv.ch[r] = cv.ch[r][-s:] + cv.ch[r][:-s]
                    cv.co[r] = cv.co[r][-s:] + cv.co[r][:-s]
            elif kind == "corrupt":
                for r in range(g["r0"], min(H, g["r0"] + g["h"])):
                    for c in range(g["c0"], min(W, g["c0"] + g["w"])):
                        if random.random() < 0.45:
                            cv.put(c, r, random.choice(GLITCH), random.choice((196, 160, 124, 231, 250, 244)))
            elif kind == "static":
                for _ in range(W * H // 22):
                    cv.put(random.randrange(W), random.randrange(H), random.choice(NOISE),
                           random.choice((238, 241, 245, 250)))
        if any(a <= t < b for a, b in self.flashes):
            for r in range(H):
                cv.co[r] = [FLASH] * W
        if t < self.shake_until:
            a = self.shake_amp
            sx, sy = random.randint(-a, a), (random.randint(-1, 1) if a > 1 else 0)
            if sx:
                pad_c, pad_o = [" "] * abs(sx), [BLANK] * abs(sx)
                for r in range(H):
                    if sx > 0:
                        cv.ch[r], cv.co[r] = pad_c + cv.ch[r][:-sx], pad_o + cv.co[r][:-sx]
                    else:
                        cv.ch[r], cv.co[r] = cv.ch[r][-sx:] + pad_c, cv.co[r][-sx:] + pad_o
            if sy > 0:
                cv.ch, cv.co = [[" "] * W] + cv.ch[:-1], [[BLANK] * W] + cv.co[:-1]
            elif sy < 0:
                cv.ch, cv.co = cv.ch[1:] + [[" "] * W], cv.co[1:] + [[BLANK] * W]
        return cv


def too_small(W, H):
    cv = Canvas(W, H)
    for i, line in enumerate(("the window is too small.", "make it bigger. it needs room to move.")):
        for j, ch in enumerate(line[:W]):
            cv.put(max(0, (W - len(line)) // 2) + j, H // 2 - 1 + i, ch, 124)
    return cv


# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="A cinematic ASCII horror spider for your terminal.")
    parser.add_argument("--no-flash", action="store_true", help="disable red screen flashes")
    parser.add_argument("--fps", type=int, default=20, help="frames per second (default 20)")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--demo", action="store_true", help="play every sequence, one after another")
    parser.add_argument("--scene", choices=sorted(SCENES), help="start with this sequence")
    args = parser.parse_args()
    random.seed(args.seed)
    frame = 1.0 / clamp(args.fps, 5, 60)

    term = Terminal()
    atexit.register(term.restore)

    def stop(*_):
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), stop)
            except (ValueError, OSError):
                pass

    escaped = False
    try:
        term.start()
        W, H = term.size()
        world = World(W, H, flash=not args.no_flash, demo=args.demo, first=args.scene)
        start = last = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt, last = min(0.1, now - last), now
            t = now - start
            key = term.key()
            if key and (key[:1] in ("q", "Q", "\x03") or key == "\x1b"):
                escaped = True
                break
            if " " in key:
                world.want_scene = True
            size = term.size()
            if size != (world.W, world.H):
                world.resize(*size)
                term.invalidate()
            if world.W < 48 or world.H < 16:
                term.present(too_small(world.W, world.H))
            else:
                world.update(dt, t)
                term.present(world.compose(t))
            pause = frame - (time.perf_counter() - now)
            if pause > 0:
                time.sleep(pause)
    except KeyboardInterrupt:
        escaped = True
    finally:
        term.restore()
    if escaped:
        print("\033[38;5;124m" + OUTRO_LINE + "\033[0m")


if __name__ == "__main__":
    main()
