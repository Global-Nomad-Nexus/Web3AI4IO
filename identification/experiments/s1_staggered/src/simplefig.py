"""Minimal dependency-free figure writer (stdlib only).

The dependency lock (numpy/pandas/pyarrow/scipy/statsmodels) excludes
matplotlib, so figure_s1 is rendered twice by hand:
  - PDF: a minimal vector PDF writer (built-in Helvetica, no compression)
  - PNG: software rasterizer (rectangles, Bresenham lines, a 5x7 bitmap
    font) encoded with zlib + struct.
Both renderers share one Canvas command list so the two outputs match.
"""

from __future__ import annotations

import struct
import zlib

FONT: dict[str, tuple[str, ...]] = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    " ": ("00000",) * 7,
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00100", "00100"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    "=": ("00000", "00000", "01110", "00000", "01110", "00000", "00000"),
}

# Colors as (r, g, b) floats 0..1
BLACK = (0.0, 0.0, 0.0)
GRAY = (0.55, 0.55, 0.55)
DARK = (0.12, 0.12, 0.12)
LIGHT = (0.80, 0.80, 0.80)
WHITE = (1.0, 1.0, 1.0)


class Canvas:
    """Top-left origin coordinate system; commands replayed per backend."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.ops: list[tuple] = []

    def rect(self, x: float, y: float, w: float, h: float, color=BLACK):
        self.ops.append(("rect", x, y, w, h, color))

    def line(self, x0: float, y0: float, x1: float, y1: float, color=BLACK):
        self.ops.append(("line", x0, y0, x1, y1, color))

    def text(self, x: float, y: float, s: str, size: int = 10, color=BLACK):
        self.ops.append(("text", x, y, s.upper(), size, color))

    def text_width(self, s: str, size: int = 10) -> float:
        return len(s) * 6 * (size / 10.0)

    # ------------------------------------------------------------------ PDF

    def write_pdf(self, path: str) -> None:
        parts: list[str] = []

        def fy(y: float) -> float:
            return self.height - y

        for op in self.ops:
            kind = op[0]
            if kind == "rect":
                _, x, y, w, h, c = op
                parts.append(
                    f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} rg "
                    f"{x:.2f} {fy(y + h):.2f} {w:.2f} {h:.2f} re f"
                )
            elif kind == "line":
                _, x0, y0, x1, y1, c = op
                parts.append(
                    f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} RG 0.8 w "
                    f"{x0:.2f} {fy(y0):.2f} m {x1:.2f} {fy(y1):.2f} l S"
                )
            elif kind == "text":
                _, x, y, s, size, c = op
                esc = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
                parts.append(
                    f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} rg "
                    f"BT /F1 {size} Tf {x:.2f} {fy(y) - size:.2f} Td ({esc}) Tj ET"
                )
        stream = "\n".join(parts).encode("latin-1")

        objs = []
        objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
            f"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>".encode()
        )
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        out = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref_pos = len(out)
        out += f"xref\n0 {len(objs) + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode()
        with open(path, "wb") as f:
            f.write(bytes(out))

    # ------------------------------------------------------------------ PNG

    def write_png(self, path: str, scale: int = 2) -> None:
        w, h = self.width * scale, self.height * scale
        buf = bytearray(b"\xff" * (w * h * 3))

        def px(x: int, y: int, c) -> None:
            if 0 <= x < w and 0 <= y < h:
                i = (y * w + x) * 3
                buf[i] = int(c[0] * 255)
                buf[i + 1] = int(c[1] * 255)
                buf[i + 2] = int(c[2] * 255)

        for op in self.ops:
            kind = op[0]
            if kind == "rect":
                _, x, y, rw, rh, c = op
                for yy in range(int(y * scale), int((y + rh) * scale)):
                    for xx in range(int(x * scale), int((x + rw) * scale)):
                        px(xx, yy, c)
            elif kind == "line":
                _, x0, y0, x1, y1, c = op
                x0, y0, x1, y1 = (int(v * scale) for v in (x0, y0, x1, y1))
                dx, dy = abs(x1 - x0), -abs(y1 - y0)
                sx = 1 if x0 < x1 else -1
                sy = 1 if y0 < y1 else -1
                err = dx + dy
                while True:
                    px(x0, y0, c)
                    if x0 == x1 and y0 == y1:
                        break
                    e2 = 2 * err
                    if e2 >= dy:
                        err += dy
                        x0 += sx
                    if e2 <= dx:
                        err += dx
                        y0 += sy
            elif kind == "text":
                _, x, y, s, size, c = op
                ts = max(1, round(scale * size / 10))
                cx = int(x * scale)
                cy = int((y - size) * scale)
                for ch in s:
                    glyph = FONT.get(ch, FONT[" "])
                    for r, row in enumerate(glyph):
                        for col, bit in enumerate(row):
                            if bit == "1":
                                for yy in range(cy + r * ts, cy + (r + 1) * ts):
                                    for xx in range(cx + col * ts, cx + (col + 1) * ts):
                                        px(xx, yy, c)
                    cx += 6 * ts

        raw = bytearray()
        stride = w * 3
        for yy in range(h):
            raw.append(0)
            raw += buf[yy * stride : (yy + 1) * stride]
        compressed = zlib.compress(bytes(raw), 9)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )
        with open(path, "wb") as f:
            f.write(png)


def figure_s1(summary_rows: list[dict], pdf_path: str, png_path: str) -> None:
    """Grouped bar chart: bias by arm x method, coverage annotated below.

    summary_rows: dicts with keys arm, method, bias, coverage_95.
    """
    arms = ["zero", "homogeneous", "heterogeneous"]
    methods = [("twfe", DARK), ("cs_att", LIGHT)]
    lookup = {(r["arm"], r["method"]): r for r in summary_rows}

    cv = Canvas(560, 400)
    cv.rect(0, 0, 560, 400, WHITE)
    cv.text(60, 26, "FIGURE S1: BIAS AND 95% COVERAGE BY ARM AND METHOD", 12, BLACK)

    x0, y0, pw, ph = 70, 50, 440, 220  # plot box (top-left origin)
    biases = [lookup[(a, m)]["bias"] for a in arms for m, _ in methods if (a, m) in lookup]
    vmax = max([abs(b) for b in biases] + [1e-6]) * 1.25
    zero_y = y0 + ph / 2

    def ypix(v: float) -> float:
        return zero_y - (v / vmax) * (ph / 2)

    # axes and zero line
    cv.line(x0, y0, x0, y0 + ph, BLACK)
    cv.line(x0, y0 + ph, x0 + pw, y0 + ph, BLACK)
    cv.line(x0, zero_y, x0 + pw, zero_y, GRAY)
    cv.text(x0 - 52, zero_y + 3, "0", 9, BLACK)
    cv.text(x0 - 52, y0 + 3, f"{vmax:.3f}", 9, BLACK)
    cv.text(x0 - 52, y0 + ph + 3, f"-{vmax:.3f}"[0:6], 9, BLACK)
    cv.text(x0 - 58, zero_y - 40, "BIAS", 9, BLACK)

    group_w = pw / len(arms)
    bar_w = group_w / 5
    for gi, arm in enumerate(arms):
        gx = x0 + gi * group_w
        for mi, (method, color) in enumerate(methods):
            row = lookup.get((arm, method))
            if row is None:
                continue
            bx = gx + group_w / 2 - bar_w + mi * (bar_w + 4) - 2
            by = ypix(max(row["bias"], 0))
            bh = abs(ypix(row["bias"]) - zero_y)
            cv.rect(bx, by, bar_w, max(bh, 1), color)
            cov = row["coverage_95"]
            cv.text(bx - 4, y0 + ph + 24 + mi * 12, f"CV {cov:.2f}", 8, BLACK)
        cv.text(gx + group_w / 2 - 3 * len(arm), y0 + ph + 8, arm, 9, BLACK)

    # legend
    lx = x0 + pw - 150
    cv.rect(lx, 60, 12, 8, DARK)
    cv.text(lx + 18, 68, "TWFE", 9, BLACK)
    cv.rect(lx, 76, 12, 8, LIGHT)
    cv.text(lx + 18, 84, "CS-ATT", 9, BLACK)

    cv.write_pdf(pdf_path)
    cv.write_png(png_path)
