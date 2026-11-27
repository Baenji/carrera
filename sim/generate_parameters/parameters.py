"""Lässt das Auto mit einem festen Throttle fahren und misst dabei die Geschwindigkeit.

Daraus sollen später die Konstanten (K, T) für throttle_consts in environment.py bestimmt werden.

Voraussetzungen:
  - Arduino mit carrera_controller_pwm.ino (sim/einfache Arduinosteuerung) ist per USB angeschlossen
  - Kamera (Brio) hängt über der Bahn, das Auto hat den blauen Punkt
  - sim/car_to_track/track_polygon.npy existiert (vorher einmal car_speed.py starten und mit [r] aufnehmen)

Start:
  python sim/generate_parameters/parameters.py                                  # neu messen + auswerten
  python sim/generate_parameters/parameters.py --raw raw_vals_2026-11-27_14-31.json   # nur vorhandene Rohwerte auswerten
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import select, termios, tty

V_MAX_PLAUSIBEL = 4000    # mm/s, alles darüber ist ein Tracking-Fehler (z.B. Sprünge auf ~10000)

def filtern(werte):
    """Wirft nicht erkannte (None) und physikalisch unmögliche Werte (negativ, zu groß) raus."""
    return [p for p in werte if p[1] is not None and 0 <= p[1] <= V_MAX_PLAUSIBEL]

def glaetten(werte):
    """Gleitender Median über 3 Werte: einzelne Ausreißer-Spitzen fliegen raus,
    ein echter Anstieg bleibt erhalten. Zeitstempel bleiben unverändert."""
    v = [p[1] for p in werte]
    return [[werte[i][0], float(np.median(v[max(i - 1, 0):i + 2]))] for i in range(len(werte))]

def kipppunkt(werte, geduld=4):  # 4: kurzes Stocken beim Hochlaufen (3 Werte) ist noch keine Kurve
    """werte: gefilterte Liste von [t, v].
    Gibt (Index des Kipppunkts, [t, v] des Kipppunkts, alle Werte bis einschließlich Kipppunkt) zurück."""
    if not werte:
        return None, None, []

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
    return best_idx, werte[best_idx], werte[:best_idx + 1]   # alle Werte bis einschließlich Kipppunkt

def calc_parameters(messwerte):
    parameters = {}
    for throttle, werte in messwerte.items():
        # 0: Ungültige Werte rausfiltern und einzelne Ausreißer glätten
        werte = glaetten(filtern(werte))

        # 1: Wo ist der Kipppunkt = wo wird zum ersten Mal (durch die Kurve) abgebremst
        _, edge_point, relevant_vals = kipppunkt(werte)
        if edge_point is None:
            continue

        # 2: Höchste Geschwindigkeit bis zur ersten Kurve = K
        K = edge_point[1]

        # 3: Was sind 63% von K
        v_63 = K * 0.63

        # 4: Welcher V-Wert liegt am nächsten an den 63%
        best_val = relevant_vals[0]
        diff = float("inf")
        for i in range(len(relevant_vals)): 
            if abs(relevant_vals[i][1] - v_63) < diff: 
                diff =  abs(relevant_vals[i][1] - v_63)
                best_val = relevant_vals[i]

        # 5: Wie viel Zeit vergeht bis zu dieser 63% Geschwindigkeit -> T
        T = best_val[0]
        # 6: für jeden Throttle je T und K abspeichern
        parameters[throttle] = (K, T)
    return parameters

DATEN = Path(__file__).resolve().parent  # sim/generate_parameters/

def speichern(daten, dateiname):
    """Speichert ein Dict {throttle: ...} als JSON in sim/generate_parameters/."""
    with open(DATEN / dateiname, "w") as f:
        json.dump(daten, f, indent=2, default=float)  # default=float: numpy-Zahlen in normale floats umwandeln
    print(f"Gespeichert: {DATEN / dateiname}")

def laden(dateiname):
    """Lädt ein gespeichertes Dict. JSON-Schlüssel sind Strings -> wieder zu int machen.
    dateiname: Pfad oder nur Dateiname (wird dann in sim/generate_parameters/ gesucht)."""
    pfad = Path(dateiname)
    if not pfad.exists():
        pfad = DATEN / pfad.name
    with open(pfad) as f:
        daten = json.load(f)
    return {int(k): v for k, v in daten.items()}

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


def messen():
    """Fährt die Throttles nacheinander ab und gibt (raw_vals, zeitstempel) zurück."""
    # 1. Einrichten: Arduino verbinden, Kamera öffnen, Referenzbild bei stehendem Auto
    arduino = ArduinoInterface()
    kamera = kamera_starten()
    raw_vals = {}
    zeitstempel = time.strftime("%Y-%m-%d_%H-%M")  # gleicher Stempel für Rohwerte und Parameter
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
        # Rohwerte im finally speichern -> gehen auch bei Abbruch (Strg+C, Fehler) nicht verloren
        if raw_vals:
            speichern(raw_vals, f"raw_vals_{zeitstempel}.json")
    return raw_vals, zeitstempel


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", help="vorhandene raw_vals_*.json auswerten, statt neu zu messen")
    args = parser.parse_args()

    if args.raw:
        raw_vals = laden(args.raw)
        zeitstempel = Path(args.raw).stem.removeprefix("raw_vals_")  # Parameter bekommen den Stempel der Rohwerte
    else:
        raw_vals, zeitstempel = messen()

    parameters = calc_parameters(raw_vals)
    speichern(parameters, f"parameters_{zeitstempel}.json")
    print(parameters)