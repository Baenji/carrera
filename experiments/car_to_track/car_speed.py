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

Die Geschwindigkeit wird über die letzten SPEED_WINDOW_SECONDS gemittelt, weil schon wenige
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
import track_blue_dot  # noqa: E402

WINDOW_NAME = "Car Speed"
SCRIPT_DIR = Path(__file__).resolve().parent
POLYGON_FILE = SCRIPT_DIR / "track_polygon.npy"
TRACK_CONFIG_FILE = SCRIPT_DIR / "strecke.json"

MIN_POINT_DISTANCE = 5  # px: neuer Punkt erst ab diesem Abstand zum letzten (sonst Punkthaufen beim Stehen)
CLOSE_DISTANCE = 30  # px: so nah am Startpunkt gilt die Runde als geschlossen
MIN_POINTS = 100  # Mindestanzahl Punkte (≈ 500 px Weg), damit die Runde nicht sofort schließt

CAMERA_HEIGHT = 108.0  # cm: Kamera über der Bahn
DOT_HEIGHT = 2.0  # cm: blauer Punkt über der Bahn

# Teilemaße laut Wiki ("Überarbeitung Streckenerkennung"), Set "DTM High Speed Showdown"
STRAIGHT_LENGTHS_MM = {"start": 114.0, "kurz": 114.0, "mittel": 171.0, "lang": 342.0}
CURVE_INNER_LENGTH_MM = math.pi / 2 * 144  # 90°-Kurve auf der inneren Spur ≈ 226 mm
CURVE_OUTER_LENGTH_MM = math.pi / 2 * 201  # 90°-Kurve auf der äußeren Spur ≈ 316 mm

# s: über diese Zeit wird die Geschwindigkeit gemittelt. Der Wert hinkt etwa um die halbe
# Fensterlänge hinterher. Kleiner = schneller, aber unruhiger.
SPEED_WINDOW_SECONDS = 0.1


def calculate_lane_length(track_config_file: Path) -> float:
    """Länge der Spur, auf der das Auto fährt, in mm, berechnet aus der Config."""
    config = json.loads(track_config_file.read_text(encoding="utf-8"))
    lane = config["spur"]
    if lane not in ("links", "rechts"):
        raise SystemExit(
            f"{track_config_file}: spur muss 'links' oder 'rechts' sein, nicht {lane!r}"
        )
    inner_turn = "R" if lane == "rechts" else "L"  # in dieser Kurvenrichtung fährt das Auto innen
    lane_length_mm = 0.0
    for part in config["teile"]:
        if part in STRAIGHT_LENGTHS_MM:
            lane_length_mm += STRAIGHT_LENGTHS_MM[part]
        elif part in ("R", "L"):
            lane_length_mm += (
                CURVE_INNER_LENGTH_MM if part == inner_turn else CURVE_OUTER_LENGTH_MM
            )
        else:
            raise SystemExit(
                f"{track_config_file}: unbekanntes Teil {part!r}, "
                f"erlaubt sind {list(STRAIGHT_LENGTHS_MM)}, 'R' und 'L'"
            )
    return lane_length_mm


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


def calculate_speed(
    progress_samples: deque[tuple[float, float]], lane_length_mm: float
) -> float | None:
    """Geschwindigkeit in mm/s aus dem ältesten und dem neuesten (Zeit, Fortschritt)-Paar."""
    if len(progress_samples) < 2:
        return None
    oldest_time, oldest_progress = progress_samples[0]
    newest_time, newest_progress = progress_samples[-1]
    # Über die Startlinie hinweg ist 0.99 -> 0.01 ein Schritt von +0.02, nicht -0.98.
    # Kleine Rückwärtssprünge durch Jitter bleiben dabei klein negativ.
    progress_change = (newest_progress - oldest_progress + 0.5) % 1.0 - 0.5
    return progress_change * lane_length_mm / (newest_time - oldest_time)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--device", default=None, help="Kamera (Pfad oder Index). Default: Brio suchen"
    )
    parser.add_argument(
        "--strecke",
        type=Path,
        default=TRACK_CONFIG_FILE,
        help="Config mit den Streckenteilen",
    )
    args = parser.parse_args()

    lane_length_mm = calculate_lane_length(args.strecke)
    print(f"[strecke] Spurlänge laut {args.strecke.name}: {lane_length_mm:.0f} mm")

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
    progress_samples: deque[tuple[float, float]] = deque()  # (Zeit in s, Fortschritt 0..1)

    try:
        while True:
            frame = track_blue_dot.read_frame(camera)
            now = time.perf_counter()
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

            # Nicht erkannte Frames fügen nichts hinzu. Alte Werte fallen nach SPEED_WINDOW_SECONDS
            # raus, bei einem längeren Aussetzer gibt es deshalb keine Geschwindigkeit.
            if polygon_closed and position is not None:
                progress, foot_point = calculate_progress(position, np.array(polygon))
                progress_samples.append((now, progress))
                cv2.circle(view, foot_point, 6, (255, 0, 255), -1)  # Position auf dem Polygon
            while progress_samples and now - progress_samples[0][0] > SPEED_WINDOW_SECONDS:
                progress_samples.popleft()

            if polygon_closed and position is not None:
                speed_mm_per_s = calculate_speed(progress_samples, lane_length_mm)
                speed_text = (
                    f"{speed_mm_per_s / 1000:.2f} m/s" if speed_mm_per_s is not None else "-"
                )
                status_lines = [
                    f"Fortschritt: {progress * 100:.1f} %",
                    f"Geschwindigkeit: {speed_text}",
                ]
            elif polygon_closed:
                status_lines = ["Fortschritt: Auto nicht erkannt"]
            elif recording:
                status_lines = [f"Aufnahme: {len(polygon)} Punkte"]
            else:
                status_lines = ["bereit"]
            track_blue_dot.put_text(
                view, status_lines + ["[r] Aufnahme (neu) starten  [q] Ende"]
            )
            cv2.imshow(WINDOW_NAME, view)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("r"):
                polygon, recording, polygon_closed = [], True, False
                progress_samples.clear()
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
