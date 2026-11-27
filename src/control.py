"""Steuerung: verbindet Wahrnehmung, Agent und Hardware zum Gesamtsystem.

Ablauf wie im Sequenzdiagramm im Wiki (Architektur):
  set_up_track(perception, lane)   Strecke erkennen, dann eine langsame Runde fahren und aufnehmen.
  drive(perception)                Fahrschleife: pro State eine Aktion holen, als Throttle senden.

Gestartet wird über main.py. Erwartet, dass connect() aus arduino schon aufgerufen wurde.

Platzhalter, bis es state.py und ein trainiertes Modell gibt: generate_states(), predict_action()
und convert_action_to_throttle(). Damit fährt das Auto mit konstantem Gas, und die Kette
Kamera -> Throttle lässt sich schon an der Bahn testen.

Hardware-Test ohne Kamera (das Auto fährt stufenweise schneller), aus dem Ordner src/ starten:
  python control.py
"""

from __future__ import annotations

import time
from typing import Iterator

from arduino import close, connect, set_throttle
from perception.perception import Perception

SETUP_THROTTLE = 30  # 0-100, beim Einrichten: langsam, aber schnell genug zum Anfahren. An der Bahn ausprobieren.
PLACEHOLDER_ACTION = -0.4  # -1 bis 1, konstante Aktion, solange es kein Modell gibt (= Throttle 30)


def generate_states(perception: Perception) -> Iterator[tuple[object, str]]:
    """Platzhalter für state.generate_states(): reicht die Messung unverändert als State durch."""
    for position_mm, speed_mm_per_s, status in perception.generate_measurements():
        yield (position_mm, speed_mm_per_s), status


def predict_action(state: object) -> float:
    """Platzhalter für model.predict(state): immer dieselbe Aktion."""
    return PLACEHOLDER_ACTION


def convert_action_to_throttle(action: float) -> int:
    """Platzhalter: Aktion -1 bis 1 linear auf Throttle 0 bis 100. Muss zur Umrechnung im Env passen."""
    return round((action + 1) / 2 * 100)


def set_up_track(perception: Perception, lane: str) -> None:
    """Erkennt die Strecke und nimmt eine langsame Runde auf. Wirft TrackError bei einem Fehler."""
    set_throttle(0)
    perception.detect_track(lane)  # das Auto steht dabei
    set_throttle(SETUP_THROTTLE)
    try:
        perception.record_lap()
    finally:
        set_throttle(0)


def drive(perception: Perception) -> None:
    """Fährt, bis Strg+C gedrückt wird. Ist das Auto nicht erkannt, geht das Gas weg."""
    try:
        for state, status in generate_states(perception):
            if status == "erkannt":
                set_throttle(convert_action_to_throttle(predict_action(state)))
            else:
                set_throttle(0)
    finally:
        set_throttle(0)


def test_throttle_steps() -> None:
    """Hardware-Test: Das Auto fährt stufenweise schneller."""
    try:
        connect()
        for throttle in range(10, 50, 10):
            print(f"throttle = {throttle}")
            set_throttle(throttle)
            time.sleep(2)
    except KeyboardInterrupt:
        print()
    finally:
        close()


if __name__ == "__main__":
    test_throttle_steps()
