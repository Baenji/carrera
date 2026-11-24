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
import track_blue_dot  # noqa: E402

WINDOW_NAME = "Car to Track"
POLYGON_FILE = Path(__file__).resolve().parent / "track_polygon.npy"

MIN_POINT_DISTANCE = 5  # px: neuer Punkt erst ab diesem Abstand zum letzten (sonst Punkthaufen beim Stehen)
CLOSE_DISTANCE = 30  # px: so nah am Startpunkt gilt die Runde als geschlossen
MIN_POINTS = 100  # Mindestanzahl Punkte (≈ 500 px Weg), damit die Runde nicht sofort schließt

CAMERA_HEIGHT = 108.0  # cm: Kamera über der Bahn
DOT_HEIGHT = 2.0  # cm: blauer Punkt über der Bahn


def correct_parallax(
    position: tuple[int, int], frame_shape: tuple[int, ...]
) -> tuple[int, int]:
    """Rechnet die Position des Punkts auf die Stelle der Bahn direkt darunter zurück.

    Der Punkt erscheint um den Faktor H / (H - h) weiter von der Bildmitte entfernt als die
    Bahn unter ihm (H = CAMERA_HEIGHT, h = DOT_HEIGHT), also wird er um (H - h) / H zur
    Bildmitte hin gezogen.
    Annahme: Die Kamera schaut senkrecht nach unten (Bildmitte = Stelle unter der Kamera).
    """
    scale = (CAMERA_HEIGHT - DOT_HEIGHT) / CAMERA_HEIGHT
    center_x, center_y = frame_shape[1] / 2, frame_shape[0] / 2
    return (
        round(center_x + (position[0] - center_x) * scale),
        round(center_y + (position[1] - center_y) * scale),
    )


def calculate_progress(
    position: tuple[int, int], polygon: np.ndarray
) -> tuple[float, tuple[int, int]]:
    """Gibt (Fortschritt 0..1 entlang des geschlossenen Polygons, Fußpunkt auf dem Polygon) zurück.

    Abschnitt i geht von Punkt i zu Punkt i+1, der letzte zurück zum ersten. Die Position
    wird auf jeden Abschnitt projiziert (Lot fällen), der nächstgelegene Fußpunkt gewinnt.
    """
    position = np.asarray(position, dtype=np.float64)
    segment_starts = polygon.astype(np.float64)
    segment_ends = np.roll(segment_starts, -1, axis=0)  # der letzte Abschnitt endet am ersten Punkt
    segment_vectors = segment_ends - segment_starts
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)

    # Lage des Fußpunkts als Anteil des Abschnitts (0 = Anfang, 1 = Ende), auf 0..1 begrenzt,
    # sonst läge er neben dem Abschnitt
    fraction_along_segment = np.clip(
        ((position - segment_starts) * segment_vectors).sum(axis=1)
        / np.maximum(segment_lengths**2, 1e-9),
        0,
        1,
    )
    foot_points = segment_starts + fraction_along_segment[:, None] * segment_vectors
    closest_segment = int(np.argmin(np.linalg.norm(foot_points - position, axis=1)))

    # Weg vom Startpunkt = alle Abschnitte davor + Anteil des nächstgelegenen
    distance_travelled = (
        segment_lengths[:closest_segment].sum()
        + fraction_along_segment[closest_segment] * segment_lengths[closest_segment]
    )
    lap_length = segment_lengths.sum()
    foot_point = foot_points[closest_segment]
    return distance_travelled / lap_length, (round(foot_point[0]), round(foot_point[1]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--device", default=None, help="Kamera (Pfad oder Index). Default: Brio suchen"
    )
    args = parser.parse_args()

    device = args.device if args.device is not None else track_blue_dot.find_brio()
    camera = track_blue_dot.open_camera(device, 1280, 720, 60)
    track_blue_dot.lock_camera(camera, track_blue_dot.DEFAULT_EXPOSURE)
    # Dieselben Werte wie die Defaults von track_blue_dot.py
    tracker = track_blue_dot.DiffTracker(
        threshold=20, blur=5, scale=0.5, ref_alpha=0.05, protect_radius=70
    )
    tracker.set_reference([track_blue_dot.read_frame(camera) for _ in range(30)])
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    polygon: list[tuple[int, int]] = []  # Positionen in Fahrtrichtung
    recording = False
    polygon_closed = False
    if POLYGON_FILE.exists():
        polygon = [tuple(point) for point in np.load(POLYGON_FILE).tolist()]
        polygon_closed = True
        print(f"[polygon] {len(polygon)} Punkte aus {POLYGON_FILE} geladen")

    try:
        while True:
            frame = track_blue_dot.read_frame(camera)
            diff_mask = tracker.process(frame)
            dot_center, dot_radius, _ = track_blue_dot.find_blue_dot(frame, diff_mask)
            tracker.update_reference(dot_center)
            # Stelle der Bahn unter dem Punkt
            position = (
                correct_parallax(dot_center, frame.shape) if dot_center is not None else None
            )

            if recording and position is not None:
                if not polygon or math.dist(position, polygon[-1]) >= MIN_POINT_DISTANCE:
                    polygon.append(position)
                if (
                    len(polygon) >= MIN_POINTS
                    and math.dist(position, polygon[0]) < CLOSE_DISTANCE
                ):
                    recording, polygon_closed = False, True
                    np.save(POLYGON_FILE, np.array(polygon, dtype=np.int32))
                    print(f"[polygon] {len(polygon)} Punkte gespeichert in {POLYGON_FILE}")

            # Zeichnen: Spur orange während der Aufnahme, geschlossenes Polygon grün
            view = frame
            if len(polygon) >= 2:
                color = (0, 255, 0) if polygon_closed else (0, 165, 255)
                cv2.polylines(view, [np.array(polygon, np.int32)], polygon_closed, color, 2)
            if polygon:
                cv2.circle(view, polygon[0], 6, (0, 255, 255), -1)  # Startpunkt
            if dot_center is not None:
                cv2.circle(view, dot_center, dot_radius + 2, (0, 0, 255), 1, cv2.LINE_AA)

            if polygon_closed and position is not None:
                progress, foot_point = calculate_progress(position, np.array(polygon))
                cv2.circle(view, foot_point, 6, (255, 0, 255), -1)  # Position auf dem Polygon
                status = f"Fortschritt: {progress * 100:.1f} %"
            elif polygon_closed:
                status = "Fortschritt: Auto nicht erkannt"
            elif recording:
                status = f"Aufnahme: {len(polygon)} Punkte"
            else:
                status = "bereit"
            track_blue_dot.put_text(view, [status, "[r] Aufnahme (neu) starten  [q] Ende"])
            cv2.imshow(WINDOW_NAME, view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("r"):
                polygon, recording, polygon_closed = [], True, False
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
