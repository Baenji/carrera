"""Prüft, ob die Systemidentifikation bekannte Parameter aus einer künstlichen Fahrt zurückgewinnt."""
import pytest

from carrera_rl.fake_run import TRUE_PARAMS, write_fake_run
from carrera_rl.sysid import estimate_crash_limit, fit_params, load_run


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    path = tmp_path_factory.mktemp("fake")
    write_fake_run(str(path), seed=1)
    return load_run(str(path))


def test_fit_recovers_true_params(run):
    params, info = fit_params([run], verbose=False)
    assert params.delay == pytest.approx(TRUE_PARAMS.delay, abs=0.01)
    assert params.v_max == pytest.approx(TRUE_PARAMS.v_max, rel=0.05)
    assert params.u0 == pytest.approx(TRUE_PARAMS.u0, abs=1.0)
    assert params.tau_up == pytest.approx(TRUE_PARAMS.tau_up, rel=0.15)
    assert params.tau_down == pytest.approx(TRUE_PARAMS.tau_down, rel=0.15)
    assert info["rms_mm"] < 10


def test_crash_limit_estimate(run):
    crash = estimate_crash_limit([run])
    assert crash["a_lat_max_estimate"] == pytest.approx(TRUE_PARAMS.a_lat_max, rel=0.08)
