import numpy as np
import pytest

from carrera_rl.track import Track


@pytest.mark.parametrize("lane, length", [("right", 4249.8), ("left", 4607.9)])
def test_track_closes_and_has_expected_length(lane, length):
    track = Track(lane=lane)
    assert track.closure_error < 1e-6
    assert track.length == pytest.approx(length, abs=0.5)


def test_curvature_matches_measured_radii():
    track = Track(lane="right")
    radii = sorted({round(1 / abs(k), 1) for k in track._curv if k != 0})
    assert radii == [142.5, 199.5]


def test_project_roundtrip():
    track = Track()
    for s in np.linspace(0, track.length, 50, endpoint=False):
        x, y = track.position(s)
        s_back, lateral = track.project(float(x), float(y))
        d = (s_back - s + track.length / 2) % track.length - track.length / 2
        assert abs(d) < 1.0 and abs(lateral) < 1.0
