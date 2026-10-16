"""
Exakte Geometrie der Carrera-GO-Strecke.

Die Strecke wird aus Geraden und 90°-Kreisbögen zusammengesetzt. Für eine
gewählte Spur entsteht daraus die Linie, der der Leitkiel des Autos folgt.
Alle Längen in Millimetern, Koordinatensystem mathematisch (x rechts, y oben).

Position auf der Strecke = s (mm entlang der Spur), s = 0 am Anfang der
Start/Ziel-Geraden in Fahrtrichtung.
"""
from dataclasses import dataclass

import numpy as np

# Maße aus dem entzerrten Foto vom 16.10.2026 (±3 mm), siehe README
STRAIGHT_LENGTHS = {
    "S": 114.0,  # Start/Ziel-Gerade (Anschlussschiene)
    "g": 114.0,  # kurze Gerade
    "G": 342.0,  # lange Gerade
}
CURVE_CENTER_RADIUS = 171.0  # Radius der Fahrbahnmitte einer 90°-Kurve
LANE_OFFSET = 28.5           # Abstand Spur <-> Fahrbahnmitte (Spurabstand 57 mm)
CURVE_ANGLE = np.pi / 2

# Aktueller Aufbau, ab Start/Ziel im Uhrzeigersinn (R = Rechts-, L = Linkskurve)
LAYOUT = ["S", "R", "R", "L", "G", "L", "R", "R", "G", "g", "R", "G", "G", "G", "R", "G"]


@dataclass
class Segment:
    piece: str          # Code des Streckenteils (S, g, G, R, L)
    index: int          # Position im Layout
    s0: float           # Startposition entlang der Spur
    length: float
    p0: np.ndarray      # Startpunkt (x, y)
    heading0: float     # Fahrtrichtung am Start (rad)
    curvature: float    # 1/r, positiv = Linkskurve, negativ = Rechtskurve, 0 = Gerade

    def point(self, ds):
        """Punkt und Fahrtrichtung nach ds mm innerhalb des Segments."""
        ds = np.asarray(ds, dtype=float)
        k, h0 = self.curvature, self.heading0
        if k == 0.0:
            x = self.p0[0] + ds * np.cos(h0)
            y = self.p0[1] + ds * np.sin(h0)
            return x, y, np.full_like(ds, h0)
        h = h0 + k * ds
        x = self.p0[0] + (np.sin(h) - np.sin(h0)) / k
        y = self.p0[1] - (np.cos(h) - np.cos(h0)) / k
        return x, y, h


class Track:
    """
    Spurlinie einer Carrera-GO-Strecke.

    Args:
        layout: Liste von Teile-Codes in Fahrtrichtung, beginnend mit Start/Ziel
        lane: "right" oder "left" = Spur rechts bzw. links in Fahrtrichtung.
              Bei diesem Aufbau (Uhrzeigersinn) ist "right" die Spur, die in den
              6 Rechtskurven innen liegt.
        start_heading: Fahrtrichtung am Start in rad (nur für die Darstellung)
    """

    def __init__(self, layout=LAYOUT, lane="right", start_heading=-np.pi / 2,
                 straight_lengths=STRAIGHT_LENGTHS, curve_center_radius=CURVE_CENTER_RADIUS,
                 lane_offset=LANE_OFFSET):
        if lane not in ("right", "left"):
            raise ValueError("lane muss 'right' oder 'left' sein")
        self.layout = list(layout)
        self.lane = lane
        # Seitlicher Versatz der Spur, positiv = rechts von der Fahrbahnmitte
        d = lane_offset if lane == "right" else -lane_offset

        self.segments = []
        p = np.zeros(2)
        heading = start_heading
        s = 0.0
        for i, piece in enumerate(self.layout):
            if piece in straight_lengths:
                seg = Segment(piece, i, s, straight_lengths[piece], p.copy(), heading, 0.0)
            elif piece in ("R", "L"):
                # Rechtskurve: rechte Spur liegt innen -> kleinerer Radius
                r = curve_center_radius - d if piece == "R" else curve_center_radius + d
                k = -1.0 / r if piece == "R" else 1.0 / r
                seg = Segment(piece, i, s, r * CURVE_ANGLE, p.copy(), heading, k)
            else:
                raise ValueError(f"Unbekanntes Streckenteil: {piece}")
            self.segments.append(seg)
            x, y, heading = seg.point(seg.length)
            p = np.array([float(x), float(y)])
            heading = float(heading)
            s += seg.length

        self.length = s
        self.closure_error = float(np.linalg.norm(p))  # muss ~0 sein, sonst schließt die Strecke nicht
        self._s0 = np.array([seg.s0 for seg in self.segments])
        self._curv = np.array([seg.curvature for seg in self.segments])

        # Dichte Abtastung für schnelle Projektion (Kamera -> s)
        self._dense_s = np.arange(0.0, self.length, 1.0)
        self._dense_xy = np.stack(self.position(self._dense_s), axis=1)

    # ------------------------------------------------------------------
    def segment_index(self, s):
        s = np.mod(np.asarray(s, dtype=float), self.length)
        return np.clip(np.searchsorted(self._s0, s, side="right") - 1, 0, len(self.segments) - 1)

    def curvature(self, s):
        """Krümmung 1/r an Position s (vektorisiert)."""
        return self._curv[self.segment_index(s)]

    def position(self, s):
        """(x, y) an Position s (vektorisiert)."""
        s = np.mod(np.asarray(s, dtype=float), self.length)
        idx = self.segment_index(s)
        x = np.empty_like(s)
        y = np.empty_like(s)
        for i in np.unique(idx):
            m = idx == i
            seg = self.segments[i]
            x[m], y[m], _ = seg.point(s[m] - seg.s0)
        return x, y

    def heading(self, s):
        s = np.mod(np.asarray(s, dtype=float), self.length)
        idx = self.segment_index(s)
        h = np.empty_like(s)
        for i in np.unique(idx):
            m = idx == i
            seg = self.segments[i]
            h[m] = seg.point(s[m] - seg.s0)[2]
        return h

    def project(self, x, y):
        """
        Projiziert einen Punkt auf die Spur.

        Returns:
            (s, lateral): Position entlang der Spur und seitlicher Abstand
            (positiv = rechts der Spur in Fahrtrichtung)
        """
        d2 = (self._dense_xy[:, 0] - x) ** 2 + (self._dense_xy[:, 1] - y) ** 2
        i = int(np.argmin(d2))
        # Feinkorrektur entlang der lokalen Tangente
        s = self._dense_s[i]
        h = float(self.heading(s))
        dx, dy = x - self._dense_xy[i, 0], y - self._dense_xy[i, 1]
        along = dx * np.cos(h) + dy * np.sin(h)
        lateral = dx * np.sin(h) - dy * np.cos(h)
        return float(np.mod(s + along, self.length)), float(lateral)

    def sample(self, ds=5.0):
        """Gleichmäßig abgetastete Spur: s, x, y, Krümmung."""
        s = np.arange(0.0, self.length, ds)
        x, y = self.position(s)
        return s, x, y, self.curvature(s)

    def rails(self, ds=2.0, rail_offset=5.5, lane_offset=LANE_OFFSET):
        """
        Punkte auf allen Schienen und Schlitzen beider Spuren (für die
        Kamera-Kalibrierung). Liefert (rails_xy, slots_xy).
        """
        d_self = lane_offset if self.lane == "right" else -lane_offset
        s = np.arange(0.0, self.length, ds)
        x, y = self.position(s)
        h = self.heading(s)
        nx, ny = np.sin(h), -np.cos(h)  # Normale nach rechts
        rails, slots = [], []
        for lane_d in (lane_offset, -lane_offset):
            off = lane_d - d_self  # Versatz relativ zur gewählten Spur
            slots.append(np.stack([x + off * nx, y + off * ny], 1))
            for r in (-rail_offset, rail_offset):
                rails.append(np.stack([x + (off + r) * nx, y + (off + r) * ny], 1))
        # Bögen der jeweils anderen Spur haben einen anderen Radius; die Normalen-
        # Verschiebung bildet das exakt ab, weil Spuren konzentrische Kreise sind.
        return np.concatenate(rails), np.concatenate(slots)

    def piece_centers(self):
        """Mittelpunkt (auf der Fahrbahnmitte) jedes Streckenteils + Teile-Code."""
        d_self = LANE_OFFSET if self.lane == "right" else -LANE_OFFSET
        out = []
        for seg in self.segments:
            sm = seg.s0 + seg.length / 2
            x, y = self.position(sm)
            h = float(self.heading(sm))
            out.append((float(x) - d_self * np.sin(h), float(y) + d_self * np.cos(h), seg.piece))
        return out

    def lookahead_curvature(self, s, distances):
        """Krümmung an s + d für jede Distanz d (für die Beobachtung des Agenten)."""
        return self.curvature(np.asarray(s)[..., None] + np.asarray(distances))
