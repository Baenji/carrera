"""Teiletabelle: Länge jedes Streckenteils auf der Spur, auf der das Auto fährt.

Übernommen aus experiments/car_to_track/car_speed.py (calculate_lane_length).

Teile wie in der tag_list (siehe perception/track_detector.py):
  1 / 2 / 3   kurze / mittlere / lange Gerade, der Start zählt als 1
  "L" / "R"   90°-Kurve links / rechts herum, in Fahrtrichtung gesehen

Spur: "links" oder "rechts", in Fahrtrichtung gesehen. Geraden sind auf beiden Spuren gleich lang.
Die rechte Spur ist in Rechtskurven innen (kurz) und in Linkskurven außen (lang), die linke Spur
umgekehrt.

Genutzt von perception (Spurlänge), später von state.py und der Simulation (Teillängen).
"""

from __future__ import annotations

import math

# Maße laut Wiki ("Überarbeitung Streckenerkennung"), Set "DTM High Speed Showdown"
STRAIGHT_LENGTHS_MM = {1: 114.0, 2: 171.0, 3: 342.0}  # Schlüssel wie in der tag_list
CURVE_INNER_RADIUS_MM = 144.0  # Radius der inneren Spur
CURVE_OUTER_RADIUS_MM = 201.0  # Radius der äußeren Spur
CURVE_INNER_LENGTH_MM = math.pi / 2 * CURVE_INNER_RADIUS_MM  # 90°-Bogen innen ≈ 226 mm
CURVE_OUTER_LENGTH_MM = math.pi / 2 * CURVE_OUTER_RADIUS_MM  # 90°-Bogen außen ≈ 316 mm
LANES = ("links", "rechts")


def calculate_part_lengths(tag_list: list[int | str], lane: str) -> list[float]:
    """Länge jedes Teils der tag_list in mm auf der gegebenen Spur, in derselben Reihenfolge."""
    if lane not in LANES:
        raise ValueError(f"Spur muss 'links' oder 'rechts' sein, nicht {lane!r}")
    inner_turn = "R" if lane == "rechts" else "L"  # in dieser Kurvenrichtung fährt das Auto innen
    part_lengths_mm = []
    for part in tag_list:
        if part in STRAIGHT_LENGTHS_MM:
            part_lengths_mm.append(STRAIGHT_LENGTHS_MM[part])
        elif part in ("R", "L"):
            part_lengths_mm.append(
                CURVE_INNER_LENGTH_MM if part == inner_turn else CURVE_OUTER_LENGTH_MM
            )
        else:
            raise ValueError(
                f"Unbekanntes Teil {part!r}, erlaubt sind {list(STRAIGHT_LENGTHS_MM)}, 'R' und 'L'"
            )
    return part_lengths_mm


def calculate_lane_length(tag_list: list[int | str], lane: str) -> float:
    """Länge der ganzen Spur in mm."""
    return sum(calculate_part_lengths(tag_list, lane))
