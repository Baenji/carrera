"""Geschwindigkeit des Autos aus dem Fortschritt und der Spurlänge (Iteration von car_to_track.py).

Idee: car_to_track.py liefert den Fortschritt als Anteil einer Runde. Kennt man die Länge der Runde
in mm, ist die Geschwindigkeit einfach

    v = Änderung des Fortschritts / vergangene Zeit * Spurlänge

Die Spurlänge wird aus den Streckenteilen berechnet, die von Hand in einer Config stehen
(Standard: strecke.json neben diesem Skript):

    {
      "spur": "rechts",
      "teile": ["start", "kurz", "lang", "R", "R", ...]
    }

  spur   Spur, auf der das Auto fährt, in Fahrtrichtung gesehen: "links" oder "rechts".
         Die rechte Spur ist in Rechtskurven innen (kurz) und in Linkskurven außen (lang).
  teile  Streckenteile in Fahrtrichtung, beginnend beim Start:
         start, kurz, mittel, lang (Geraden) und R, L (90°-Kurve rechts oder links herum).

Für die Länge zählt nur, welche Teile vorkommen. Die Reihenfolge wird erst später gebraucht
(z. B. für die Distanz zur nächsten Kurve im State).

Die Geschwindigkeit wird über die letzten SPEED_WINDOW_S Sekunden gemittelt, weil schon wenige
Pixel Jitter von Frame zu Frame große Sprünge ergeben. Wird das Auto länger nicht erkannt, gibt es
keine Geschwindigkeit statt einer erfundenen.

Ablauf und Polygon wie in car_to_track.py:
  1. Starten. Kamera und Referenzbild wie in track_blue_dot.py.
  2. Gibt es track_polygon.npy schon, wird es geladen. Sonst Auto langsam fahren lassen und [r]
     drücken, die Runde wird aufgenommen, bis das Auto wieder am Startpunkt ist.
  3. Mit fertigem Polygon werden Fortschritt und Geschwindigkeit angezeigt.
  4. [r] nimmt neu auf (überschreibt die Datei), [q] / ESC beendet.

Start: python experiments/car_to_track/car_speed.py [--strecke andere_strecke.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

# track_blue_dot.py liegt in einem anderen Experiment-Ordner
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "car_diff_tracking"))
import track_blue_dot as tbd  # noqa: E402

WINDOW = "Car Speed"
HERE = Path(__file__).resolve().parent
OUT_FILE = HERE / "track_polygon.npy"
TRACK_FILE = HERE / "strecke.json"

MIN_STEP = 5  # px: neuer Punkt erst ab diesem Abstand zum letzten (sonst Punkthaufen beim Stehen)
CLOSE_DIST = 30  # px: so nah am Startpunkt gilt die Runde als geschlossen
MIN_POINTS = 100  # Mindestanzahl Punkte (≈ 500 px Weg), damit die Runde nicht sofort schließt

CAMERA_HEIGHT = 108.0  # cm: Kamera über der Bahn
DOT_HEIGHT = 2.0  # cm: blauer Punkt über der Bahn

# Teilemaße laut Wiki ("Überarbeitung Streckenerkennung"), Set "DTM High Speed Showdown"
STRAIGHTS_MM = {"start": 114.0, "kurz": 114.0, "mittel": 171.0, "lang": 342.0}
CURVE_INNER_MM = math.pi / 2 * 144  # 90°-Kurve auf der inneren Spur ≈ 226 mm
CURVE_OUTER_MM = math.pi / 2 * 201  # 90°-Kurve auf der äußeren Spur ≈ 316 mm

# s: über diese Zeit wird die Geschwindigkeit gemittelt. Der Wert hinkt etwa um die halbe
# Fensterlänge hinterher. Kleiner = schneller, aber unruhiger.
SPEED_WINDOW_S = 0.1


def lane_length(track_file: Path) -> float:
    """Länge der Spur, auf der das Auto fährt, in mm, berechnet aus der Config."""
    cfg = json.loads(track_file.read_text(encoding="utf-8"))
    lane = cfg["spur"]
    if lane not in ("links", "rechts"):
        raise SystemExit(f"{track_file}: spur muss 'links' oder 'rechts' sein, nicht {lane!r}")
    inner_turn = "R" if lane == "rechts" else "L"  # in dieser Kurvenrichtung fährt das Auto innen
    total = 0.0
    for part in cfg["teile"]:
        if part in STRAIGHTS_MM:
            total += STRAIGHTS_MM[part]
        elif part in ("R", "L"):
            total += CURVE_INNER_MM if part == inner_turn else CURVE_OUTER_MM
        else:
            raise SystemExit(
                f"{track_file}: unbekanntes Teil {part!r}, erlaubt sind {list(STRAIGHTS_MM)}, 'R' und 'L'"
            )
    return total


def correct_parallax(p: tuple[int, int], shape: tuple[int, ...]) -> tuple[int, int]:
    """Rechnet die Position des Punkts auf die Stelle der Bahn direkt darunter zurück.

    Der Punkt erscheint um den Faktor H / (H - h) weiter von der Bildmitte entfernt als die
    Bahn unter ihm, also wird er um (H - h) / H zur Bildmitte hin gezogen.
    Annahme: Die Kamera schaut senkrecht nach unten (Bildmitte = Stelle unter der Kamera).
    """
    k = (CAMERA_HEIGHT - DOT_HEIGHT) / CAMERA_HEIGHT
    cx, cy = shape[1] / 2, shape[0] / 2
    return round(cx + (p[0] - cx) * k), round(cy + (p[1] - cy) * k)


def progress(pos: tuple[int, int], polygon: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Gibt (Fortschritt 0..1 entlang des geschlossenen Polygons, Fußpunkt auf dem Polygon) zurück.

    Abschnitt i geht von Punkt i zu Punkt i+1, der letzte zurück zum ersten. Die Position
    wird auf jeden Abschnitt projiziert (Lot fällen), der nächstgelegene Fußpunkt gewinnt.
    """
    p = np.asarray(pos, dtype=np.float64)
    a = polygon.astype(np.float64)  # Anfang jedes Abschnitts
    seg = np.roll(a, -1, axis=0) - a  # Vektor vom Anfang zum Ende jedes Abschnitts
    seg_len = np.linalg.norm(seg, axis=1)
    # Lage des Fußpunkts als Anteil t des Abschnitts, auf 0..1 begrenzt (sonst läge er daneben)
    t = np.clip(((p - a) * seg).sum(axis=1) / np.maximum(seg_len**2, 1e-9), 0, 1)
    foot = a + t[:, None] * seg
    i = int(np.argmin(np.linalg.norm(foot - p, axis=1)))  # nächstgelegener Abschnitt
    # Weg vom Startpunkt = alle Abschnitte davor + Anteil des aktuellen
    s = seg_len[:i].sum() + t[i] * seg_len[i]
    return s / seg_len.sum(), (round(foot[i, 0]), round(foot[i, 1]))


def speed(samples: deque[tuple[float, float]], lane_mm: float) -> float | None:
    """Geschwindigkeit in mm/s aus dem ältesten und dem neuesten (Zeit, Fortschritt)-Paar."""
    if len(samples) < 2:
        return None
    (t0, p0), (t1, p1) = samples[0], samples[-1]
    # Über die Startlinie hinweg ist 0.99 -> 0.01 ein Schritt von +0.02, nicht -0.98.
    # Kleine Rückwärtssprünge durch Jitter bleiben dabei klein negativ.
    d = (p1 - p0 + 0.5) % 1.0 - 0.5
    
    return d * lane_mm / (t1 - t0)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--device", default=None, help="Kamera (Pfad oder Index). Default: Brio suchen"
    )
    ap.add_argument(
        "--strecke", type=Path, default=TRACK_FILE, help="Config mit den Streckenteilen"
    )
    args = ap.parse_args()

    lane_mm = lane_length(args.strecke)
    print(f"[strecke] Spurlänge laut {args.strecke.name}: {lane_mm:.0f} mm")

    device = args.device if args.device is not None else tbd.find_brio()
    cap = tbd.open_camera(device, 1280, 720, 60)
    tbd.lock_camera(cap, tbd.DEFAULT_EXPOSURE)
    # Dieselben Werte wie die Defaults von track_blue_dot.py
    tracker = tbd.DiffTracker(
        threshold=20, blur=5, scale=0.5, ref_alpha=0.05, protect_radius=70
    )
    tracker.set_reference([tbd.read_frame(cap) for _ in range(30)])
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    points: list[tuple[int, int]] = []  # Positionen in Fahrtrichtung
    recording = False
    closed = False
    if OUT_FILE.exists():
        points = [tuple(p) for p in np.load(OUT_FILE).tolist()]
        closed = True
        print(f"[polygon] {len(points)} Punkte aus {OUT_FILE} geladen")
    samples: deque[tuple[float, float]] = deque()  # (Zeit in s, Fortschritt 0..1)

    try:
        while True:
            frame = tbd.read_frame(cap)
            now = time.perf_counter()
            diff_mask = tracker.process(frame)
            center, radius, _ = tbd.find_blue_dot(frame, diff_mask)
            tracker.update_reference(center)
            pos = correct_parallax(center, frame.shape) if center is not None else None

            if recording and pos is not None:
                if not points or math.dist(pos, points[-1]) >= MIN_STEP:
                    points.append(pos)
                if len(points) >= MIN_POINTS and math.dist(pos, points[0]) < CLOSE_DIST:
                    recording, closed = False, True
                    np.save(OUT_FILE, np.array(points, dtype=np.int32))
                    print(f"[polygon] {len(points)} Punkte gespeichert in {OUT_FILE}")

            # Zeichnen: Spur orange während der Aufnahme, geschlossenes Polygon grün
            view = frame
            if len(points) >= 2:
                color = (0, 255, 0) if closed else (0, 165, 255)
                cv2.polylines(view, [np.array(points, np.int32)], closed, color, 2)
            if points:
                cv2.circle(view, points[0], 6, (0, 255, 255), -1)  # Startpunkt
            if center is not None:
                cv2.circle(view, center, radius + 2, (0, 0, 255), 1, cv2.LINE_AA)

            # Nicht erkannte Frames fügen nichts hinzu. Alte Werte fallen nach SPEED_WINDOW_S raus,
            # bei einem längeren Aussetzer gibt es deshalb keine Geschwindigkeit.
            if closed and pos is not None:
                frac, foot = progress(pos, np.array(points))
                samples.append((now, frac))
                cv2.circle(view, foot, 6, (255, 0, 255), -1)  # Position auf dem Polygon
            while samples and now - samples[0][0] > SPEED_WINDOW_S:
                samples.popleft()

            if closed and pos is not None:
                v = speed(samples, lane_mm)
                v_text = f"{v / 1000:.2f} m/s" if v is not None else "-"
                lines = [f"Fortschritt: {frac * 100:.1f} %", f"Geschwindigkeit: {v_text}"]
            elif closed:
                lines = ["Fortschritt: Auto nicht erkannt"]
            elif recording:
                lines = [f"Aufnahme: {len(points)} Punkte"]
            else:
                lines = ["bereit"]
            tbd.put_text(view, lines + ["[r] Aufnahme (neu) starten  [q] Ende"])
            cv2.imshow(WINDOW, view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("r"):
                points, recording, closed = [], True, False
                samples.clear()
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
