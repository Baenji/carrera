"""Steuerung: verbindet Wahrnehmung, Agent und Hardware zum Gesamtsystem.

Bisher nur ein Hardware-Test: Das Auto fährt stufenweise schneller.
Aus dem Ordner src/ starten:
  python control.py
"""

from __future__ import annotations

import time

from arduino import close, connect, set_throttle


def main() -> None:
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
    main()
