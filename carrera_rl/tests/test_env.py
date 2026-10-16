"""Grundprüfungen der RL-Umgebung (übersprungen, wenn gymnasium fehlt)."""
import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")

from carrera_rl.env import CarreraEnv  # noqa: E402
from carrera_rl.vehicle import VehicleParams  # noqa: E402

PARAMS = VehicleParams(v_max=5200, u0=25, gamma=0.37, tau_up=0.26, tau_down=0.29, curve_drag=0.4,
                       curve_exp=1.3, supply_drop=0.17, delay=0.135, a_lat_max=46000)


def test_env_api():
    from gymnasium.utils.env_checker import check_env
    check_env(CarreraEnv(vehicle=PARAMS), skip_render_check=True)


def test_full_throttle_crashes_and_zero_throttle_stands_still():
    env = CarreraEnv(vehicle=PARAMS, randomize=False)
    env.reset(seed=0, options={"s0": 0.0})
    for _ in range(env.max_steps):
        _, r, term, trunc, _ = env.step(np.array([1.0]))  # 50 % Gas: oberhalb der Abfluggrenze
        if term or trunc:
            break
    assert term and r < 0

    env.reset(seed=0)
    total = sum(env.step(np.array([-1.0]))[1] for _ in range(30))
    assert total == pytest.approx(0.0, abs=1e-6)
