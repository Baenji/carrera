"""Strecke aus den AprilTags (tag36h11) erkennen und als tag_list zurückgeben.

Übernommen aus experiments/track_detection/track_from_tags.py.

tag_list  Streckenteile in Fahrtrichtung, beginnend beim Start, z. B. ["1", "3", "R", "R", "L", "3", ...]
          "1" / "2" / "3" = kurze / mittlere / lange Gerade, "L" / "R" = Links- / Rechtskurve.
          Der Start steht als "1" an erster Stelle, weil er so lang ist wie eine kurze Gerade.

Wie die Reihenfolge entsteht:
  Aus Position und Drehung jedes Tags und den Teilemaßen wird berechnet, wo die beiden Enden
  seines Streckenteils liegen. Ab dem Start-Tag wird immer das Teil angehängt, dessen Ende am
  Ausgang des vorherigen Teils liegt.

Klebe-Regeln (Oberkante = die Seite, die im offiziellen Tag-Bild oben ist):
  Start (ID 0) und Geraden: Oberkante in Fahrtrichtung.
  Kurve (ID 4): Oberkante zum Kurvenmittelpunkt.
  Tags mittig auf dem Teil, zwischen den Spuren.
"""

from __future__ import annotations

import cv2
import numpy as np
from pupil_apriltags import Detector

# Tag-ID -> (Name, Länge in mm). Maße laut CLAUDE.md (Set "DTM High Speed Showdown").
PARTS = {
    0: ("Start", 114.0),
    1: ("kurze Gerade", 114.0),
    2: ("mittlere Gerade", 171.0),
    3: ("lange Gerade", 342.0),
    4: ("Kurve", None),  # 90°
}
START_ID, CURVE_ID = 0, 4
# Kurvenradien gemessen: innere Spur 144 mm (Bogen 226,2 mm), äußere Spur 201 mm (Bogen 315,7 mm).
# Das Tag klebt mittig zwischen den Spuren, sitzt also 172,5 mm vom Kurvenmittelpunkt entfernt.
CURVE_RADIUS_MM = (144.0 + 201.0) / 2
TAG_BLACK_MM = 26.4  # Kante des schwarzen Quadrats (33-mm-Tag = 10 Zellen à 3,3 mm, davon 8 schwarz umrandet)
# So weit dürfen die berechneten Enden zweier zusammengesteckter Teile auseinanderliegen (schief geklebte
# Tags, Perspektive). Kleiner als die kürzeste Gerade (114 mm), damit ein fehlendes Teil immer auffällt.
MAX_GAP_MM = 80.0


class TrackError(Exception):
    """Die Strecke ließ sich nicht eindeutig zusammensetzen."""


# --------------------------------
# Tags erkennen
# --------------------------------


def detect_tags(gray: np.ndarray, detector: Detector) -> list[dict]:
    """Nur fehlerfrei gelesene Tags (hamming == 0) mit bekannter ID."""
    tags = []
    for detection in detector.detect(gray):
        if detection.hamming != 0 or detection.tag_id not in PARTS:
            continue
        corners = detection.corners  # pupil_apriltags: [unten links, unten rechts, oben rechts, oben links]
        up = (corners[2] + corners[3]) / 2 - detection.center  # Richtung der Oberkante
        side_length_px = np.mean([np.linalg.norm(corners[index] - corners[index - 1]) for index in range(4)])
        tags.append(
            {
                "id": detection.tag_id,
                "center": detection.center,
                "up": up / np.linalg.norm(up),
                "px_per_mm": side_length_px / TAG_BLACK_MM,
            }
        )
    return tags


def merge_frames(tags_per_frame: list[list[dict]]) -> list[dict]:
    """Erkennungen mehrerer Frames zusammenfassen. Ein Tag zählt, wenn er in mindestens der
    Hälfte der Frames an derselben Stelle gefunden wurde. Das hilft gegen Flackern."""
    groups: list[list[dict]] = []
    for tags in tags_per_frame:
        for tag in tags:
            for group in groups:
                same_place = np.linalg.norm(group[0]["center"] - tag["center"]) < 5 * tag["px_per_mm"]
                if group[0]["id"] == tag["id"] and same_place:
                    group.append(tag)
                    break
            else:
                groups.append([tag])
    merged = []
    for group in groups:
        if 2 * len(group) >= len(tags_per_frame):
            up = np.mean([tag["up"] for tag in group], axis=0)
            merged.append(
                {
                    "id": group[0]["id"],
                    "center": np.mean([tag["center"] for tag in group], axis=0),
                    "up": up / np.linalg.norm(up),
                    "px_per_mm": float(np.mean([tag["px_per_mm"] for tag in group])),
                }
            )
    return merged


# --------------------------------
# Strecke zusammensetzen
# --------------------------------


def rotate(vector: np.ndarray, degrees: float) -> np.ndarray:
    angle = np.radians(degrees)
    return np.array(
        [
            vector[0] * np.cos(angle) - vector[1] * np.sin(angle),
            vector[0] * np.sin(angle) + vector[1] * np.cos(angle),
        ]
    )


def calculate_piece_ends(tag: dict) -> list[np.ndarray]:
    """Die beiden Enden des Streckenteils in Pixeln. Bei Geraden [hinten, vorne] in Fahrtrichtung."""
    px_per_mm = tag["px_per_mm"]
    if tag["id"] == CURVE_ID:
        to_center = tag["up"] * CURVE_RADIUS_MM * px_per_mm
        curve_center = tag["center"] + to_center
        # Das Tag sitzt in der Mitte des 90°-Bogens, die Enden liegen 45° davor und dahinter
        return [curve_center - rotate(to_center, 45), curve_center - rotate(to_center, -45)]
    half_length = tag["up"] * PARTS[tag["id"]][1] / 2 * px_per_mm
    return [tag["center"] - half_length, tag["center"] + half_length]


def build_tag_list(tags: list[dict]) -> tuple[list[str], list[dict]]:
    """Tags in Fahrtrichtung ordnen. Gibt (tag_list, geordnete Tags) zurück, tag_list wie oben beschrieben."""
    starts = [tag for tag in tags if tag["id"] == START_ID]
    if len(starts) != 1:
        raise TrackError(f"{len(starts)} Start-Tags (ID {START_ID}) gefunden, erwartet genau 1.")
    start = starts[0]
    px_per_mm = float(np.median([tag["px_per_mm"] for tag in tags]))  # nur um Lücken in mm anzugeben
    start_back, exit_point = calculate_piece_ends(start)
    ordered, turns = [start], [None]
    rest = [tag for tag in tags if tag is not start]

    while True:
        # Welches noch freie Teil hat ein Ende am Ausgang des letzten Teils?
        candidates = [
            (np.linalg.norm(end - exit_point), tag, end_index)
            for tag in rest
            for end_index, end in enumerate(calculate_piece_ends(tag))
        ]
        gap_px, best_tag, end_index = (
            min(candidates, key=lambda candidate: candidate[0]) if candidates else (np.inf, None, 0)
        )
        closing_gap_px = np.linalg.norm(start_back - exit_point)
        if closing_gap_px <= gap_px:  # das nächste Ende ist das hintere Ende des Starts
            if closing_gap_px / px_per_mm > MAX_GAP_MM:
                raise TrackError(
                    f"Die Runde schließt nicht: {closing_gap_px / px_per_mm:.0f} mm Lücke vor dem Start."
                )
            break
        if gap_px / px_per_mm > MAX_GAP_MM:
            name = PARTS[ordered[-1]["id"]][0]
            raise TrackError(
                f"Nach Teil {len(ordered)} ({name}) kein Anschluss gefunden, das nächste Ende ist "
                f"{gap_px / px_per_mm:.0f} mm entfernt. Fehlt dort ein Tag oder wurde es nicht erkannt?"
            )
        ends = calculate_piece_ends(best_tag)
        entry_point, exit_point = ends[end_index], ends[1 - end_index]
        turn = None
        if best_tag["id"] == CURVE_ID:
            # Liegt der Kurvenmittelpunkt rechts der Fahrtrichtung -> Rechtskurve (Bild-y zeigt nach unten)
            direction = exit_point - entry_point
            cross_product = direction[0] * best_tag["up"][1] - direction[1] * best_tag["up"][0]
            turn = "R" if cross_product > 0 else "L"
        ordered.append(best_tag)
        turns.append(turn)
        rest = [tag for tag in rest if tag is not best_tag]

    if rest:
        print(f"[WARNUNG] {len(rest)} Tag(s) gehören nicht zur Runde, IDs {[tag['id'] for tag in rest]}")
    if abs(turns.count("R") - turns.count("L")) != 4:
        print(
            f"[WARNUNG] Rechts - Links = {turns.count('R') - turns.count('L')}, erwartet ±4. "
            "Kurven-Tag verdreht?"
        )
    tag_list = []
    for tag, turn in zip(ordered, turns):
        if turn:  # Kurve -> "L" oder "R"
            tag_list.append(turn)
        elif tag["id"] == START_ID:  # Start ist so lang wie die kurze Gerade (ID 1)
            tag_list.append("1")
        else:
            tag_list.append(str(tag["id"]))
    return tag_list, ordered


def detect_track(frames: list[np.ndarray]) -> tuple[list[str], tuple[float, float]]:
    """Erkennt die Strecke auf mehreren Kamerabildern.

    Gibt (tag_list, Anfang des Startteils in px) zurück. Der Anfang des Startteils ist der
    Punkt, an dem die tag_list beginnt, und wird später zum Nullpunkt der Position.
    Wirft TrackError, wenn sich die Strecke nicht eindeutig zusammensetzen lässt.
    """
    detector = Detector(
        families="tag36h11", nthreads=4, quad_decimate=1.0, refine_edges=1, decode_sharpening=0.25
    )
    tags = merge_frames(
        [detect_tags(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), detector) for frame in frames]
    )
    counts = {part_id: sum(tag["id"] == part_id for tag in tags) for part_id in PARTS}
    print(f"[strecke] {len(tags)} Tags erkannt: " + ", ".join(f"{PARTS[part_id][0]} {count}" for part_id, count in counts.items()))
    if tags:
        cell_px = np.median([tag["px_per_mm"] for tag in tags]) * TAG_BLACK_MM / 8
        if cell_px < 3:
            print(f"[WARNUNG] nur {cell_px:.1f} px pro Tag-Zelle, unter 3 px wird die Erkennung unzuverlässig")

    tag_list, ordered = build_tag_list(tags)
    start_back, _ = calculate_piece_ends(ordered[0])
    return tag_list, (float(start_back[0]), float(start_back[1]))
