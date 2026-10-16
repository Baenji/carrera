"""
Künstliche Messfahrt zum Testen ohne Hardware.

Simuliert ein Auto mit bekannten ("wahren") Parametern und schreibt die
Aufzeichnung im selben Format wie record.py, inklusive Kamerarauschen,
verlorener Bilder und Abflug. Damit lässt sich prüfen, ob sysid.py die
wahren Parameter zurückgewinnt.

    python -m carrera_rl.fake_run --out data/fake_run
    python -m carrera_rl.sysid data/fake_run
"""
import argparse
import csv
import json
import os

import numpy as np

from .track import LAYOUT, Track
from .vehicle import VehicleParams, simulate_trajectory

TRUE_PARAMS = VehicleParams(v_max=4200.0, u0=14.0, gamma=1.25, tau_up=0.12, tau_down=0.30,
                            curve_drag=0.08, delay=0.07, a_lat_max=38000.0)


def command_program(rng):
    """probe-artige Rampe + Zufallswechsel, als (Zeit, Gas)-Liste."""
    t, out = 0.0, []
    for u in range(20, 80, 4):          # Rampe: jede Stufe 4 s
        out.append((t, float(u)))
        t += 4.0
    while t < 150.0:                    # Zufallswechsel zwischen 30 und 55 %
        out.append((t, float(rng.choice([30, 38, 46, 55]))))
        t += rng.uniform(0.15, 1.0)
    out.append((t, 0.0))
    return out, t


def write_fake_run(out_dir, params=TRUE_PARAMS, lane="right", fps=30.0, noise_mm=1.5,
                   drop_rate=0.03, seed=0):
    rng = np.random.default_rng(seed)
    track = Track(LAYOUT, lane=lane)
    program, t_end = command_program(rng)
    t_cmd = np.array([p[0] for p in program])
    u_cmd = np.array([p[1] for p in program])

    # Fahrt simulieren; bei Abflug: Auto 2 s später wieder bei s=0 einsetzen
    t_grid, s_grid, on_grid = [], [], []
    crashes, resumes = [], []
    t0, s0 = 0.0, 0.0
    while t0 < t_end:
        t, s, v, a = simulate_trajectory(params, track, t_cmd - t0, u_cmd, t_end - t0, s0=s0)
        t = t + t0
        over = np.nonzero(a > params.a_lat_max)[0]
        if len(over) == 0:
            t_grid.append(t), s_grid.append(s), on_grid.append(np.ones_like(t, bool))
            break
        k = over[0]
        t_grid.append(t[:k]), s_grid.append(s[:k]), on_grid.append(np.ones(k, bool))
        crashes.append((t[k] + 0.3, float(np.mod(s[k], track.length))))  # record.py meldet nach 0.3 s
        t0 = t[k] + 2.0
        resumes.append(t0)
        s0 = 0.0
    t_all = np.concatenate(t_grid)
    s_all = np.concatenate(s_grid)

    # Kamera: Bildzeitpunkte mit Zittern, Rauschen, Aussetzer
    base = np.arange(0.0, t_end, 1.0 / fps)
    t_frames = np.sort(base + rng.normal(0, 0.003, len(base)))
    t_frames = t_frames[t_frames > 0]
    # Bilder zwischen Abflug und Wiedereinsetzen: Auto nicht auf der Spur
    on = np.ones(len(t_frames), bool)
    for (tc, _), tr in zip(crashes, resumes):
        on &= ~((t_frames > tc - 0.3) & (t_frames < tr))
    on &= rng.random(len(t_frames)) > drop_rate
    s_frames = np.interp(t_frames, t_all, s_all) + rng.normal(0, noise_mm, len(t_frames))
    s_frames = np.mod(s_frames, track.length)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump({"layout": track.layout, "lane": lane, "track_length_mm": track.length,
                   "fake": True, "true_params": params.__dict__}, f, indent=2)
    with open(os.path.join(out_dir, "commands.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "u"])
        w.writerows([[f"{t:.4f}", u] for t, u in program])
    with open(os.path.join(out_dir, "frames.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "u", "detected", "px", "py", "s", "lateral"])
        u_at = u_cmd[np.clip(np.searchsorted(t_cmd, t_frames, side="right") - 1, 0, None)]
        for t, u, o, s in zip(t_frames, u_at, on, s_frames):
            w.writerow([f"{t:.4f}", u, int(o), "", "", f"{s:.1f}" if o else "nan", "0.0" if o else "nan"])
    with open(os.path.join(out_dir, "events.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "type", "s", "info"])
        for (tc, sc), tr in zip(crashes, resumes):
            w.writerow([f"{tc:.4f}", "crash", f"{sc:.1f}", ""])
            w.writerow([f"{tr:.4f}", "resume", "", ""])
    return len(crashes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/fake_run")
    ap.add_argument("--lane", default="right", choices=["right", "left"])
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    n = write_fake_run(args.out, lane=args.lane, seed=args.seed)
    print(f"Künstliche Fahrt mit {n} Abflügen geschrieben nach {args.out}")
    print("Wahre Parameter:", TRUE_PARAMS)


if __name__ == "__main__":
    main()
