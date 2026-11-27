"""Startet das Gesamtsystem, solange es noch kein Frontend gibt.

Übernimmt die Rolle des Frontends aus dem Sequenzdiagramm im Wiki (Architektur): Die Befehle
kommen über die Tastatur. Kamera und Arduino bleiben zwischen den Befehlen verbunden.

Aus dem Ordner src/ starten:
  python main.py

Befehle:
  e   Strecke einrichten (Spur aus config.LANE), das Auto fährt dabei eine langsame Runde
  s   Langsam zum Start fahren und dort anhalten
  f   Fahren, Strg+C stoppt und führt zurück ins Menü
  q   Beenden
"""

from __future__ import annotations

import config
import control
from arduino import close, connect
from perception.perception import Perception
from perception.track_detector import TrackError

MENU = "\n[e] Strecke einrichten   [s] Zum Start fahren   [f] Fahren   [q] Beenden: "


def main() -> None:
    connect()
    perception = Perception()
    try:
        while True:
            command = input(MENU).strip().lower()
            if command == "e":
                try:
                    control.set_up_track(perception, config.LANE)
                    print("Strecke eingerichtet.")
                except TrackError as error:
                    print(f"[FEHLER] {error}")
                except KeyboardInterrupt:
                    print("\nEinrichten abgebrochen.")
            elif command == "s":
                print("Fahre zum Start, Strg+C stoppt.")
                try:
                    control.drive_to_start(perception)
                    print("Auto steht am Start.")
                except TrackError as error:  # z. B. noch keine Strecke eingerichtet
                    print(f"[FEHLER] {error}")
                except KeyboardInterrupt:
                    print("\nGestoppt.")
            elif command == "f":
                print("Fahre, Strg+C stoppt.")
                try:
                    control.drive(perception)
                except TrackError as error:  # z. B. noch keine Strecke eingerichtet
                    print(f"[FEHLER] {error}")
                except KeyboardInterrupt:
                    print("\nGestoppt.")
            elif command == "q":
                break
    except KeyboardInterrupt:  # Strg+C im Menü beendet
        print()
    finally:
        perception.close()
        close()


if __name__ == "__main__":
    main()
