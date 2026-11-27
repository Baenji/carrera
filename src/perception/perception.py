"""Wahrnehmung: Strecke einrichten und pro Kamerabild Position und Geschwindigkeit des Autos liefern.

Einrichten, einmal pro Aufbau (Ergebnis landet in track_map.json und wird beim Start geladen):
  detect_track(lane)   AprilTags erkennen -> tag_list und Anfang des Startteils. Das Auto steht.
  record_lap()         Das Auto fährt eine langsame Runde -> Polygon der Spur und Nullpunkt.

Fahren:
  generate_measurements()   Synchroner Generator: wartet auf das nächste Kamerabild, verarbeitet
                            es und liefert (Position in mm ab Start, Geschwindigkeit in mm/s, Status).
                            Status ist "erkannt" oder "nicht erkannt", dann sind Position und
                            Geschwindigkeit None.

Die Geschwindigkeit ist übernommen aus experiments/car_to_track/car_speed.py. Sie wird über die
letzten SPEED_WINDOW_SECONDS gemittelt, weil schon wenige Pixel Jitter von Frame zu Frame große
Sprünge ergeben. Wird das Auto länger nicht erkannt, gibt es keine Geschwindigkeit statt einer
erfundenen.

Test ohne Steuerung (Auto mit dem Handregler fahren), aus dem Ordner src/ starten:
  python -m perception.perception --spur rechts   # Strecke neu einrichten, dann messen
  python -m perception.perception                 # gespeicherte Strecke laden, messen
"""

from __future__ import annotations

import argparse
import time
from collections import deque
from typing import Iterator

import track_parts
from perception import camera, car_tracker, track_detector, track_map
from perception.track_detector import TrackError

# s: über diese Zeit wird die Geschwindigkeit gemittelt. Der Wert hinkt etwa um die halbe
# Fensterlänge hinterher. Kleiner = schneller, aber unruhiger.
SPEED_WINDOW_SECONDS = 0.1
REFERENCE_FRAMES = 30  # aus so vielen Bildern wird das Referenzbild gemittelt
DETECT_FRAMES = 10  # über so viele Bilder werden die AprilTags gemittelt
LAP_TIMEOUT_SECONDS = 60.0  # so lange darf die langsame Runde beim Einrichten dauern


def calculate_speed(
    position_samples: deque[tuple[float, float]], lane_length_mm: float
) -> float | None:
    """Geschwindigkeit in mm/s aus dem ältesten und dem neuesten (Zeit, Position in mm)-Paar."""
    if len(position_samples) < 2:
        return None
    oldest_time, oldest_position_mm = position_samples[0]
    newest_time, newest_position_mm = position_samples[-1]
    # Über die Startlinie hinweg ist z. B. 3990 mm -> 10 mm ein Schritt von +20 mm, nicht -3980 mm.
    # Kleine Rückwärtssprünge durch Jitter bleiben dabei klein negativ.
    half_lap_mm = lane_length_mm / 2
    distance_mm = (newest_position_mm - oldest_position_mm + half_lap_mm) % lane_length_mm - half_lap_mm
    return distance_mm / (newest_time - oldest_time)


class Perception:
    """Hält Kamera, Tracker und Strecke zwischen Einrichten und Fahren."""

    def __init__(self, device: str | int | None = None):
        device = device if device is not None else camera.find_brio()
        # Eine Auflösung für alles, damit Polygon und AprilTags dieselben Pixelkoordinaten haben
        self.camera = camera.open_camera(device, 1280, 720, 60)
        camera.lock_camera(self.camera, camera.DEFAULT_EXPOSURE)
        self.tracker = car_tracker.DiffTracker()
        self.tracker.set_reference(
            [camera.read_frame(self.camera) for _ in range(REFERENCE_FRAMES)]
        )
        self.track = track_map.load_track_map()  # None, solange keine Strecke eingerichtet ist
        # (tag_list, Spur, Anfang des Startteils in px) zwischen detect_track() und record_lap()
        self.detected_track: tuple[list, str, tuple[float, float]] | None = None

    def detect_track(self, lane: str) -> None:
        """Erkennt die Strecke an den AprilTags. Wirft TrackError, z. B. wenn ein Tag fehlt.

        lane: Spur, auf der das Auto fährt, in Fahrtrichtung gesehen: "links" oder "rechts".
        """
        frames = [camera.read_frame(self.camera) for _ in range(DETECT_FRAMES)]
        tag_list, start_point_px = track_detector.detect_track(frames)
        lane_length_mm = track_parts.calculate_lane_length(tag_list, lane)
        print(f"[strecke] tag_list = {tag_list}, Spur {lane}: {lane_length_mm:.0f} mm")
        self.detected_track = (tag_list, lane, start_point_px)

    def record_lap(self) -> None:
        """Nimmt eine Runde auf, bestimmt den Nullpunkt und speichert track_map.json.

        Das Auto muss dabei langsam fahren. Wirft TrackError, wenn die Runde nicht innerhalb von
        LAP_TIMEOUT_SECONDS geschlossen ist.
        """
        if self.detected_track is None:
            raise TrackError("Erst detect_track() aufrufen.")
        tag_list, lane, start_point_px = self.detected_track
        polygon = track_map.record_lap(self.generate_positions(LAP_TIMEOUT_SECONDS))
        if polygon is None:
            raise TrackError(f"Runde nicht innerhalb von {LAP_TIMEOUT_SECONDS:.0f} s geschlossen.")
        self.track = {
            "tag_list": tag_list,
            "lane": lane,
            "polygon": polygon,
            "start_progress": track_map.find_start_point(start_point_px, polygon),
        }
        track_map.save_track_map(self.track)
        self.detected_track = None

    def generate_positions(self, duration_seconds: float) -> Iterator[tuple[int, int] | None]:
        """Liefert duration_seconds lang pro Kamerabild die Position des Autos in px oder None."""
        end_time = time.perf_counter() + duration_seconds
        while time.perf_counter() < end_time:
            yield car_tracker.find_car(self.tracker, camera.read_frame(self.camera))

    def get_track_layout(self) -> tuple[list[int | str], str]:
        """Gibt (tag_list, Spur) der eingerichteten Strecke zurück."""
        if self.track is None:
            raise TrackError("Noch keine Strecke eingerichtet.")
        return self.track["tag_list"], self.track["lane"]

    def generate_measurements(self) -> Iterator[tuple[float | None, float | None, str]]:
        """Liefert pro Kamerabild (Position in mm ab Start, Geschwindigkeit in mm/s, Status)."""
        tag_list, lane = self.get_track_layout()
        lane_length_mm = track_parts.calculate_lane_length(tag_list, lane)
        position_samples: deque[tuple[float, float]] = deque()  # (Zeit in s, Position in mm)
        while True:
            frame = camera.read_frame(self.camera)
            now = time.perf_counter()
            position_px = car_tracker.find_car(self.tracker, frame)
            position_mm = None
            if position_px is not None:
                position_mm = track_map.calculate_position_mm(
                    position_px, self.track["polygon"], self.track["start_progress"], lane_length_mm
                )
                position_samples.append((now, position_mm))
            # Nicht erkannte Frames fügen nichts hinzu. Alte Werte fallen nach SPEED_WINDOW_SECONDS
            # raus, bei einem längeren Aussetzer gibt es deshalb keine Geschwindigkeit.
            while position_samples and now - position_samples[0][0] > SPEED_WINDOW_SECONDS:
                position_samples.popleft()

            if position_mm is None:
                yield None, None, "nicht erkannt"
            else:
                yield position_mm, calculate_speed(position_samples, lane_length_mm), "erkannt"

    def close(self) -> None:
        self.camera.release()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--spur",
        choices=["links", "rechts"],
        help="Strecke neu einrichten, das Auto fährt auf dieser Spur",
    )
    parser.add_argument(
        "--device", default=None, help="Kamera (Pfad, Index oder Name). Default: Brio suchen"
    )
    args = parser.parse_args()
    if args.spur is None and not track_map.TRACK_MAP_FILE.exists():
        parser.error("Noch keine Strecke eingerichtet, erst mit --spur links oder --spur rechts starten.")

    perception = Perception(args.device)
    try:
        if args.spur:
            perception.detect_track(args.spur)
            print(
                "[strecke] Auto jetzt langsam eine Runde fahren lassen "
                f"(höchstens {LAP_TIMEOUT_SECONDS:.0f} s)"
            )
            perception.record_lap()
        for position_mm, speed_mm_per_s, status in perception.generate_measurements():
            if status == "erkannt":
                speed_text = f"{speed_mm_per_s / 1000:.2f} m/s" if speed_mm_per_s is not None else "-"
                line = f"Position {position_mm:6.0f} mm   Geschwindigkeit {speed_text}"
            else:
                line = status
            print(f"\r{line:<50}", end="", flush=True)
    except TrackError as error:
        print(f"[FEHLER] {error}")
    except KeyboardInterrupt:
        print()
    finally:
        perception.close()


if __name__ == "__main__":
    main()
