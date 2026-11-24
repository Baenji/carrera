"""Lässt das Auto mit einem festen Throttle fahren und misst dabei die Geschwindigkeit.

Daraus sollen später die Konstanten (K, T) für throttle_consts in environment.py bestimmt werden.

Voraussetzungen:
  - Arduino mit carrera_controller_pwm.ino (sim/einfache Arduinosteuerung) ist per USB angeschlossen
  - Kamera (Brio) hängt über der Bahn, das Auto hat den blauen Punkt
  - sim/car_to_track/track_polygon.npy existiert (vorher einmal car_speed.py starten und mit [r] aufnehmen)

Start: python sim/generate_parameters/parameters.py --throttle 40 --dauer 5
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import select, termios, tty

def leertaste_gedrueckt() -> bool:
    """Wartet auf eine Taste: True bei Leertaste, False bei jeder anderen."""
    fd = sys.stdin.fileno()
    alt = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)              # Taste sofort lesen, ohne Enter
        return sys.stdin.read(1) == " "
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, alt)

def taste_n_gedrueckt() -> bool:
    """Prüft ohne zu warten, ob seit dem letzten Aufruf 'n' gedrückt wurde."""
    fd = sys.stdin.fileno()
    alt = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if select.select([sys.stdin], [], [], 0)[0]:  # liegt eine Taste bereit?
            return sys.stdin.read(1).lower() == "n"
        return False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, alt)

ROOT = Path(__file__).resolve().parents[2]  # carrera/

# Anbindung Arduinoprogramm um Auto über dieses Skript mit bestimmter Geschwindigkeit fahren zu lassen
sys.path.insert(0, str(ROOT / "sim" / "einfache Arduinosteuerung"))
from arduinosteuerung import ArduinoInterface  # noqa: E402

# Anbindung an das Skript zum Messen der Geschwindigkeit ich will hier drin den return der speed() funktion
sys.path.insert(0, str(ROOT / "sim" / "car_to_track"))
from car_speed import kamera_starten, main as speed_stream  # noqa: E402


if __name__ == "__main__":
    # 1. Einrichten: Arduino verbinden, Kamera öffnen, Referenzbild bei stehendem Auto
    arduino = ArduinoInterface()
    kamera = kamera_starten()
    raw_vals = {}
    try:
        # 2. Losfahren
        for i in range(101): 
            print(f"Throttle {i}: [Leertaste] fahren, andere Taste = überspringen. Während der Fahrt: [n] = weiter")
            if leertaste_gedrueckt(): 
                raw_vals[i] = []
                arduino.set_signal_rate(i)  # Throttle 0..100
                start = time.perf_counter()
                # 3. Messen: alle 0.05 s ein Wert (wie dt in environment.py)
                for t0, t1, v in speed_stream(show=False, intervall=0.05, kamera=kamera):
                    v_text = "- (Auto nicht erkannt)" if v is None else f"{v:.0f} mm/s"
                    raw_vals[i].append([t0 - start, t1 - start, v])
                    print(f"t0={t0 - start:.3f}  t1={t1 - start:.3f}  v={v_text}")
                    if t1 - start > 5:  # nach 5 s aufhören
                        break
                    if taste_n_gedrueckt():  # [n] = manuell zum nächsten Throttle
                        print("-> übersprungen")
                        break
                arduino.set_signal_rate(0)
    finally:
        arduino.close()  # setzt Throttle auf 0
        kamera[0].release()
        print(raw_vals)