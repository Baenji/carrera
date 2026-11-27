"""Spur als Polygon aufnehmen, mit der erkannten Strecke abgleichen, Position auf die Strecke projizieren.

Übernommen aus experiments/car_to_track/car_to_track.py (Polygon, calculate_progress).

Polygon: Das Auto fährt die Strecke ab, die Positionen liegen also schon in Fahrtrichtung vor.
Eine aufgenommene Runde ist damit direkt das Polygon der Spur. Sortieren ist nicht nötig.

Nullpunkt: Das Polygon beginnt dort, wo die Aufnahme zufällig begonnen hat. Die Position soll aber
ab dem Anfang des Startteils zählen, weil dort auch die tag_list beginnt. Deshalb wird der Anfang
des Startteils (aus track_detector) aufs Polygon projiziert und sein Anteil der Runde gespeichert.

track_map.json enthält tag_list, Spur, Polygon und Nullpunkt. Gilt nur, solange die Kamera nicht
bewegt wird (Pixelkoordinaten).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

TRACK_MAP_FILE = Path(__file__).resolve().parent / "track_map.json"

MIN_POINT_DISTANCE = 5  # px: neuer Punkt erst ab diesem Abstand zum letzten (sonst Punkthaufen beim Stehen)
CLOSE_DISTANCE = 30  # px: so nah am Startpunkt gilt die Runde als geschlossen
MIN_POINTS = 100  # Mindestanzahl Punkte (≈ 500 px Weg), damit die Runde nicht sofort schließt


def record_lap(positions: Iterable[tuple[int, int] | None]) -> np.ndarray | None:
    """Sammelt Positionen in Fahrtrichtung, bis das Auto wieder am ersten Punkt ist.

    Gibt das Polygon als Array (N, 2) zurück, Zeile i = i-ter Punkt in Fahrtrichtung, Spalten
    x, y in Pixeln. None, wenn die Positionen enden, bevor die Runde geschlossen ist.
    """
    polygon: list[tuple[int, int]] = []
    for position in positions:
        if position is None:
            continue
        if not polygon or math.dist(position, polygon[-1]) >= MIN_POINT_DISTANCE:
            polygon.append(position)
        if len(polygon) >= MIN_POINTS and math.dist(position, polygon[0]) < CLOSE_DISTANCE:
            return np.array(polygon, dtype=np.int32)
    return None


def calculate_progress(
    position: tuple[float, float], polygon: np.ndarray
) -> tuple[float, tuple[int, int]]:
    """Gibt (Fortschritt 0..1 entlang des geschlossenen Polygons, Fußpunkt auf dem Polygon) zurück.

    Abschnitt i geht von Punkt i zu Punkt i+1, der letzte zurück zum ersten. Die Position
    wird auf jeden Abschnitt projiziert (Lot fällen), der nächstgelegene Fußpunkt gewinnt.
    Bei Strecken mit Kreuzung ist der nächstgelegene Abschnitt direkt an der Kreuzung nicht eindeutig.
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


def find_start_point(start_point_px: tuple[float, float], polygon: np.ndarray) -> float:
    """Anteil der Runde (0..1 ab dem ersten Polygonpunkt), an dem der Anfang des Startteils liegt."""
    start_progress, _ = calculate_progress(start_point_px, polygon)
    return start_progress


def calculate_position_mm(
    position: tuple[int, int], polygon: np.ndarray, start_progress: float, lane_length_mm: float
) -> float:
    """Weg vom Anfang des Startteils bis zur Position in mm, entlang der Spur (0 bis Spurlänge)."""
    progress, _ = calculate_progress(position, polygon)
    return (progress - start_progress) % 1.0 * lane_length_mm


def save_track_map(track: dict) -> None:
    track = {**track, "polygon": np.asarray(track["polygon"]).tolist()}
    TRACK_MAP_FILE.write_text(json.dumps(track) + "\n", encoding="utf-8")
    print(f"[strecke] gespeichert in {TRACK_MAP_FILE}")


def load_track_map() -> dict | None:
    """Gibt die gespeicherte Strecke zurück oder None, wenn noch keine eingerichtet wurde."""
    if not TRACK_MAP_FILE.exists():
        return None
    track = json.loads(TRACK_MAP_FILE.read_text(encoding="utf-8"))
    track["polygon"] = np.array(track["polygon"], dtype=np.int32)
    print(f"[strecke] aus {TRACK_MAP_FILE} geladen: {track['tag_list']}, Spur {track['lane']}")
    return track
