"""
1D-Fahrzeugmodell eines Slot-Cars.

Das Auto folgt der Spur; der Zustand besteht nur aus Position s und
Geschwindigkeit v. Das Modell hat wenige, physikalisch deutbare Parameter,
die per Systemidentifikation (sysid.py) aus echten Fahrten bestimmt werden:

    u_eff(t) = u(t - delay)                                 Verzögerung
    v_ss(u)  = v_max * clip((u - u0) / (100 - u0), 0, 1)^gamma   Kennlinie
    dv/dt    = (v_ss - v) / tau          tau = tau_up oder tau_down
               - curve_drag * |kappa| * v^2                 Reibung in Kurven
    Abflug, wenn v^2 * |kappa| > a_lat_max

Einheiten: mm, s, Gas u in Prozent (0-100).
"""
import json
from dataclasses import asdict, dataclass, fields

import numpy as np


@dataclass
class VehicleParams:
    v_max: float = 3500.0       # mm/s bei 100 % Gas (Endgeschwindigkeit auf der Geraden)
    u0: float = 15.0            # Totzone: unter diesem Gas bewegt sich das Auto nicht
    gamma: float = 1.0          # Form der Kennlinie (1 = linear)
    tau_up: float = 0.15        # Zeitkonstante Beschleunigen (s)
    tau_down: float = 0.25      # Zeitkonstante Abbremsen (s)
    curve_drag: float = 0.0     # zusätzliche Bremswirkung in Kurven (dimensionslos)
    delay: float = 0.08         # Gesamtverzögerung Kamera + Rechner + Arduino + Motor (s)
    a_lat_max: float = 40000.0  # maximale Querbeschleunigung vor dem Abflug (mm/s^2)

    def v_ss(self, u):
        """Endgeschwindigkeit bei dauerhaft Gas u."""
        x = np.clip((np.asarray(u, dtype=float) - self.u0) / (100.0 - self.u0), 0.0, 1.0)
        return self.v_max * x ** self.gamma

    def save(self, path):
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            data = json.load(f)
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


def step(params, track, s, v, u_eff, dt):
    """
    Ein Zeitschritt (vektorisiert über beliebig viele Autos/Fenster).

    Returns:
        (s, v, a_lat): neue Position, neue Geschwindigkeit, Querbeschleunigung
    """
    kappa = np.abs(track.curvature(s))
    v_target = params.v_ss(u_eff)
    tau = np.where(v_target > v, params.tau_up, params.tau_down)
    dv = (v_target - v) / tau - params.curve_drag * kappa * v * v
    v = np.maximum(v + dv * dt, 0.0)
    s = s + v * dt
    return s, v, v * v * kappa


def command_at(t_cmd, u_cmd, t):
    """Gas zum Zeitpunkt t bei stückweise konstanten Befehlen (Zero-Order-Hold)."""
    i = np.searchsorted(t_cmd, t, side="right") - 1
    return np.where(i >= 0, u_cmd[np.clip(i, 0, len(u_cmd) - 1)], 0.0)


def simulate(params, track, t_cmd, u_cmd, t_start, t_eval, s0, v0, dt=0.002):
    """
    Simuliert mehrere Zeitfenster gleichzeitig.

    Args:
        t_cmd, u_cmd: Befehlszeitpunkte und Gaswerte (gesendet)
        t_start: (n,) Startzeit jedes Fensters
        t_eval: (n, m) Zeitpunkte, zu denen s ausgegeben wird (NaN = ignorieren)
        s0, v0: (n,) Anfangszustand jedes Fensters

    Returns:
        s_eval (n, m), a_lat_max (n,) größte Querbeschleunigung im Fenster
    """
    t_start = np.asarray(t_start, dtype=float)
    t_eval = np.asarray(t_eval, dtype=float)
    s = np.asarray(s0, dtype=float).copy()
    v = np.asarray(v0, dtype=float).copy()
    a_peak = np.zeros_like(s)

    n_steps = int(np.ceil(np.nanmax(t_eval - t_start[:, None]) / dt)) + 1
    s_hist = np.empty((len(s), n_steps + 1))
    s_hist[:, 0] = s
    for k in range(n_steps):
        u = command_at(t_cmd, u_cmd, t_start + k * dt - params.delay)
        s, v, a_lat = step(params, track, s, v, u, dt)
        s_hist[:, k + 1] = s
        a_peak = np.maximum(a_peak, a_lat)

    grid = np.arange(n_steps + 1) * dt
    out = np.full(t_eval.shape, np.nan)
    for i in range(len(s)):
        valid = np.isfinite(t_eval[i])
        out[i, valid] = np.interp(t_eval[i, valid] - t_start[i], grid, s_hist[i])
    return out, a_peak


def simulate_trajectory(params, track, t_cmd, u_cmd, t_end, s0=0.0, v0=0.0, dt=0.002):
    """
    Eine lange Fahrt am Stück (z.B. für künstliche Testdaten).

    Returns:
        t, s, v, a_lat als Arrays auf dem Zeitraster dt
    """
    n = int(np.ceil(t_end / dt))
    t = np.arange(n + 1) * dt
    u = command_at(np.asarray(t_cmd, float), np.asarray(u_cmd, float), t - params.delay)
    s = np.empty(n + 1)
    v = np.empty(n + 1)
    a = np.zeros(n + 1)
    s[0], v[0] = s0, v0
    for k in range(n):
        s[k + 1], v[k + 1], a[k + 1] = step(params, track, s[k], v[k], u[k], dt)
    return t, s, v, a
