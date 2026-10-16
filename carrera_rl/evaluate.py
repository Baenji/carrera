"""
Auswertung eines trainierten Agenten in der Simulation.

Vergleicht mit der besten konstanten Gasstufe (Messlatte) und zeigt, wo der
Agent bremst und beschleunigt.

    python -m carrera_rl.evaluate models_rl/sac_v1/best_model.zip
"""
import argparse
import json
import os

import numpy as np

from .env import CarreraEnv
from .sim import CarSim, Randomization, run_policy


def drive(env, act, episodes, seed=0, duration_s=20.0):
    """Fährt mit act(obs) -> Aktion. Liefert Rundenzeiten (ohne erste Runde), Abflugrate, Verlauf der ersten Episode."""
    env.max_steps = int(duration_s / env.sim.control_dt)
    laps, crashes, trace = [], 0, []
    for ep in range(episodes):
        obs, _ = env.reset(seed=seed + ep, options={"s0": 0.0})
        ep_laps = []
        done = False
        while not done:
            obs, _, term, trunc, info = env.step(act(obs))
            done = term or trunc
            if info["lap_time"] is not None:
                ep_laps.append(info["lap_time"])
            if ep == 0:
                trace.append((info["s"], info["v"], info["throttle"]))
        crashes += int(term)
        laps += ep_laps[1:]  # erste vollständige Runde startet aus dem Stand
    return np.array(laps), crashes / episodes, np.array(trace)


def best_constant(env, levels=range(30, 51)):
    """Schnellste konstante Gasstufe ohne Abflug im nominalen Modell."""
    sim = CarSim(env.sim.base, env.track, control_dt=env.sim.control_dt)
    best = None
    for u in levels:
        r = run_policy(sim, lambda _s, u=u: u, np.random.default_rng(0), duration=15.0)
        if not r["crashed"] and len(r["laps"]) > 1:
            best = (u, float(np.mean(r["laps"][1:])))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--episodes", type=int, default=30)
    ap.add_argument("--plot", default=None, help="PNG mit Geschwindigkeit/Gas entlang der Runde")
    args = ap.parse_args()

    from stable_baselines3 import PPO, SAC
    model_dir = os.path.dirname(args.model)
    with open(os.path.join(model_dir, "config.json")) as f:
        cfg = json.load(f)
    algo = SAC if cfg["args"]["algo"] == "sac" else PPO
    model = algo.load(args.model)
    act = lambda obs: model.predict(obs, deterministic=True)[0]

    kw = {**cfg["env_kwargs"]}
    nominal = CarreraEnv(**{**kw, "randomize": False})
    varied = CarreraEnv(**{**kw, "randomize": True})

    u_c, lap_c = best_constant(nominal)
    print(f"Messlatte: konstant {u_c:.0f} % -> {lap_c:.3f} s pro Runde (Modell; echt bei 44 %: 2.36 s)")
    for name, env in (("nominal", nominal), ("mit Zufallsvariation", varied)):
        laps, crash_rate, trace = drive(env, act, 1 if name == "nominal" else args.episodes)
        lap = f"{laps.mean():.3f} s (min {laps.min():.3f})" if len(laps) else "keine Runde"
        print(f"Agent {name:22s}: Runde {lap}, Abflugrate {crash_rate * 100:.0f} %")
        if name == "nominal":
            nominal_trace = trace

    plot = args.plot or os.path.join(model_dir, "evaluation.png")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s, v, u = nominal_trace[:, 0], nominal_trace[:, 1], nominal_trace[:, 2]
    lap2 = np.nonzero(np.diff(s) < -1000)[0]
    if len(lap2) >= 2:
        sl = slice(lap2[0] + 1, lap2[1] + 1)
        s, v, u = s[sl], v[sl], u[sl]
    fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    for seg in nominal.track.segments:
        if seg.curvature != 0:
            for a in ax:
                a.axvspan(seg.s0, seg.s0 + seg.length, color="0.9" if seg.piece == "R" else "#ffe9c9")
    ax[0].plot(s, v / 1000, "k-")
    ax[0].set_ylabel("Geschwindigkeit (m/s)")
    ax[1].step(s, u, "b-", where="post")
    ax[1].axhline(u_c, color="r", ls="--", lw=0.8, label=f"beste Konstante {u_c:.0f} %")
    ax[1].set_ylabel("Gas (%)")
    ax[1].set_xlabel("Position s (mm)   grau = Rechtskurve, orange = Linkskurve")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(plot, dpi=110)
    print(f"Verlauf einer Runde: {plot}")


if __name__ == "__main__":
    main()
