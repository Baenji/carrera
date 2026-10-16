"""
RL-Trainingsumgebung (Gymnasium) für die Carrera-Bahn.

Der Agent entscheidet 30-mal pro Sekunde über das Gas.

Beobachtung (alles grob auf -1..1 skaliert):
  - Geschwindigkeit (gemessen, mit Rauschen)
  - Position in der Runde als sin/cos (für ortsabhängige Effekte wie den Spannungsabfall)
  - Vorschau: Krümmung der Spur 0 bis 800 mm voraus (|1/r| * 171 mm, 0 = Gerade)
  - die letzten Aktionen (wegen der Verzögerung von ~135 ms sind sie noch "unterwegs")

Aktion: eine Zahl -1..1 -> Gas 0..u_max %.
Belohnung: zurückgelegte Strecke (je 100 mm = 1), beim Abflug -crash_penalty und Ende der Episode.
Jede Episode startet im Stand an einer zufälligen Stelle, mit zufällig variierten
Fahrzeugparametern (siehe sim.Randomization).
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .sim import CarSim, Randomization
from .track import Track
from .vehicle import R_REF, VehicleParams

LOOKAHEAD_MM = (0, 50, 100, 150, 200, 300, 400, 500, 600, 800)
V_REF = 2500.0  # mm/s, zur Skalierung


class CarreraEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, vehicle="calibration/vehicle.json", lane="right", control_hz=30.0, u_max=50.0,
                 episode_s=12.0, randomize=True, crash_penalty=20.0, n_past_actions=6,
                 obs_noise_v=0.03, obs_noise_s=3.0, random_start=True):
        params = VehicleParams.load(vehicle) if isinstance(vehicle, str) else vehicle
        self.track = Track(lane=lane)
        self.sim = CarSim(params, self.track, control_dt=1.0 / control_hz)
        self.randomization = Randomization() if randomize is True else (randomize or None)
        self.u_max = u_max
        self.max_steps = int(round(episode_s * control_hz))
        self.crash_penalty = crash_penalty
        self.n_past = n_past_actions
        self.obs_noise_v, self.obs_noise_s = obs_noise_v, obs_noise_s
        self.random_start = random_start
        self.lookahead = np.asarray(LOOKAHEAD_MM, dtype=float)

        n_obs = 1 + 2 + len(self.lookahead) + self.n_past
        self.observation_space = spaces.Box(-10.0, 10.0, (n_obs,), np.float32)  # alle Werte liegen etwa in -2..2
        self.action_space = spaces.Box(-1.0, 1.0, (1,), np.float32)

    def throttle(self, action):
        """Aktion -1..1 -> Gas 0..u_max %."""
        return (float(np.clip(action, -1.0, 1.0)) + 1.0) / 2.0 * self.u_max

    def _obs(self):
        rng = self.np_random
        v = self.sim.v * (1.0 + rng.normal(0.0, self.obs_noise_v))
        s = self.sim.s + rng.normal(0.0, self.obs_noise_s)
        phase = 2 * np.pi * (s % self.track.length) / self.track.length
        kappa = np.abs(self.track.curvature(s + self.lookahead)) * R_REF
        return np.concatenate([[v / V_REF, np.sin(phase), np.cos(phase)], kappa, self.past]).astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        options = options or {}
        s0 = options.get("s0", self.np_random.uniform(0, self.track.length) if self.random_start else 0.0)
        self.sim.reset(self.np_random, s0=s0, randomization=self.randomization)
        self.past = np.full(self.n_past, -1.0)  # Gas 0
        self.steps = 0
        return self._obs(), {}

    def step(self, action):
        a = float(np.clip(np.asarray(action, dtype=float).reshape(-1)[0], -1.0, 1.0))
        u = self.throttle(a)
        info = self.sim.step(u)
        self.past = np.roll(self.past, 1)
        self.past[0] = a
        self.steps += 1

        reward = info["progress"] / 100.0
        terminated = bool(info["crashed"])
        if terminated:
            reward -= self.crash_penalty
        truncated = self.steps >= self.max_steps
        return self._obs(), float(reward), terminated, truncated, {
            "lap_time": info["lap_time"], "crashed": terminated, "throttle": u,
            "v": self.sim.v, "s": self.sim.s_mod,
        }
