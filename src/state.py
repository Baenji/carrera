"""State für den Agenten: die normierten Werte, die das Modell aus der aktuellen Lage des Autos bekommt.

Dieselbe Rechnung für die Simulation und die echte Bahn, damit das Modell an der Bahn genau die
Zahlen sieht, mit denen es trainiert wurde. Format wie CarreraEnv._get_obs() in sim/environment.py.

State = [Kurvenrest, Distanz zur nächsten Kurve, Geschwindigkeit], jeweils auf 0 bis 1 normiert:
  Kurvenrest                  In einer Kurve der Weg bis zu ihrem Ende, auf einer Geraden 0.
  Distanz zur nächsten Kurve  Weg bis zum Anfang der nächsten Kurve, auch aus einer Kurve heraus.
                              Folgt direkt eine weitere Kurve, ist das der Rest des aktuellen Teils.
  Geschwindigkeit             entlang der Spur
Jedes Teil zählt einzeln, auch zwei Kurven direkt hintereinander. Die Position zählt in mm ab dem
Anfang des Startteils, wie in der Wahrnehmung (perception) und der tag_list.

Simulation:  calculate_state(tag_list, lane, position_mm, speed_mm_per_s)
Echtbetrieb: for state, status in generate_states(perception): ...

Test ohne Steuerung (Auto mit dem Handregler fahren, Strecke vorher mit perception einrichten),
aus dem Ordner src/ starten:
  python -m state
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterator

import numpy as np

import track_parts

# Normierung: muss zu d_max und v_max in sim/environment.py passen, sonst sieht das Modell an der
# echten Bahn andere Zahlen als im Training. Ändert sich ein Wert, muss das Modell neu trainiert
# werden. Sobald die Simulation state.py direkt nutzt, stehen die Werte nur noch hier.
MAX_DISTANCE_MM = 1200.0
MAX_SPEED_MM_PER_S = 3000.0


@lru_cache(maxsize=8)
def calculate_part_bounds(tag_list: tuple[str, ...], lane: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Anfang und Ende jedes Teils in mm ab dem Anfang des Startteils, dazu welche Teile Kurven sind.

    Wird pro Strecke nur einmal berechnet, weil die Simulation den State in jedem Schritt abfragt.
    Die tag_list kommt als Tupel, weil der Zwischenspeicher (lru_cache) unveränderliche Werte braucht.
    """
    part_lengths_mm = np.array(track_parts.calculate_part_lengths(list(tag_list), lane))
    part_ends_mm = np.cumsum(part_lengths_mm)
    part_starts_mm = part_ends_mm - part_lengths_mm
    is_curve = np.array([str(part) in ("L", "R") for part in tag_list])
    if not is_curve.any():
        raise ValueError("Die Strecke hat keine Kurve, es gibt also keine nächste Kurve.")
    return part_starts_mm, part_ends_mm, is_curve


def calculate_curve_distances(tag_list: list[str], lane: str, position_mm: float) -> tuple[float, float]:
    """Gibt (Kurvenrest, Distanz zur nächsten Kurve) in mm zurück, wie oben beschrieben."""
    part_starts_mm, part_ends_mm, is_curve = calculate_part_bounds(tuple(tag_list), lane)
    lane_length_mm = part_ends_mm[-1]
    position_mm = position_mm % lane_length_mm  # nach einer Runde wieder bei 0
    current_part = int(np.searchsorted(part_starts_mm, position_mm, side="right")) - 1
    rest_of_part_mm = part_ends_mm[current_part] - position_mm

    curve_rest_mm = rest_of_part_mm if is_curve[current_part] else 0.0

    # Bis zur nächsten Kurve: Rest des aktuellen Teils plus alle Geraden dazwischen
    distance_to_next_curve_mm = rest_of_part_mm
    next_part = (current_part + 1) % len(tag_list)
    while not is_curve[next_part]:
        distance_to_next_curve_mm += part_ends_mm[next_part] - part_starts_mm[next_part]
        next_part = (next_part + 1) % len(tag_list)
    return float(curve_rest_mm), float(distance_to_next_curve_mm)


def calculate_state(
    tag_list: list[str], lane: str, position_mm: float, speed_mm_per_s: float
) -> np.ndarray:
    """State als float32-Array der Form (3,), jeder Wert auf 0 bis 1 begrenzt.

    lane: Spur in Fahrtrichtung, "links" oder "rechts" (siehe track_parts.py).
    """
    curve_rest_mm, distance_to_next_curve_mm = calculate_curve_distances(tag_list, lane, position_mm)
    state = np.array(
        [
            curve_rest_mm / MAX_DISTANCE_MM,
            distance_to_next_curve_mm / MAX_DISTANCE_MM,
            speed_mm_per_s / MAX_SPEED_MM_PER_S,
        ],
        dtype=np.float32,
    )
    # Werte über 1 (z. B. eine lange Gerade) werden 1, kleine negative Geschwindigkeiten durch Jitter 0
    return np.clip(state, 0.0, 1.0)


def generate_states(perception) -> Iterator[tuple[np.ndarray | None, str]]:
    """Echtbetrieb: liefert pro Kamerabild (State, Status).

    perception: ein perception.Perception mit eingerichteter Strecke.
    Der Status kommt unverändert aus der Wahrnehmung ("erkannt" oder "nicht erkannt"). Der State ist
    None, wenn Position oder Geschwindigkeit fehlen. Das passiert auch im ersten Bild nach einem
    Aussetzer: Das Auto ist wieder erkannt, eine Geschwindigkeit gibt es aber erst ab zwei Bildern.
    Bei None nimmt die Steuerung Gas weg.
    """
    tag_list, lane = perception.get_track_layout()
    for position_mm, speed_mm_per_s, status in perception.generate_measurements():
        if position_mm is None or speed_mm_per_s is None:
            yield None, status
        else:
            yield calculate_state(tag_list, lane, position_mm, speed_mm_per_s), status


def main() -> None:
    # Erst hier importieren: Die Simulation nutzt state.py ohne Kamera und AprilTag-Bibliothek
    from perception.perception import Perception
    from perception.track_detector import TrackError

    perception = Perception()
    try:
        for state, status in generate_states(perception):
            if state is None:
                line = status
            else:
                line = (
                    f"Kurvenrest {state[0]:.2f}   nächste Kurve {state[1]:.2f}   "
                    f"Geschwindigkeit {state[2]:.2f}"
                )
            print(f"\r{line:<70}", end="", flush=True)
    except TrackError as error:
        print(f"[FEHLER] {error}")
    except KeyboardInterrupt:
        print()
    finally:
        perception.close()


if __name__ == "__main__":
    main()
