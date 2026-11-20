#!/usr/bin/env python3
"""Erzeugt ein druckfertiges A4-PDF mit AprilTags der Familie tag36h11.

Jedes Tag ist inkl. weißem Rand TAG_MM groß: 10 x 10 Zellen, davon 1 Zelle weißer Rand,
1 Zelle schwarzer Rand und 6 x 6 Datenzellen. Die Zellen werden als Vektorflächen
gezeichnet und sind beim Druck scharf.

Ausrichtung: Die Tags stehen wie die offiziellen Bilder (AprilRobotics/apriltag-imgs).
pupil_apriltags liefert die Ecken dann in der Reihenfolge
[unten links, unten rechts, oben rechts, oben links]. Die mit dem Pfeil markierte
Oberkante liegt also zwischen corners[3] und corners[2].

Aufruf:  python Documentation/generate_apriltags_pdf.py [ausgabe.pdf]
"""
import sys
from pathlib import Path

import cv2
import numpy as np

QUANTITIES = {0: 2, 1: 8, 2: 8, 3: 12, 4: 12, 5: 2, 6: 2, 7: 2}   # ID -> Stückzahl
TAG_MM = 33.0                                                    # Kantenlänge inkl. weißem Rand
CELLS = 10                                                       # Zellen über die ganze Breite
OUT = Path(__file__).with_name("apriltags_tag36h11_33mm.pdf")

PAGE_W, PAGE_H = 210.0, 297.0        # A4 in mm
COLS, ROWS = 5, 5
GAP_X, LABEL_H, GAP_Y = 5.0, 6.0, 4.0
X0 = (PAGE_W - COLS * TAG_MM - (COLS - 1) * GAP_X) / 2
Y0 = 30.0
K = 72.0 / 25.4                      # mm -> pt


def tag_cells(tag_id):
    """10x10-Matrix in offizieller Ausrichtung, True = schwarz."""
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    inner = cv2.aruco.generateImageMarker(d, tag_id, CELLS - 2, borderBits=1)
    inner = np.rot90(inner, 2)       # OpenCV zeichnet 180° gedreht ggü. den offiziellen Bildern
    cells = np.zeros((CELLS, CELLS), bool)
    cells[1:-1, 1:-1] = inner < 128
    return cells


def pdf_text(s):
    out = bytearray()
    for b in s.encode("cp1252"):
        if b in b"\\()":
            out += b"\\" + bytes([b])
        elif b >= 128:
            out += b"\\%03o" % b
        else:
            out.append(b)
    return bytes(out)


class Page:
    """Zeichenbefehle in mm, Ursprung oben links."""

    def __init__(self):
        self.ops = []

    def _rect(self, x, y, w, h):
        return f"{x * K:.3f} {(PAGE_H - y - h) * K:.3f} {w * K:.3f} {h * K:.3f} re"

    def fill_rects(self, rects, gray=0.0):
        if rects:
            self.ops.append(f"{gray} g " + " ".join(self._rect(*r) for r in rects) + " f")

    def stroke_rect(self, x, y, w, h, gray=0.6, width_pt=0.25):
        self.ops.append(f"{gray} G {width_pt} w {self._rect(x, y, w, h)} S")

    def triangle_up(self, cx, base_y, half_w, height):
        pts = [(cx - half_w, base_y), (cx + half_w, base_y), (cx, base_y - height)]
        p = [f"{x * K:.3f} {(PAGE_H - y) * K:.3f}" for x, y in pts]
        self.ops.append(f"0 g {p[0]} m {p[1]} l {p[2]} l h f")

    def text(self, x, y, s, size=8, bold=False):
        font = "F2" if bold else "F1"
        self.ops.append(f"BT /{font} {size} Tf {x * K:.3f} {(PAGE_H - y) * K:.3f} Td ".encode()
                        + b"(" + pdf_text(s) + b") Tj ET")

    def stream(self):
        return b"\n".join(o if isinstance(o, bytes) else o.encode() for o in self.ops)


def draw_tag(page, tag_id, x, y):
    cell = TAG_MM / CELLS
    m = tag_cells(tag_id)
    page.fill_rects([(x + c * cell, y + r * cell, cell, cell)
                     for r in range(CELLS) for c in range(CELLS) if m[r, c]])
    page.stroke_rect(x, y, TAG_MM, TAG_MM)                       # Schnittlinie
    page.text(x, y - 1.6, f"ID {tag_id}", size=8, bold=True)
    page.triangle_up(x + TAG_MM / 2, y - 1.2, 1.8, 3.0)          # Pfeil auf die Oberkante
    page.text(x + TAG_MM / 2 + 2.8, y - 1.6, "oben", size=6.5)


def build_pages():
    tags = [i for i, n in sorted(QUANTITIES.items()) for _ in range(n)]
    per_page = COLS * ROWS
    chunks = [tags[i:i + per_page] for i in range(0, len(tags), per_page)]
    summary = " · ".join(f"ID {i}: {n}" for i, n in sorted(QUANTITIES.items()))
    pages = []
    for p, chunk in enumerate(chunks, 1):
        pg = Page()
        pg.text(X0, 13, f"AprilTags tag36h11 · {TAG_MM:g} × {TAG_MM:g} mm inkl. weißem Rand", 12, True)
        pg.text(X0, 18.5, "Drucken mit 100 % / „Tatsächliche Größe“, nicht „An Seite anpassen“. "
                          "Kontrolle: Der Maßstab unten muss genau 100 mm lang sein.", 7.5)
        pg.text(X0, 22.5, "Entlang der grauen Linie ausschneiden, der weiße Rand gehört zum Tag. "
                          "Blatt als Vorlage behalten, der Pfeil wird mit abgeschnitten.", 7.5)
        pg.text(X0, 26.5, "Aufkleben, Pfeil = Oberkante:  Kurve: zum Kurvenmittelpunkt  ·  "
                          "Start/Ziel: in Fahrtrichtung  ·  Gerade: längs der Schiene", 7.5, True)
        for k, tag_id in enumerate(chunk):
            r, c = divmod(k, COLS)
            x = X0 + c * (TAG_MM + GAP_X)
            y = Y0 + r * (LABEL_H + TAG_MM + GAP_Y) + LABEL_H
            draw_tag(pg, tag_id, x, y)
        # Maßstab 100 mm, abwechselnd schwarz/weiß je 10 mm
        pg.fill_rects([(X0 + 10 * i, 276, 10, 2) for i in range(0, 10, 2)])
        pg.stroke_rect(X0, 276, 100, 2, gray=0.0, width_pt=0.3)
        pg.text(X0, 274, "100 mm", 7)
        pg.text(X0, 284, f"Seite {p}/{len(chunks)} · {summary} · gesamt {len(tags)}", 7)
        pages.append(pg)
    return pages


def write_pdf(pages, path):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Title (AprilTags tag36h11) >>"]
    kids = []
    for pg in pages:
        data = pg.stream()
        objs.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] "
                    b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>"
                    % (PAGE_W * K, PAGE_H * K, len(objs)))
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    Path(path).write_bytes(out)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    write_pdf(build_pages(), target)
    print(f"{sum(QUANTITIES.values())} Tags -> {target}")
