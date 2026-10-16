"""
Kamera-Kalibrierung: Kamerapixel -> Position auf der Spur.

Ablauf (einmal pro Kameraposition):
  1. AprilTags erkennen. Alle Tags sind gleich große Quadrate auf dem Tisch,
     daraus lässt sich die Perspektive (Homographie) berechnen.
  2. Streckenmodell grob einpassen: jedes Streckenteil trägt einen Tag,
     dessen ID den Teiltyp verrät.
  3. Feinjustierung: das Modell wird so verschoben/verzerrt, dass die
     Modell-Schienen genau auf den hellen Schienen im Bild liegen.

Ergebnis ist eine 3x3-Matrix (Streckenmodell in mm -> Bildpixel), gespeichert
als JSON. Wird die Kamera bewegt, muss neu kalibriert werden.

Benutzung:
    python -m carrera_rl.camera_calib --image bild.jpg --out calibration/camera.json
    python -m carrera_rl.camera_calib --camera --out calibration/camera.json
"""
import argparse
import json

import cv2
import numpy as np
from scipy.optimize import least_squares, linear_sum_assignment, minimize

from .track import LANE_OFFSET, LAYOUT, Track

# Tag-ID -> mögliche Teile-Codes (siehe src/config.py, TAG_MAP)
TAG_TO_PIECES = {1: {"S"}, 2: {"g"}, 3: {"M"}, 4: {"G"}, 5: {"R", "L"}}
TAG_FAMILY = cv2.aruco.DICT_APRILTAG_16h5


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def apply_h(h, pts):
    pts = np.asarray(pts, dtype=float)
    p = np.c_[pts, np.ones(len(pts))] @ h.T
    return p[:, :2] / p[:, 2:]


def detect_tags(gray):
    """Liefert [(id, corners(4x2))] aller erkannten AprilTags."""
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(TAG_FAMILY), params)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return []
    return [(int(i), c.reshape(4, 2).astype(float)) for c, i in zip(corners, ids.flatten())]


def fit_plane_homography(tags):
    """
    Homographie Tischebene -> Bild aus der Bedingung, dass alle Tags gleich
    große Quadrate sind. Einheit der Tischebene: eine Tag-Seitenlänge.

    Returns:
        (H, centers, rms): H bildet Tischebene auf Bild ab, centers sind die
        Tag-Mittelpunkte in der Tischebene, rms der Restfehler in Pixeln.
    """
    if len(tags) < 4:
        raise RuntimeError(f"Zu wenige AprilTags erkannt ({len(tags)}), mindestens 4 nötig")
    corners = [c for _, c in tags]
    off = np.array([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]])

    def angle(c):
        v = c[1] - c[0]
        return np.arctan2(v[1], v[0])

    # Startwert: Ähnlichkeitsabbildung aus dem ersten Tag
    c0 = corners[0].mean(0)
    scale = np.mean([np.linalg.norm(c[1] - c[0]) for c in corners])
    th0 = angle(corners[0])
    rot = np.array([[np.cos(th0), -np.sin(th0)], [np.sin(th0), np.cos(th0)]])
    h0 = np.eye(3)
    h0[:2, :2] = scale * rot
    h0[:2, 2] = c0
    x0 = list(h0.ravel()[:8])
    for c in corners[1:]:
        x0 += list(((c.mean(0) - c0) / scale) @ rot) + [angle(c) - th0]

    def unpack(x):
        h = np.append(x[:8], 1.0).reshape(3, 3)
        poses = np.vstack([[0.0, 0.0, 0.0], np.reshape(x[8:], (-1, 3))])  # Tag 0 fixiert
        return h, poses

    def residual(x):
        h, poses = unpack(x)
        res = []
        for c, (tx, ty, th) in zip(corners, poses):
            r = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
            res.append((apply_h(h, off @ r.T + [tx, ty]) - c).ravel())
        return np.concatenate(res)

    sol = least_squares(residual, np.array(x0), x_scale="jac")
    h, poses = unpack(sol.x)
    rms = float(np.sqrt(np.mean(sol.fun ** 2)))
    return h, poses[:, :2], rms


def umeyama_rotation(src, dst):
    """Ähnlichkeitsabbildung (Skala, Rotation, Translation) src -> dst ohne Spiegelung."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    u, sig, vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(u @ vt))
    r = u @ np.diag([1, d]) @ vt
    s = (sig * [1, d]).sum() / (a ** 2).sum()
    return s, r, md - s * r @ ms


def initial_alignment(track, tags, tag_centers):
    """
    Grobe Zuordnung Streckenmodell (mm) -> Tischebene über Tag-Typen.
    Probiert alle Drehungen und beide Spiegelungen durch (Bild hat y nach unten).
    """
    pieces = track.piece_centers()
    model = np.array([[x, y] for x, y, _ in pieces])
    codes = [p for _, _, p in pieces]
    tag_ids = [i for i, _ in tags]
    penalty = np.array([[0.0 if code in TAG_TO_PIECES.get(tid, set()) else 1e6
                         for code in codes] for tid in tag_ids])

    best = None
    for flip in (1.0, -1.0):
        m = model * [1.0, flip]
        for theta in np.deg2rad(np.arange(0, 360, 10)):
            r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
            s = np.sqrt(((tag_centers - tag_centers.mean(0)) ** 2).sum(1).mean()
                        / ((m - m.mean(0)) ** 2).sum(1).mean())
            t = tag_centers.mean(0) - s * r @ m.mean(0)
            for _ in range(10):
                proj = (s * (r @ m.T)).T + t
                cost = ((tag_centers[:, None, :] - proj[None]) ** 2).sum(2) + penalty
                ri, ci = linear_sum_assignment(cost)
                s, r, t = umeyama_rotation(m[ci], tag_centers[ri])
            if np.any(penalty[ri, ci] > 0):
                continue
            proj = (s * (r @ m.T)).T + t
            err = np.sqrt(((proj[ci] - tag_centers[ri]) ** 2).sum(1).mean())
            if best is None or err < best[0]:
                best = (err, s, r, t, flip)
    if best is None:
        raise RuntimeError("Konnte Tags keinem Streckenteil zuordnen (Layout/Tag-IDs prüfen)")
    err, s, r, t, flip = best
    a = np.eye(3)
    a[:2, :2] = s * r @ np.diag([1.0, flip])
    a[:2, 2] = t
    return a, err / s  # Restfehler in mm


def rail_contrast(h, gray_blur, rails, slots):
    """Mittlere Helligkeit auf den Schienen minus auf den Schlitzen."""
    def sample(pts):
        p = apply_h(h, pts).astype(np.float32)
        if not np.all(np.isfinite(p)):
            return np.nan
        v = cv2.remap(gray_blur, p[:, 0].reshape(1, -1), p[:, 1].reshape(1, -1),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return v.mean()  # Punkte außerhalb des Bildes zählen als 0 -> wird bestraft
    c = float(sample(rails) - sample(slots))
    return c if np.isfinite(c) else -1e3


def px_per_mm(h, track):
    """Mittlerer Abbildungsmaßstab der Homographie im Bereich der Strecke."""
    _, x, y, _ = track.sample(50.0)
    p = np.stack([x, y], 1)
    q = apply_h(h, p)
    return float(np.median(np.linalg.norm(q[1:] - q[:-1], axis=1)
                           / np.linalg.norm(p[1:] - p[:-1], axis=1)))


RAIL_OFFSET_MM = 5.6  # Schiene <-> Schlitzmitte (gemessen)


def distort(pts, k1, size):
    """Radiale Linsenverzeichnung (ein Parameter, Zentrum = Bildmitte)."""
    c = np.asarray(size, dtype=float) / 2
    f = np.linalg.norm(c)
    d = (np.asarray(pts, dtype=float) - c) / f
    return c + d * (1 + k1 * (d ** 2).sum(1, keepdims=True)) * f


def undistort(pts, k1, size):
    c = np.asarray(size, dtype=float) / 2
    f = np.linalg.norm(c)
    d = (np.asarray(pts, dtype=float) - c) / f
    u = d.copy()
    for _ in range(20):
        u = d / (1 + k1 * (u ** 2).sum(1, keepdims=True))
    return c + u * f


def project(h, k1, size, pts):
    """Streckenmodell (mm) -> Bildpixel."""
    return distort(apply_h(h, pts), k1, size)


def find_slots(gray, q, u, rail_px, search):
    """
    Sucht für jeden Bildpunkt q entlang der Normalen u (±search px) das Muster
    helle Schiene - dunkler Schlitz - helle Schiene. Liefert (Versatz, gültig).
    """
    t = np.arange(-search, search + 1e-9, 0.25)
    T = np.broadcast_to(t, (len(q), len(t)))

    def sample(off):
        x = (q[:, :1] + off * u[:, :1]).astype(np.float32)
        y = (q[:, 1:] + off * u[:, 1:]).astype(np.float32)
        return cv2.remap(gray, x, y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan)

    r = rail_px[:, None]
    resp = sample(T - r) + sample(T + r) - 2 * sample(T)
    resp = np.where(np.isfinite(resp), resp, -np.inf)
    k = np.argmax(resp, axis=1)
    rows = np.arange(len(q))
    peak = resp[rows, k]
    inner = (k > 0) & (k < len(t) - 1)
    kk = np.clip(k, 1, len(t) - 2)
    a, b, c = resp[rows, kk - 1], resp[rows, kk], resp[rows, kk + 1]
    with np.errstate(invalid="ignore", divide="ignore"):  # -inf am Bildrand
        denom = a - 2 * b + c
        sub = np.where(np.abs(denom) > 1e-9, 0.5 * (a - c) / denom, 0.0)
    offset = t[kk] + np.clip(sub, -0.5, 0.5) * (t[1] - t[0])
    valid = inner & np.isfinite(peak) & (peak > 60) & np.isfinite(offset)
    return offset, valid


def refine_on_rails(h0, gray, track, size, fit_distortion=False):
    """
    Feinjustierung in zwei Stufen:
      1. dunkle Fahrbahn auf hellen Tisch ausrichten (fängt Fehler von mehreren cm)
      2. Schlitze im Bild suchen und das Modell darauf einpassen (sub-pixel),
         optional mit radialer Linsenverzeichnung k1

    Returns:
        (H, k1, rms_px, Anteil gefundener Schlitzpunkte)
    """
    inside, outside = track.body(ds=6.0)
    c = inside.mean(0)
    n = np.array([[1e-3, 0, -c[0] * 1e-3], [0, 1e-3, -c[1] * 1e-3], [0, 0, 1]])  # mm -> normiert
    n_inv = np.linalg.inv(n)

    def h_of(p):
        dp = np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1.0]])
        return h0 @ n_inv @ dp @ n

    scale = px_per_mm(h0, track)
    gray = gray.astype(np.float32)

    # Stufe 1: Fahrbahn (0.01 = ~10 mm Verschiebung bzw. 1 % Skalierung)
    p = np.zeros(8)
    for sigma_mm, step in ((8.0, 0.03), (4.0, 0.01)):
        blur = cv2.GaussianBlur(gray, (0, 0), sigma_mm * scale)
        res = minimize(lambda q: -rail_contrast(h_of(q), blur, outside, inside), p, method="Nelder-Mead",
                       options={"initial_simplex": np.vstack([p, p + step * np.eye(8)]),
                                "xatol": 1e-5, "fatol": 1e-3, "maxfev": 3000})
        p = res.x

    # Stufe 2: Schlitze suchen und einpassen (wie ICP)
    lanes = (LANE_OFFSET, -LANE_OFFSET)
    pts = track.lateral_points(lanes, ds=4.0)
    pts_right = track.lateral_points([l + 1.0 for l in lanes], ds=4.0)  # 1 mm weiter rechts
    sharp = cv2.GaussianBlur(gray, (0, 0), 0.7)
    x = np.append(p, 0.0) if fit_distortion else p
    unpack = lambda xx: (h_of(xx[:8]), xx[8] if fit_distortion else 0.0)
    for search in (8.0, 6.0, 4.0, 3.0, 3.0):
        h, k1 = unpack(x)
        q = project(h, k1, size, pts)
        nv = project(h, k1, size, pts_right) - q
        px_mm = np.linalg.norm(nv, axis=1)
        u = nv / px_mm[:, None]
        off, valid = find_slots(sharp, q, u, RAIL_OFFSET_MM * px_mm, search)
        target, uu, pv = q[valid] + off[valid, None] * u[valid], u[valid], pts[valid]

        def residual(xx):
            hh, kk = unpack(xx)
            return ((project(hh, kk, size, pv) - target) * uu).sum(1)

        x = least_squares(residual, x, loss="soft_l1", f_scale=1.0, x_scale="jac").x
    h, k1 = unpack(x)
    rms = float(np.sqrt(np.median(residual(x) ** 2)))
    return h, float(k1), rms, float(valid.mean())


def calibrate(image, layout=LAYOUT, lane="right", target_image=None, fit_distortion=False):
    """
    Komplette Kalibrierung. Liefert ein dict (JSON-fähig).

    Args:
        image: Bild zur Tag-Erkennung (möglichst hohe Auflösung)
        target_image: optional Bild in der Auflösung, in der später gemessen wird
            (gleicher Bildausschnitt, nur kleiner). Die Feinjustierung läuft dann
            darauf, und die Kalibrierung gilt für diese Auflösung.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    track = Track(layout, lane=lane)
    tags = detect_tags(gray)
    h_plane, tag_centers, rms = fit_plane_homography(tags)
    a, align_err = initial_alignment(track, tags, tag_centers)
    h_init = h_plane @ a
    target = image if target_image is None else target_image
    if target is not image:
        sx = target.shape[1] / image.shape[1]
        sy = target.shape[0] / image.shape[0]
        h_init = np.diag([sx, sy, 1.0]) @ h_init
    size = (int(target.shape[1]), int(target.shape[0]))
    h, k1, slot_rms, found = refine_on_rails(h_init, cv2.cvtColor(target, cv2.COLOR_BGR2GRAY), track, size,
                                             fit_distortion)
    return {
        "H_model_to_image": h.tolist(),
        "k1": k1,
        "layout": list(layout),
        "lane": lane,
        "image_size": list(size),
        "n_tags": len(tags),
        "tag_fit_rms_px": rms,
        "tag_alignment_error_mm": float(align_err),
        "slot_fit_rms_px": slot_rms,
        "slot_fit_rms_mm": slot_rms / px_per_mm(h, track),
        "slot_points_found": found,
    }


def draw_overlay(image, calib):
    """Zeichnet beide Spuren (grün = gewählte Spur) zur Sichtkontrolle ins Bild."""
    out = image.copy()
    h, k1, size = np.array(calib["H_model_to_image"]), calib.get("k1", 0.0), calib["image_size"]
    track = Track(calib["layout"], lane=calib["lane"])
    for off, col in ((LANE_OFFSET if calib["lane"] == "right" else -LANE_OFFSET, (0, 255, 0)),
                     (-LANE_OFFSET if calib["lane"] == "right" else LANE_OFFSET, (255, 0, 255))):
        p = project(h, k1, size, track.lateral_points([off], ds=2.0))
        cv2.polylines(out, [np.round(p * 4).astype(np.int32)], True, col, 1, cv2.LINE_AA, shift=2)
    x0, y0 = project(h, k1, size, np.array(track.position(0.0)).reshape(1, 2))[0]
    cv2.circle(out, (int(x0), int(y0)), 5, (0, 0, 255), -1)
    cv2.putText(out, "s=0", (int(x0) + 8, int(y0)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return out


def remove_parallax(xy, parallax):
    """
    Der Aufkleber sitzt über der Bahn und erscheint deshalb radial vom Fußpunkt
    der Kamera weg verschoben: p_beobachtet = C + (1 + k) * (p_wahr - C).
    """
    if not parallax:
        return xy
    c = np.array([parallax["cx"], parallax["cy"]])
    return c + (np.asarray(xy, dtype=float) - c) / (1.0 + parallax["k"])


class CameraCalibration:
    """Rechnet Kamerapixel in Streckenposition um."""

    def __init__(self, path):
        with open(path) as f:
            self.data = json.load(f)
        self.h = np.array(self.data["H_model_to_image"])
        self.h_inv = np.linalg.inv(self.h)
        self.k1 = self.data.get("k1", 0.0)
        self.size = self.data["image_size"]
        self.parallax = self.data.get("parallax")
        self.track = Track(self.data["layout"], lane=self.data["lane"])

    def pixels_to_model(self, pxy, parallax=True):
        """Bildpunkte (N, 2) -> Streckenmodell (mm), optional ohne Parallaxe-Korrektur."""
        xy = apply_h(self.h_inv, undistort(np.asarray(pxy, dtype=float).reshape(-1, 2), self.k1, self.size))
        return remove_parallax(xy, self.parallax) if parallax else xy

    def pixel_to_model(self, px, py):
        return self.pixels_to_model([[px, py]])[0]

    def pixel_to_track(self, px, py):
        """(s, lateral) in mm für einen Bildpunkt."""
        x, y = self.pixel_to_model(px, py)
        s, lateral = self.track.project(x, y)
        return s, lateral - (self.parallax or {}).get("d_lat", 0.0)

    def pixels_to_track(self, pxy):
        s, lateral = self.track.project_many(self.pixels_to_model(pxy))
        return s, lateral - (self.parallax or {}).get("d_lat", 0.0)

    def track_region(self, margin_mm=60.0):
        """Maske der Strecke plus Rand (für die Autosuche)."""
        center = self.track.lateral_points([0.0], ds=5.0)
        p = project(self.h, self.k1, self.size, center)
        width_px = (115.0 + 2 * margin_mm) * px_per_mm(self.h, self.track)
        mask = np.zeros((self.size[1], self.size[0]), np.uint8)
        cv2.polylines(mask, [np.round(p).astype(np.int32)], True, 255, int(round(width_px)))
        return mask


def fit_parallax(calib, pixels, max_points=6000):
    """
    Bestimmt Fußpunkt der Kamera (cx, cy), Verschiebungsfaktor k und den seitlichen
    Versatz des Aufklebers d_lat aus aufgezeichneten Fahrten: korrigiert müssen
    alle Positionen auf der Spurlinie liegen.
    """
    pixels = np.asarray(pixels, dtype=float)
    if len(pixels) > max_points:
        pixels = pixels[np.linspace(0, len(pixels) - 1, max_points).astype(int)]
    xy_obs = calib.pixels_to_model(pixels, parallax=False)
    c0 = calib.pixels_to_model([[calib.size[0] / 2, calib.size[1] / 2]], parallax=False)[0]

    def residual(p):
        par = {"cx": p[0], "cy": p[1], "k": p[2]}
        return calib.track.project_many(remove_parallax(xy_obs, par))[1] - p[3]

    before = residual([c0[0], c0[1], 0.0, 0.0])
    sol = least_squares(residual, [c0[0], c0[1], 0.03, 0.0], loss="soft_l1", f_scale=3.0, x_scale=[100, 100, 0.01, 1])
    p = sol.x
    return ({"cx": float(p[0]), "cy": float(p[1]), "k": float(p[2]), "d_lat": float(p[3])},
            float(np.sqrt(np.mean((before - np.median(before)) ** 2))), float(np.sqrt(np.mean(sol.fun ** 2))))


def main():
    from .camera import DEFAULT_FPS, DEFAULT_INDEX, DEFAULT_SIZE, grab_frame

    if "--fit-parallax" in __import__("sys").argv:
        return main_parallax()

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="Bilddatei der Strecke (ohne Auto)")
    src.add_argument("--camera", action="store_true", help="Bild direkt von der Kamera holen")
    ap.add_argument("--cam-index", type=int, default=DEFAULT_INDEX)
    ap.add_argument("--width", type=int, default=DEFAULT_SIZE[0], help="Auflösung der Messfahrten")
    ap.add_argument("--height", type=int, default=DEFAULT_SIZE[1])
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--tag-size", type=int, nargs=2, default=[1920, 1080],
                    help="höhere Auflösung für die Tag-Erkennung")
    ap.add_argument("--lane", default="right", choices=["right", "left"])
    ap.add_argument("--out", default="calibration/camera.json")
    args = ap.parse_args()

    if args.image:
        image = cv2.imread(args.image)
        if image is None:
            raise SystemExit(f"Bild konnte nicht geladen werden: {args.image}")
        target = None
    else:
        image = grab_frame(args.cam_index, *args.tag_size, fps=30)
        target = grab_frame(args.cam_index, args.width, args.height, fps=args.fps)
    calib = calibrate(image, lane=args.lane, target_image=target)
    shown = image if target is None else target

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(calib, f, indent=2)
    base = os.path.splitext(args.out)[0]
    cv2.imwrite(base + "_frame.png", shown)
    if target is not None:
        cv2.imwrite(base + "_frame_tags.png", image)
    cv2.imwrite(base + "_overlay.png", draw_overlay(shown, calib))
    print(f"Tags erkannt: {calib['n_tags']}, Tag-Fit: {calib['tag_fit_rms_px']:.2f} px, "
          f"Grobzuordnung: {calib['tag_alignment_error_mm']:.0f} mm")
    print(f"Schlitze gefunden: {calib['slot_points_found'] * 100:.0f} %, Restfehler: "
          f"{calib['slot_fit_rms_px']:.2f} px = {calib['slot_fit_rms_mm']:.2f} mm, Linsenverzeichnung k1 = {calib['k1']:.4f}")
    print(f"Gespeichert: {args.out}  ->  bitte {base}_overlay.png ansehen: Linien müssen auf den Schlitzen liegen")


def main_parallax():
    """python -m carrera_rl.camera_calib --fit-parallax data/runs/A data/runs/B [--calib calibration/camera.json]"""
    import csv
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit-parallax", nargs="+", required=True, metavar="RUN")
    ap.add_argument("--calib", default="calibration/camera.json")
    args = ap.parse_args()
    calib = CameraCalibration(args.calib)
    pixels = []
    for run in args.fit_parallax:
        with open(os.path.join(run, "frames.csv")) as f:
            pixels += [(float(r["px"]), float(r["py"])) for r in csv.DictReader(f)
                       if r["detected"] == "1" and r["px"] not in ("", "nan")]
    par, rms_before, rms_after = fit_parallax(calib, pixels)
    calib.data["parallax"] = par
    with open(args.calib, "w") as f:
        json.dump(calib.data, f, indent=2)
    print(f"{len(pixels)} Positionen. Seitliche Streuung um die Spur: {rms_before:.1f} mm -> {rms_after:.1f} mm")
    print(f"Fußpunkt der Kamera (Modell-mm): ({par['cx']:.0f}, {par['cy']:.0f}), k = {par['k']:.4f}, "
          f"Aufkleber seitlich versetzt um {par['d_lat']:.1f} mm")
    print(f"Gespeichert in {args.calib}")


if __name__ == "__main__":
    main()
