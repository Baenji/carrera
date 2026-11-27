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

def kipppunkt(werte, geduld=3):
    """werte: Liste von [t, v]. Gibt [t, v] des Kipppunkts zurück."""
    werte = [p for p in werte if p[1] is not None]  # nicht erkannte rausfiltern
    if not werte:
        return None, []

    best_idx = 0
    zaehler = 0
    for i in range(1, len(werte)):
        if werte[i][1] > werte[best_idx][1]:
            best_idx = i
            zaehler = 0
        else:
            zaehler += 1
            if zaehler >= geduld:
                break
    return werte[best_idx], werte[:best_idx + 1]   # alle Werte bis einschließlich Kipppunkt

def calc_parameters(messwerte):
    parameters = {}
    # 0:  
    # 1: Wo ist der Kipppunkt
    for throttle, werte in messwerte.items(): 
        edge_point, relevant_vals = kipppunkt(werte)
        if edge_point is None: 
            continue 
        # 2: Höchsten V-Wert vor Kipppunkt als v_max dieses Throttles -> Daraus sollte sich direkt K des PT-1-Glieds berechnen lassen
        v_max = edge_point[1]
        K = v_max 

        # 3: Was sind 63% von v_max
        v_63 = v_max * 0.63

        # 4: Welcher V-Wert liegt am nächsten an den 63%
        best_val = relevant_vals[0]
        diff = 10000
        for i in range(len(relevant_vals)): 
            if abs(i[1] - v_63) < diff: 
                diff =  abs(i[1] - v_63)
                best_val = relevant_vals[i]

        # 5: Wie viel Zeit vergeht bis zu dieser 63% Geschwindigkeit -> T
        T = best_val[0]
        # 6: für jeden Throttle je T und K abspeichern
        parameters[throttle].append([K, T])
    return parameters 

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

                    # Mittlere Zeitstempel und Geschwindigkeiten abspeichern
                    t_val_0 = t0 - start
                    t_val_1 = t1 - start
                    raw_vals[i].append([(t_val_1 - t_val_0)/ 2 + t_val_0, v])
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