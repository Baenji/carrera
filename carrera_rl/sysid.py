"""
Systemidentifikation: Fahrzeugparameter aus Messfahrten bestimmen.

Idee: Die Aufzeichnung wird in kurze Zeitfenster (~1 s) zerlegt. Jedes Fenster
startet mit der gemessenen Position und Geschwindigkeit und wird mit den
tatsächlich gesendeten Gasbefehlen simuliert. Die Parameter werden so
angepasst, dass die simulierten Positionen möglichst gut zu den gemessenen
passen. Die Verzögerung wird außen per Suche bestimmt, der Rest per
Least-Squares.

Die Abfluggrenze (a_lat_max) kommt aus den Abflügen der probe-Fahrt.

Benutzung:
    python -m carrera_rl.sysid data/runs/<lauf1> data/runs/<lauf2> ... --out calibration/vehicle.json
"""
import argparse
import csv
import json
import os
from dataclasses import asdict, dataclass, field, replace

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

from .track import Track
from .vehicle import VehicleParams, command_at, simulate

FIT_NAMES = ["v_max", "u0", "gamma", "tau_up", "tau_down", "curve_drag", "curve_exp", "supply_drop", "tau_u"]
LOWER = [300.0, 0.0, 0.2, 0.01, 0.01, 0.0, 0.0, 0.0, 0.0]
UPPER = [10000.0, 60.0, 3.0, 2.0, 3.0, 3.0, 4.0, 0.6, 1.0]


@dataclass
class Run:
    track: Track
    t: np.ndarray            # Bildzeitpunkte (s)
    s: np.ndarray            # gemessene Position (mm, 0..Rundenlänge), NaN wenn nicht erkannt
    on_track: np.ndarray     # bool
    t_cmd: np.ndarray        # Befehlszeitpunkte
    u_cmd: np.ndarray        # Gas (%)
    crashes: list = field(default_factory=list)   # [(t, s_last)]
    resumes: list = field(default_factory=list)   # [t]
    name: str = ""


def load_run(run_dir, calib=None, max_lateral=40.0):
    """
    Liest eine mit record.py aufgezeichnete Fahrt.

    Ist calib (CameraCalibration) angegeben, werden die Positionen aus den
    gespeicherten Pixeln neu berechnet, z.B. nach einer Parallaxe-Korrektur.
    """
    with open(os.path.join(run_dir, "meta.json")) as f:
        meta = json.load(f)
    track = Track(meta["layout"], lane=meta["lane"])

    def read(name):
        with open(os.path.join(run_dir, name)) as f:
            return list(csv.DictReader(f))

    frames = read("frames.csv")
    cmds = read("commands.csv")
    events = read("events.csv")
    num = lambda x: float(x) if x not in ("", "nan") else np.nan
    if calib is not None and any(r["px"] for r in frames):  # künstliche Fahrten haben keine Pixel
        px = np.array([[num(r["px"]), num(r["py"])] for r in frames])
        ok = np.isfinite(px).all(1) & np.array([r["detected"] == "1" for r in frames])
        s_new = np.full(len(frames), np.nan)
        lat = np.full(len(frames), np.nan)
        if ok.any():
            s_new[ok], lat[ok] = calib.pixels_to_track(px[ok])
        for r, sv, ok_i in zip(frames, s_new, ok & (np.abs(lat) < max_lateral)):
            r["s"], r["detected"] = (f"{sv}" if ok_i else "nan"), ("1" if ok_i else "0")
    return Run(
        track=track,
        t=np.array([num(r["t"]) for r in frames]),
        s=np.array([num(r["s"]) for r in frames]),
        on_track=np.array([r["detected"] == "1" for r in frames]),
        t_cmd=np.array([num(r["t"]) for r in cmds]),
        u_cmd=np.array([num(r["u"]) for r in cmds]),
        crashes=[(num(r["t"]), num(r["s"])) for r in events if r["type"] == "crash"],
        resumes=[num(r["t"]) for r in events if r["type"] == "resume"],
        name=os.path.basename(os.path.normpath(run_dir)),
    )


# ----------------------------------------------------------------------
# Datenaufbereitung
# ----------------------------------------------------------------------
def continuous_segments(run, max_gap=0.12, crash_margin=0.4, lost_timeout=0.3):
    """
    Zusammenhängende Stücke, in denen das Auto auf der Spur erkannt wurde.
    Die Zeit kurz vor einem Abflug wird weggelassen (das Auto rutscht bereits).
    Ein Abflug wird erst lost_timeout nach dem Verlassen der Spur protokolliert.
    Liefert Liste von (Indexarray, abgewickelte Position s_unwrapped).
    """
    ok = run.on_track & np.isfinite(run.s)
    for t_c, _ in run.crashes:
        ok &= ~((run.t > t_c - lost_timeout - crash_margin) & (run.t <= t_c))
    idx = np.nonzero(ok)[0]
    if len(idx) == 0:
        return []
    breaks = np.nonzero(np.diff(run.t[idx]) > max_gap)[0]
    cuts = sorted(set(np.searchsorted(run.t[idx], run.resumes)) | set(breaks + 1))
    out = []
    for part in np.split(idx, cuts):
        if len(part) < 8:
            continue
        s = run.s[part]
        ds = np.diff(s)
        L = run.track.length
        ds = np.where(ds < -L / 2, ds + L, ds)
        ds = np.where(ds > L / 2, ds - L, ds)
        out.append((part, s[0] + np.concatenate([[0.0], np.cumsum(ds)])))
    return out


def local_velocity(t, s, half=3):
    """Geschwindigkeit per lokaler linearer Regression über ±half Bilder."""
    v = np.full(len(t), np.nan)
    for i in range(len(t)):
        a, b = max(0, i - half), min(len(t), i + half + 1)
        if b - a >= 3:
            v[i] = np.polyfit(t[a:b] - t[i], s[a:b], 1)[0]
    return v


def make_windows(run, window=1.2, stride=0.6, n_init=5, min_throttle=26.0):
    """
    Zeitfenster für die Anpassung: Startzustand + Messpunkte.
    Fenster, in denen das Gas unter min_throttle liegt, werden übersprungen: dort
    ruckelt das Auto (Haftreibung, Schienenübergänge), und zum Rennen ist der
    Bereich ohnehin irrelevant.
    """
    starts, evals, meas, s0s, v0s = [], [], [], [], []
    for part, s_unw in continuous_segments(run):
        t = run.t[part]
        i = 0
        while i + n_init < len(t):
            j = np.searchsorted(t, t[i] + window, side="right")
            if j - i < n_init + 5:
                break
            u_win = command_at(run.t_cmd, run.u_cmd, t[i:j] - 0.3)  # inkl. Vorlauf (Verzögerung)
            if u_win.min() < min_throttle:
                i = np.searchsorted(t, t[i] + stride)
                continue
            # Startzustand: quadratischer Fit über die ersten Bilder
            tt = t[i:i + n_init] - t[i]
            c = np.polyfit(tt, s_unw[i:i + n_init], 2)
            starts.append(t[i])
            s0s.append(c[2])
            v0s.append(max(c[1], 0.0))
            evals.append(t[i + 1:j])
            meas.append(s_unw[i + 1:j])
            i = np.searchsorted(t, t[i] + stride)
    if not starts:
        return None
    m = max(len(e) for e in evals)
    pad = lambda arrs: np.array([np.pad(a, (0, m - len(a)), constant_values=np.nan) for a in arrs])
    return dict(t_start=np.array(starts), t_eval=pad(evals), s_meas=pad(meas),
                s0=np.array(s0s), v0=np.array(v0s))


# ----------------------------------------------------------------------
# Anpassung
# ----------------------------------------------------------------------
def residuals(theta, delay, data, base, dt):
    params = replace(base, delay=delay, **dict(zip(FIT_NAMES, theta)))
    res = []
    for run, w in data:
        s_sim, _ = simulate(params, run.track, run.t_cmd, run.u_cmd,
                            w["t_start"], w["t_eval"], w["s0"], w["v0"], dt=dt)
        r = (s_sim - w["s_meas"])
        res.append(r[np.isfinite(r)])
    return np.concatenate(res)


def fit_params(runs, base=None, dt=0.004, delay_range=(0.0, 0.3), verbose=True):
    """
    Passt die Fahrzeugparameter an alle Fahrten gemeinsam an.

    Returns:
        (VehicleParams, info-dict)
    """
    base = base or VehicleParams()
    data = []
    for run in runs:
        w = make_windows(run)
        if w is not None:
            data.append((run, w))
    if not data:
        raise RuntimeError("Keine verwertbaren Fenster in den Daten (Auto nie erkannt?)")
    n_windows = sum(len(w["t_start"]) for _, w in data)

    theta = np.array([getattr(base, n) for n in FIT_NAMES])
    theta = np.clip(theta, LOWER, UPPER)
    cache = {}

    def inner(delay):
        nonlocal theta
        sol = least_squares(residuals, theta, args=(delay, data, base, dt),
                            bounds=(LOWER, UPPER), x_scale="jac", loss="soft_l1", f_scale=10.0,
                            max_nfev=60)
        theta = sol.x  # Warmstart für die nächste Verzögerung
        rms = float(np.sqrt(np.mean(sol.fun ** 2)))
        cache[delay] = (rms, sol.x.copy())
        if verbose:
            print(f"  delay={delay * 1000:5.1f} ms  RMS={rms:6.2f} mm")
        return rms

    # grobe Suche, dann fein
    grid = np.arange(delay_range[0], delay_range[1] + 1e-9, 0.04)
    rms = [inner(d) for d in grid]
    k = int(np.argmin(rms))
    lo, hi = grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]
    theta = cache[grid[k]][1]
    minimize_scalar(inner, bounds=(lo, hi), method="bounded", options={"xatol": 0.003})

    best_delay = min(cache, key=lambda d: cache[d][0])
    best_rms, best_theta = cache[best_delay]
    params = replace(base, delay=float(best_delay), **{n: float(v) for n, v in zip(FIT_NAMES, best_theta)})
    info = {"rms_mm": best_rms, "n_windows": n_windows, "n_runs": len(data)}
    return params, info


PIECE_STAGE_NAMES = ["tau_up", "tau_down", "curve_drag", "curve_exp", "tau_u"]


def fit_piece_factors(runs, params, dt=0.004, verbose=True):
    """
    Zweite Stufe: ein Korrekturfaktor je Streckenteil (plus Dynamik-Parameter),
    bei fester Verzögerung, Kennlinie und Spannungsabfall.
    """
    data = [(run, w) for run in runs if (w := make_windows(run)) is not None]
    n_pieces = len(runs[0].track.segments)
    lo = [LOWER[FIT_NAMES.index(n)] for n in PIECE_STAGE_NAMES] + [0.6] * n_pieces
    hi = [UPPER[FIT_NAMES.index(n)] for n in PIECE_STAGE_NAMES] + [1.4] * n_pieces
    x0 = [getattr(params, n) for n in PIECE_STAGE_NAMES] + list(params.piece_factor or [1.0] * n_pieces)

    def unpack(x):
        return replace(params, piece_factor=[float(v) for v in x[len(PIECE_STAGE_NAMES):]],
                       **{n: float(v) for n, v in zip(PIECE_STAGE_NAMES, x)})

    def res(x):
        p = unpack(x)
        out = []
        for run, w in data:
            s_sim, _ = simulate(p, run.track, run.t_cmd, run.u_cmd, w["t_start"], w["t_eval"], w["s0"], w["v0"], dt=dt)
            r = s_sim - w["s_meas"]
            out.append(r[np.isfinite(r)])
        return np.concatenate(out)

    sol = least_squares(res, np.clip(x0, lo, hi), bounds=(lo, hi), x_scale="jac", loss="soft_l1",
                        f_scale=10.0, max_nfev=40, verbose=0)
    rms = float(np.sqrt(np.mean(sol.fun ** 2)))
    if verbose:
        print(f"  mit Streckenteil-Faktoren: RMS={rms:6.2f} mm")
    return unpack(sol.x), rms


def estimate_crash_limit(runs):
    """
    Querbeschleunigung bei Abflügen und höchste überlebte Querbeschleunigung.
    Die echte Grenze liegt dazwischen.
    """
    survived, crashed = [], []
    for run in runs:
        L = run.track.length
        for part, s_unw in continuous_segments(run):
            v = local_velocity(run.t[part], s_unw)
            a = v ** 2 * np.abs(run.track.curvature(s_unw))
            survived.append(a[np.isfinite(a)])
        for t_c, s_last in run.crashes:
            m = run.on_track & np.isfinite(run.s) & (run.t < t_c) & (run.t > t_c - 1.5)
            idx = np.nonzero(m)[0][-8:]
            if len(idx) < 4 or not np.isfinite(s_last):
                continue
            s = run.s[idx]
            s = s + L * np.cumsum(np.concatenate([[0], np.diff(s) < -L / 2]))
            # Geschwindigkeit im letzten Bild (nicht Mittelwert): das Auto beschleunigt oft noch
            tt = run.t[idx] - run.t[idx[-1]]
            v = np.polyfit(tt, s, 2)[1]
            # Das Auto fliegt beim Einlenken: größte Krümmung kurz vor/nach der letzten Position
            k = np.abs(run.track.curvature(s_last + np.linspace(-30, 150, 40))).max()
            crashed.append(float(v * v * k))
    survived = np.concatenate(survived) if survived else np.array([])
    out = {
        "a_lat_survived_p999": float(np.percentile(survived, 99.9)) if len(survived) else None,
        "a_lat_crashes": sorted(crashed),
    }
    if crashed:
        # Ein Abflug passiert beim Einfahren in die Kurve; die gemessene Belastung liegt
        # also immer ÜBER der Grenze (je nachdem, wie schnell das Auto ankam). Der kleinste
        # Abflugwert ist daher die beste Schätzung, die höchste überlebte Belastung die
        # untere Schranke.
        est = float(min(crashed))
        if out["a_lat_survived_p999"] is not None:
            est = max(est, out["a_lat_survived_p999"])
        out["a_lat_max_estimate"] = est
    return out


def held_levels(run, min_laps=1.0):
    """Gasstufen, die mindestens min_laps Runden lang konstant gehalten wurden (ohne Abflug)."""
    L = run.track.length
    out = []
    for part, s_unw in continuous_segments(run):
        t = run.t[part]
        u = command_at(run.t_cmd, run.u_cmd, t)
        for lvl in np.unique(u):
            m = u == lvl
            if m.sum() > 2 and (s_unw[m].max() - s_unw[m].min()) >= min_laps * L:
                out.append(float(lvl))
    return sorted(set(out))


def peak_lateral(params, track, u, laps=3):
    """Größte Querbeschleunigung des Modells bei konstantem Gas u (nach dem Einschwingen)."""
    from .vehicle import simulate_trajectory
    p = replace(params, a_lat_max=np.inf)
    t, s, v, a = simulate_trajectory(p, track, [0.0], [u], t_end=laps * track.length / max(p.v_ss(u), 300.0) + 3.0)
    return float(a[s > s[-1] - track.length].max())  # letzte Runde


def estimate_crash_limit_model(runs, params):
    """
    Abfluggrenze so, dass das MODELL bei denselben konstanten Gasstufen überlebt bzw.
    abfliegt wie das echte Auto. Damit passt die Grenze zu den Geschwindigkeiten des
    Modells (auch dort, wo das Modell etwas zu schnell oder zu langsam ist).
    """
    survived, crashed = [], []
    for run in runs:
        survived += held_levels(run)
        for t_c, _ in run.crashes:
            crashed.append(float(command_at(run.t_cmd, run.u_cmd, np.array([t_c - 0.4]))[0]))
    if not survived:
        return {}
    track = runs[0].track
    u_s = max(survived)
    a_s = peak_lateral(params, track, u_s)
    out = {"survived_throttle": u_s, "a_lat_model_survived": a_s}
    crashed = [u for u in crashed if u > u_s]
    if crashed:
        u_c = min(crashed)
        a_c = peak_lateral(params, track, u_c)
        out.update(crash_throttle=u_c, a_lat_model_crash=a_c, a_lat_max_estimate=0.5 * (a_s + a_c))
    else:
        out["a_lat_max_estimate"] = 1.02 * a_s  # nur untere Schranke bekannt
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="Ordner aus data/runs/")
    ap.add_argument("--out", default="calibration/vehicle.json")
    ap.add_argument("--plot", action="store_true", help="Vergleich Messung/Simulation als PNG speichern")
    ap.add_argument("--piece-factors", action="store_true",
                    help="zusätzlich einen Korrekturfaktor je Streckenteil anpassen (braucht mehrere Fahrten)")
    ap.add_argument("--calib", default="calibration/camera.json",
                    help="Positionen mit dieser Kamera-Kalibrierung neu berechnen ('' = gespeicherte Werte nutzen)")
    args = ap.parse_args()

    calib = None
    if args.calib and os.path.exists(args.calib):
        from .camera_calib import CameraCalibration
        calib = CameraCalibration(args.calib)
    runs = [load_run(r, calib) for r in args.runs]
    print(f"{len(runs)} Fahrten geladen. Passe Parameter an ...")
    params, info = fit_params(runs)
    if args.piece_factors:
        params, info["rms_mm"] = fit_piece_factors(runs, params)
    crash = estimate_crash_limit_model(runs, params)
    crash["from_last_frames"] = estimate_crash_limit(runs)  # alte Methode, nur zur Info
    if crash.get("a_lat_max_estimate"):
        params = replace(params, a_lat_max=crash["a_lat_max_estimate"])
    else:
        print("WARNUNG: keine konstant gefahrene Gasstufe gefunden, a_lat_max bleibt auf dem Standardwert. probe-Fahrt aufnehmen!")
    if "crash_throttle" not in crash:
        print("Hinweis: kein Abflug oberhalb der gehaltenen Stufen, a_lat_max ist nur eine untere Schranke.")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    params.save(args.out)
    report = {"params": asdict(params), "fit": info, "crash": crash, "runs": [r.name for r in runs]}
    with open(os.path.splitext(args.out)[0] + "_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\nErgebnis:")
    for k, v in asdict(params).items():
        print(f"  {k:12s} = " + (" ".join(f"{x:.2f}" for x in v) if isinstance(v, list) else f"{v:.4g}"))
    print(f"  Restfehler (RMS) = {info['rms_mm']:.1f} mm über {info['n_windows']} Fenster")
    print("  Endgeschwindigkeit: " + ", ".join(f"{u}%: {params.v_ss(u) / 1000:.2f} m/s" for u in (30, 50, 70, 100)))
    if args.plot:
        plot_fit(runs[0], params, os.path.splitext(args.out)[0] + "_fit.png")
    print(f"\nGespeichert: {args.out}")


def plot_fit(run, params, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w = make_windows(run, window=2.0, stride=2.0)
    s_sim, _ = simulate(params, run.track, run.t_cmd, run.u_cmd, w["t_start"], w["t_eval"], w["s0"], w["v0"])
    fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    for i in range(min(len(w["t_start"]), 40)):
        m = np.isfinite(w["t_eval"][i])
        ax[0].plot(w["t_eval"][i, m], w["s_meas"][i, m] - w["s0"][i], "k.", ms=2)
        ax[0].plot(w["t_eval"][i, m], s_sim[i, m] - w["s0"][i], "r-", lw=1)
    ax[0].set_ylabel("Weg im Fenster (mm)")
    ax[0].set_title("schwarz = Messung, rot = Simulation")
    ax[1].step(run.t_cmd, run.u_cmd, where="post")
    ax[1].set_ylabel("Gas (%)")
    ax[1].set_xlabel("Zeit (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


if __name__ == "__main__":
    main()
