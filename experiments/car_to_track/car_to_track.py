"""Strecke als Polygon aus den Positionen des blauen Punkts (nutzt track_blue_dot.py).

Idee: Das Auto fährt die Strecke ab, die getrackten Positionen liegen also schon in
Fahrtrichtung vor. Eine aufgenommene Runde ist damit direkt das Polygon der Strecke (genauer:
der Spur, auf der das Auto fährt). Sortieren ist nicht nötig.

Ablauf:
  1. Starten. Kamera und Referenzbild wie in track_blue_dot.py.
  2. Auto langsam und gleichmäßig fahren lassen, [r] drücken -> Aufnahme startet.
  3. Ist das Auto wieder am Startpunkt, ist die Runde geschlossen und wird als
     track_polygon.npy gespeichert: Array (N, 2), Zeile i = i-ter Punkt in Fahrtrichtung,
     Spalten x, y in Pixeln. Gibt es die Datei schon, wird sie beim Start geladen.
  4. Mit fertigem Polygon wird der Fortschritt angezeigt: Die Position wird auf den
     nächstgelegenen Abschnitt des Polygons projiziert (magenta Punkt), Fortschritt =
     Weg vom Startpunkt bis dorthin / Rundenlänge.
  5. [r] nimmt neu auf (überschreibt die Datei), [q] / ESC beendet.

Bei Strecken mit Kreuzung ist der nächstgelegene Abschnitt direkt an der Kreuzung nicht eindeutig.

Parallaxe: Der Punkt liegt höher als die Bahn und erscheint deshalb zum Bildrand hin nach außen
verschoben. Jede Position wird auf die Stelle der Bahn direkt darunter zurückgerechnet
(correct_parallax). Bei anderem Aufbau CAMERA_HEIGHT und DOT_HEIGHT neu messen.

Laden: np.load("experiments/car_to_track/track_polygon.npy")
Gilt nur, solange die Kamera nicht bewegt wird (Pixelkoordinaten).

Start: python experiments/car_to_track/car_to_track.py
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import cv2
import numpy as np

# track_blue_dot.py liegt in einem anderen Experiment-Ordner
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "car_diff_tracking"))
import track_blue_dot as tbd  # noqa: E402

WINDOW = "Car to Track"
OUT_FILE = Path(__file__).resolve().parent / "track_polygon.npy"

MIN_STEP = 5  # px: neuer Punkt erst ab diesem Abstand zum letzten (sonst Punkthaufen beim Stehen)
CLOSE_DIST = 30  # px: so nah am Startpunkt gilt die Runde als geschlossen
MIN_POINTS = 100  # Mindestanzahl Punkte (≈ 500 px Weg), damit die Runde nicht sofort schließt

CAMERA_HEIGHT = 108.0  # cm: Kamera über der Bahn
DOT_HEIGHT = 2.0  # cm: blauer Punkt über der Bahn


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


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--device", default=None, help="Kamera (Pfad oder Index). Default: Brio suchen"
    )
    args = ap.parse_args()

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

    try:
        while True:
            frame = tbd.read_frame(cap)
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

            if closed and pos is not None:
                frac, foot = progress(pos, np.array(points))
                cv2.circle(view, foot, 6, (255, 0, 255), -1)  # Position auf dem Polygon
                status = f"Fortschritt: {frac * 100:.1f} %"
            elif closed:
                status = "Fortschritt: Auto nicht erkannt"
            elif recording:
                status = f"Aufnahme: {len(points)} Punkte"
            else:
                status = "bereit"
            tbd.put_text(view, [status, "[r] Aufnahme (neu) starten  [q] Ende"])
            cv2.imshow(WINDOW, view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("r"):
                points, recording, closed = [], True, False
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
