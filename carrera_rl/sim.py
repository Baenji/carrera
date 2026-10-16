"""
Simulationskern für das Training (nur numpy).

Ein Auto auf der Spur, gesteuert mit festem Takt (z.B. 30 Hz). Enthält die
Verzögerung, die Abflug-Erkennung und Rundenzeiten. Für robuste Agenten werden
die Fahrzeugparameter bei jedem reset() zufällig leicht verändert (Domain
Randomization), weil das Modell die echte Bahn nur auf ~5 % genau trifft.
"""
from dataclasses import dataclass, replace

import numpy as np

from .vehicle import VehicleParams, command_at, smooth, step


@dataclass
class Randomization:
    """Bereiche für die zufällige Variation pro Episode (Faktoren oder absolute Werte)."""
    v_scale: tuple = (0.92, 1.08)        # Endgeschwindigkeit
    delay: tuple = (0.10, 0.17)          # s
    tau_scale: tuple = (0.8, 1.25)       # Beschleunigen/Bremsen
    curve_drag_scale: tuple = (0.8, 1.2)
    supply_drop: tuple = (0.10, 0.25)
    a_lat_scale: tuple = (0.90, 1.02)    # leicht vorsichtig
    piece_noise: float = 0.05            # zufälliger Faktor je Streckenteil (Standardabweichung)

    def apply(self, p, n_pieces, rng):
        u = lambda r: rng.uniform(*r)
        return replace(
            p,
            v_max=p.v_max * u(self.v_scale),
            delay=u(self.delay),
            tau_up=p.tau_up * u(self.tau_scale),
            tau_down=p.tau_down * u(self.tau_scale),
            curve_drag=p.curve_drag * u(self.curve_drag_scale),
            supply_drop=u(self.supply_drop),
            a_lat_max=p.a_lat_max * u(self.a_lat_scale),
            piece_factor=list(np.clip(rng.normal(1.0, self.piece_noise, n_pieces), 0.85, 1.15)
                              * (np.asarray(p.piece_factor) if len(p.piece_factor) else 1.0)),
        )


class CarSim:
    """
    Args:
        params: gemessene Fahrzeugparameter (VehicleParams)
        track: Track
        control_dt: Takt des Reglers (s)
        sim_dt: interne Schrittweite der Physik (s)
    """

    def __init__(self, params, track, control_dt=1 / 30, sim_dt=0.002):
        self.base = params
        self.track = track
        self.control_dt = control_dt
        self.n_sub = max(1, int(round(control_dt / sim_dt)))
        self.sim_dt = control_dt / self.n_sub
        self.p = params

    def reset(self, rng, s0=0.0, v0=0.0, randomization=None):
        self.p = randomization.apply(self.base, len(self.track.segments), rng) if randomization else self.base
        self.t = 0.0
        self.s = float(s0)          # abgewickelt (nicht modulo Rundenlänge)
        self.v = float(v0)
        self.u_f = 0.0
        self.t_cmd = [-1.0]         # Befehlsverlauf für die Verzögerung
        self.u_cmd = [0.0]
        self.next_line = (np.floor(self.s / self.track.length) + 1) * self.track.length
        self.t_line = None          # Zeit der letzten Überfahrt der Ziellinie
        self.crashed = False

    def step(self, u):
        """
        Einen Regeltakt mit Gas u (%) fahren.

        Returns:
            dict mit progress (mm), crashed, a_lat (größte Querbeschleunigung), lap_time (oder None)
        """
        self.t_cmd.append(self.t)
        self.u_cmd.append(float(u))
        # nur die Befehle behalten, die wegen der Verzögerung noch wirken können
        keep = max(0, int(np.searchsorted(self.t_cmd, self.t - self.p.delay - 0.5)) - 1)
        del self.t_cmd[:keep], self.u_cmd[:keep]
        t_cmd, u_cmd = np.array(self.t_cmd), np.array(self.u_cmd)

        s_start, a_peak, lap_time = self.s, 0.0, None
        s, v, u_f = np.float64(self.s), np.float64(self.v), self.u_f
        for k in range(self.n_sub):
            t = self.t + k * self.sim_dt
            u_f = smooth(self.p, u_f, float(command_at(t_cmd, u_cmd, t - self.p.delay)), self.sim_dt)
            s, v, a_lat = step(self.p, self.track, s, v, u_f, self.sim_dt)
            a_peak = max(a_peak, float(a_lat))
            if s >= self.next_line:
                t_cross = t + self.sim_dt
                if self.t_line is not None:
                    lap_time = t_cross - self.t_line
                self.t_line = t_cross
                self.next_line += self.track.length
            if a_lat > self.p.a_lat_max:
                self.crashed = True
                break
        self.s, self.v, self.u_f = float(s), float(v), u_f
        self.t += self.control_dt
        return {"progress": self.s - s_start, "crashed": self.crashed, "a_lat": a_peak, "lap_time": lap_time}

    @property
    def s_mod(self):
        return self.s % self.track.length


def run_policy(sim, policy, rng, duration=20.0, randomization=None, s0=0.0):
    """
    Fährt eine Steuerung policy(sim) -> Gas (%) für duration Sekunden.
    Liefert Rundenzeiten und ob das Auto abgeflogen ist.
    """
    sim.reset(rng, s0=s0, randomization=randomization)
    laps = []
    for _ in range(int(duration / sim.control_dt)):
        info = sim.step(policy(sim))
        if info["lap_time"] is not None:
            laps.append(info["lap_time"])
        if info["crashed"]:
            break
    return {"laps": laps, "crashed": sim.crashed, "s": sim.s}
