"""Steuerung: verbindet Wahrnehmung, Agent und Hardware zum Gesamtsystem.

Ablauf wie im Sequenzdiagramm im Wiki (Architektur):
  set_up_track(perception, lane)   Strecke erkennen, dann eine langsame Runde fahren und aufnehmen.
  drive_to_start(perception)       Langsam bis zum Start fahren und dort anhalten.
  drive(perception)                Fahrschleife: pro State eine Aktion vom Modell holen, als Throttle senden.

Gestartet wird über main.py. Erwartet, dass connect() aus arduino schon aufgerufen wurde.

Hardware-Test ohne Kamera (das Auto fährt stufenweise schneller), aus dem Ordner src/ starten:
  python control.py
"""

from __future__ import annotations

import time
from pathlib import Path

from stable_baselines3 import PPO

import track_parts
from arduino import close, connect, set_throttle
from perception.perception import Perception
from state import generate_states

# Trainiertes Modell aus sim/train.py. Pfad relativ zu dieser Datei, damit es egal ist, von wo
# aus gestartet wird.
MODEL_FILE = Path(__file__).parent / "model" / "ppo_2026-11-27_15-29.zip"
SETUP_THROTTLE = 30  # 0-100, beim Einrichten: langsam, aber schnell genug zum Anfahren. An der Bahn ausprobieren.
DRIVE_TO_START_THROTTLE = 25  # 0-100, beim Fahren zum Start
# So weit vor dem Start geht das Gas weg: Das Auto rollt noch aus, und das Kamerabild ist schon
# etwas alt. An der Bahn ausprobieren.
START_STOP_DISTANCE_MM = 50


def convert_action_to_throttle(action: float) -> int:
    """Aktion -1 bis 1 linear auf Throttle 0 bis 100, genau wie in sim/environment.py (step)."""
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


def drive_to_start(perception: Perception) -> None:
    """Fährt langsam bis kurz vor den Start und hält an. Wirft TrackError ohne eingerichtete Strecke.

    Ist das Auto nicht erkannt, fährt es weiter, wie beim Einrichten. Steht es knapp hinter dem
    Start, fährt es eine ganze Runde.
    """
    tag_list, lane = perception.get_track_layout()
    lane_length_mm = track_parts.calculate_lane_length(tag_list, lane)
    set_throttle(DRIVE_TO_START_THROTTLE)
    try:
        for position_mm, _, _ in perception.generate_measurements():
            if position_mm is None:
                continue
            # Die Position zählt ab dem Start bis zur Spurlänge, der Rest der Runde ist der Weg zum Start
            distance_to_start_mm = lane_length_mm - position_mm
            if distance_to_start_mm < START_STOP_DISTANCE_MM:
                break
    finally:
        set_throttle(0)


def drive(perception: Perception) -> None:
    """Fährt, bis Strg+C gedrückt wird. Ohne State geht das Gas weg."""
    # Auf der CPU, weil das Netz winzig ist: Eine Vorhersage dauert unter 0,1 ms.
    model = PPO.load(MODEL_FILE, device="cpu")
    try:
        for state, _ in generate_states(perception):
            # Kein State, wenn das Auto nicht erkannt ist, aber auch im ersten Bild danach und
            # direkt nach dem Start: Für die Geschwindigkeit braucht es mindestens zwei Bilder.
            if state is None:
                set_throttle(0)
            else:
                # deterministic=True: ohne das Erkundungsrauschen aus dem Training, wie in
                # sim/evaluate.py. predict() gibt ein Array mit einer Aktion zurück.
                actions, _ = model.predict(state, deterministic=True)
                set_throttle(convert_action_to_throttle(float(actions[0])))
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
