"""
Automatische Messfahrt auf der echten Bahn.

Fährt ein Gas-Programm ab und zeichnet mit der Kamera die Position des Autos
auf. Die Aufzeichnung ist die Grundlage für die Systemidentifikation (sysid.py).

Programme:
  probe  Konstantes Gas, alle paar Runden etwas mehr, bis das Auto abfliegt.
         Liefert Endgeschwindigkeit pro Gasstufe UND die Abfluggrenze.
  steps  Sprünge zwischen festen Gasstufen (Beschleunigen/Bremsen, Verzögerung).
  prbs   Zufälliges Umschalten zwischen zwei Stufen (gut für die Verzögerung).

Benutzung (Reihenfolge):
  python -m carrera_rl.record --program probe
  python -m carrera_rl.record --program steps --max-throttle 45
  python -m carrera_rl.record --program prbs --max-throttle 45

--max-throttle bei steps/prbs etwa 5-10 Punkte unter dem Abflugwert aus probe wählen.
Abbrechen jederzeit mit Strg+C (Gas geht auf 0).
"""
import argparse
import csv
import json
import os
import time
from datetime import datetime

import numpy as np

from .camera_calib import CameraCalibration

KEEPALIVE_S = 0.1  # Firmware-Watchdog schaltet nach 0.5 s ohne Befehl ab


# ----------------------------------------------------------------------
# Gas-Programme
# ----------------------------------------------------------------------
class ProbeProgram:
    """Gas schrittweise erhöhen, bis das Auto abfliegt."""

    def __init__(self, start, step, laps_per_level, max_throttle, level_timeout=6.0):
        self.level, self.step = start, step
        self.laps_per_level, self.max = laps_per_level, max_throttle
        self.level_timeout = level_timeout  # falls das Auto in der Totzone steht
        self.laps_at_level = None
        self.t_level = 0.0
        self.last_laps = 0
        self.t_last_lap = 0.0

    def command(self, t, laps):
        if self.laps_at_level is None:
            self.laps_at_level, self.t_level, self.t_last_lap = laps, t, t
        if laps != self.last_laps:
            self.last_laps, self.t_last_lap = laps, t
        stuck = t - self.t_last_lap > self.level_timeout and t - self.t_level > self.level_timeout
        if laps - self.laps_at_level >= self.laps_per_level or stuck:
            self.level += self.step
            self.laps_at_level, self.t_level = laps, t
            print(f"  -> Gas {self.level}")
        return None if self.level > self.max else self.level

    def on_crash(self, t):
        print(f"Abflug bei Gas {self.level}. Probe beendet.")
        return False  # Programm beenden


class StepsProgram:
    """Feste Gasstufen in zufälliger Reihenfolge, jeweils hold Sekunden."""

    def __init__(self, levels, hold, repeats, seed=0):
        rng = np.random.default_rng(seed)
        seq = []
        for _ in range(repeats):
            seq += list(rng.permutation(levels))
        self.times = np.arange(len(seq) + 1) * hold
        self.seq = seq

    def command(self, t, laps):
        i = int(np.searchsorted(self.times, t, side="right") - 1)
        return None if i >= len(self.seq) else float(self.seq[i])

    def on_crash(self, t):
        return True  # nach dem Wiederaufsetzen weitermachen


class PrbsProgram:
    """Zufälliges Umschalten zwischen lo und hi mit zufälliger Haltedauer."""

    def __init__(self, lo, hi, min_hold, max_hold, duration, seed=0):
        rng = np.random.default_rng(seed)
        self.times, self.levels = [0.0], [lo]
        while self.times[-1] < duration:
            self.times.append(self.times[-1] + rng.uniform(min_hold, max_hold))
            self.levels.append(hi if self.levels[-1] == lo else lo)
        self.duration = duration

    def command(self, t, laps):
        if t >= self.duration:
            return None
        return float(self.levels[int(np.searchsorted(self.times, t, side="right") - 1)])

    def on_crash(self, t):
        return True


def make_program(args):
    if args.program == "probe":
        return ProbeProgram(args.probe_start, args.probe_step, args.probe_laps, args.max_throttle)
    lo = args.min_throttle
    if args.program == "steps":
        levels = np.linspace(lo, args.max_throttle, 5).round().tolist()
        return StepsProgram(levels, args.hold, args.repeats, args.seed)
    return PrbsProgram(lo, args.max_throttle, 0.15, 1.0, args.duration, args.seed)


# ----------------------------------------------------------------------
# Messschleife
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--program", choices=["probe", "steps", "prbs"], required=True)
    ap.add_argument("--calib", default="calibration/camera.json")
    ap.add_argument("--out", default="data/runs")
    ap.add_argument("--baud", type=int, default=115200, help="115200 für carrera_pwm_fast, 9600 für alte Firmware")
    ap.add_argument("--port", default=None, help="Serieller Port des Arduino (Standard: automatisch)")
    ap.add_argument("--max-throttle", type=float, default=None, help="Standard: 100 bei probe, sonst 50")
    ap.add_argument("--min-throttle", type=float, default=25)
    ap.add_argument("--probe-start", type=float, default=20)
    ap.add_argument("--probe-step", type=float, default=2)
    ap.add_argument("--probe-laps", type=int, default=3)
    ap.add_argument("--hold", type=float, default=3.0, help="steps: Haltedauer pro Stufe (s)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--duration", type=float, default=120, help="prbs: Dauer (s)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-lateral", type=float, default=40, help="mm Abstand zur Spur, ab dem das Auto als 'neben der Spur' gilt")
    ap.add_argument("--lost-timeout", type=float, default=0.3, help="s ohne Auto auf der Spur = Abflug")
    ap.add_argument("--show", action="store_true", help="Kamerabild anzeigen (kostet Rechenzeit)")
    args = ap.parse_args()
    if args.max_throttle is None:
        args.max_throttle = 100.0 if args.program == "probe" else 50.0

    # Vorhandene Bausteine der Vorgruppe wiederverwenden
    import cv2
    from src.camera import CarTracker, initialize_camera
    from src.hardware.arduino import ArduinoInterface

    calib = CameraCalibration(args.calib)
    track = calib.track
    program = make_program(args)

    run_dir = os.path.join(args.out, datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + args.program)
    os.makedirs(run_dir)
    meta = {"args": vars(args), "layout": track.layout, "lane": track.lane,
            "track_length_mm": track.length, "calibration": calib.data}
    with open(os.path.join(run_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    f_frames = open(os.path.join(run_dir, "frames.csv"), "w", newline="")
    f_cmds = open(os.path.join(run_dir, "commands.csv"), "w", newline="")
    f_events = open(os.path.join(run_dir, "events.csv"), "w", newline="")
    w_frames, w_cmds, w_events = csv.writer(f_frames), csv.writer(f_cmds), csv.writer(f_events)
    w_frames.writerow(["t", "u", "detected", "px", "py", "s", "lateral"])
    w_cmds.writerow(["t", "u"])
    w_events.writerow(["t", "type", "s", "info"])

    cap = initialize_camera()
    if cap is None:
        raise SystemExit("Keine Kamera gefunden")
    arduino = ArduinoInterface(port=args.port, baudrate=args.baud)

    t0 = time.perf_counter()
    now = lambda: time.perf_counter() - t0
    u_sent, t_sent = None, -1.0
    laps, last_s = 0, None
    last_seen = 0.0
    t_pause = 0.0  # Zeit, die durch Wiederaufsetzen vergangen ist (Programm pausiert)
    n_frames = 0

    def send(u):
        nonlocal u_sent, t_sent
        arduino.set_signal_rate(int(round(u)))
        t_sent = now()
        if u != u_sent:
            w_cmds.writerow([f"{t_sent:.4f}", u])
        u_sent = u

    print(f"Aufzeichnung nach {run_dir}. Strg+C zum Abbrechen.")
    try:
        send(0)
        while True:
            ok, frame = cap.read()
            t = now()
            if not ok:
                continue
            n_frames += 1

            pos, _ = CarTracker.find_car(frame)
            s = lateral = np.nan
            on_track = False
            if pos is not None:
                s, lateral = calib.pixel_to_track(*pos)
                on_track = abs(lateral) < args.max_lateral
            if on_track:
                if last_s is not None and s - last_s < -track.length / 2:
                    laps += 1
                last_s, last_seen = s, t

            u = program.command(t - t_pause, laps)
            if u is None:
                print("Programm fertig.")
                break
            u = min(u, args.max_throttle)

            # Abflug: Auto zu lange nicht auf der Spur, obwohl Gas anliegt
            if u > 0 and t - last_seen > args.lost_timeout:
                send(0)
                w_events.writerow([f"{t:.4f}", "crash", f"{last_s if last_s is not None else np.nan:.1f}", u])
                f_events.flush()
                print(f"Abflug erkannt (zuletzt bei s={last_s} mm).")
                if not program.on_crash(t - t_pause):
                    break
                t_wait = now()
                input("Auto auf die Spur setzen und Enter drücken ...")
                for _ in range(10):  # alte Bilder aus dem Kamerapuffer verwerfen
                    cap.read()
                t_pause += now() - t_wait
                w_events.writerow([f"{now():.4f}", "resume", "", ""])
                last_seen, last_s = now(), None
                continue

            if u != u_sent or t - t_sent > KEEPALIVE_S:
                send(u)

            w_frames.writerow([f"{t:.4f}", u_sent, int(on_track),
                               "" if pos is None else pos[0], "" if pos is None else pos[1],
                               f"{s:.1f}", f"{lateral:.1f}"])

            if args.show and n_frames % 3 == 0:
                if pos is not None:
                    cv2.circle(frame, pos, 12, (0, 255, 0) if on_track else (0, 0, 255), 3)
                cv2.putText(frame, f"u={u_sent:.0f} s={s:.0f} lap={laps}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 2)
                cv2.imshow("carrera_rl record", cv2.resize(frame, None, fx=0.5, fy=0.5))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("Abgebrochen.")
    finally:
        arduino.set_signal_rate(0)
        arduino.close()
        cap.release()
        for f in (f_frames, f_cmds, f_events):
            f.close()
        dur = now()
        print(f"{n_frames} Bilder in {dur:.1f} s ({n_frames / max(dur, 1e-9):.1f} fps), {laps} Runden. Daten: {run_dir}")


if __name__ == "__main__":
    main()
