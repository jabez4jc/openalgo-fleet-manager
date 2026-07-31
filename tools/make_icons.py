"""Regenerate the PWA icons in static/ from the sidebar brand mark.

The mark is the same one in BASE_TEMPLATE_START: a white plus with round caps on
the blue gradient rounded square (.brand-mark in style.css). Run after changing
either of those:

    python tools/make_icons.py

Pure stdlib on purpose - Pillow is a compiled dependency to carry for three
files that change once a year.
"""
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
GRAD_FROM = (0x3B, 0x82, 0xF6)   # --accent
GRAD_TO = (0x1D, 0x4E, 0xD8)     # .brand-mark gradient end
SS = 3                           # supersampling factor, for antialiased edges


def _write_png(path, size, px):
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        raw += px[y * size * 4:(y + 1) * size * 4]

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


def _dist_to_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size, maskable=False):
    n = size * SS
    # A maskable icon is cropped to whatever shape the launcher wants, so it
    # bleeds to the edge and keeps the glyph inside the 80% safe zone.
    radius = 0.0 if maskable else n * 0.22
    glyph_box = n * 0.72 if maskable else n
    off = (n - glyph_box) / 2
    u = glyph_box / 24.0                      # SVG viewBox unit -> pixels
    half_stroke = 2.4 * u / 2
    bars = (
        (off + 5 * u, off + 12 * u, off + 19 * u, off + 12 * u),
        (off + 12 * u, off + 5 * u, off + 12 * u, off + 19 * u),
    )

    px = bytearray(size * size * 4)
    for oy in range(size):
        for ox in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    x, y = ox * SS + sx + 0.5, oy * SS + sy + 0.5
                    if radius:
                        cx = min(max(x, radius), n - radius)
                        cy = min(max(y, radius), n - radius)
                        if (x - cx) ** 2 + (y - cy) ** 2 > radius * radius:
                            continue
                    if any(_dist_to_segment(x, y, *bar) <= half_stroke for bar in bars):
                        sr = sg = sb = 255
                    else:
                        t = (x + y) / (2 * n)
                        sr, sg, sb = (int(f + (to - f) * t) for f, to in zip(GRAD_FROM, GRAD_TO))
                    r += sr; g += sg; b += sb; a += 255
            i = (oy * size + ox) * 4
            n_sub = SS * SS
            if a:
                # Un-premultiply: edge pixels average only the covered subsamples.
                covered = a / 255
                px[i] = int(r / covered); px[i + 1] = int(g / covered); px[i + 2] = int(b / covered)
            px[i + 3] = a // n_sub
    return px


if __name__ == "__main__":
    for size, maskable, name in ((192, False, "icon-192.png"),
                                 (512, False, "icon-512.png"),
                                 (512, True, "icon-maskable-512.png")):
        _write_png(os.path.join(OUT, name), size, render(size, maskable))
        print("wrote", name)
