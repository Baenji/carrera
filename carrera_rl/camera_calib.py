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

from .track import LAYOUT, Track

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


def refine_on_rails(h0, gray, track):
    """Feinjustierung der Homographie, bis die Modell-Schienen auf den Bild-Schienen liegen."""
    rails, slots = track.rails(ds=3.0)
    c = rails.mean(0)
    n = np.array([[1e-3, 0, -c[0] * 1e-3], [0, 1e-3, -c[1] * 1e-3], [0, 0, 1]])  # mm -> normiert
    n_inv = np.linalg.inv(n)

    def h_of(p):
        dp = np.array([[1 + p[0], p[1], p[2]], [p[3], 1 + p[4], p[5]], [p[6], p[7], 1.0]])
        return h0 @ n_inv @ dp @ n

    p = np.zeros(8)
    for sigma, step in ((6.0, 0.01), (3.0, 0.004), (1.5, 0.002)):
        blur = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), sigma)
        # Startsimplex: kleine Schritte (0.01 = ~10 mm Verschiebung bzw. 1 % Skalierung)
        simplex = np.vstack([p, p + step * np.eye(8)])
        res = minimize(lambda q: -rail_contrast(h_of(q), blur, rails, slots), p,
                       method="Nelder-Mead",
                       options={"initial_simplex": simplex, "xatol": 1e-5, "fatol": 1e-3, "maxfev": 3000})
        p = res.x
    blur = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.5)
    return h_of(p), rail_contrast(h_of(p), blur, rails, slots)


def calibrate(image, layout=LAYOUT, lane="right"):
    """Komplette Kalibrierung aus einem Bild. Liefert ein dict (JSON-fähig)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    track = Track(layout, lane=lane)
    tags = detect_tags(gray)
    h_plane, tag_centers, rms = fit_plane_homography(tags)
    a, align_err = initial_alignment(track, tags, tag_centers)
    h_init = h_plane @ a
    h, contrast = refine_on_rails(h_init, gray, track)
    return {
        "H_model_to_image": h.tolist(),
        "layout": list(layout),
        "lane": lane,
        "image_size": [int(image.shape[1]), int(image.shape[0])],
        "n_tags": len(tags),
        "tag_fit_rms_px": rms,
        "tag_alignment_error_mm": float(align_err),
        "rail_contrast": contrast,
    }


def draw_overlay(image, calib):
    """Zeichnet beide Spuren (grün = gewählte Spur) zur Sichtkontrolle ins Bild."""
    out = image.copy()
    h = np.array(calib["H_model_to_image"])
    track = Track(calib["layout"], lane=calib["lane"])
    s, x, y, _ = track.sample(2.0)
    hd = track.heading(s)
    for off, col in ((0.0, (0, 255, 0)), (-57.0 if calib["lane"] == "right" else 57.0, (255, 0, 255))):
        pts = np.stack([x + off * np.sin(hd), y - off * np.cos(hd)], 1)
        p = apply_h(h, pts)
        cv2.polylines(out, [np.round(p * 4).astype(np.int32)], True, col, 2, cv2.LINE_AA, shift=2)
    x0, y0 = apply_h(h, np.array(track.position(0.0)).reshape(1, 2))[0]
    cv2.circle(out, (int(x0), int(y0)), 8, (0, 0, 255), -1)
    cv2.putText(out, "s=0", (int(x0) + 10, int(y0)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    return out


class CameraCalibration:
    """Rechnet Kamerapixel in Streckenposition um."""

    def __init__(self, path):
        with open(path) as f:
            self.data = json.load(f)
        self.h = np.array(self.data["H_model_to_image"])
        self.h_inv = np.linalg.inv(self.h)
        self.track = Track(self.data["layout"], lane=self.data["lane"])

    def pixel_to_model(self, px, py):
        return apply_h(self.h_inv, np.array([[px, py]]))[0]

    def pixel_to_track(self, px, py):
        """(s, lateral) in mm für einen Bildpunkt."""
        x, y = self.pixel_to_model(px, py)
        return self.track.project(x, y)


def grab_camera_frame(n_warmup=30):
    from src.camera import initialize_camera  # vorhandene Kamera-Initialisierung der Vorgruppe
    cap = initialize_camera()
    if cap is None:
        raise RuntimeError("Keine Kamera gefunden")
    frame = None
    for _ in range(n_warmup):  # Belichtung einschwingen lassen
        ok, f = cap.read()
        if ok:
            frame = f
    cap.release()
    if frame is None:
        raise RuntimeError("Kamera liefert keine Bilder")
    return frame


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="Bilddatei der Strecke (ohne Auto)")
    src.add_argument("--camera", action="store_true", help="Bild direkt von der Kamera holen")
    ap.add_argument("--lane", default="right", choices=["right", "left"])
    ap.add_argument("--out", default="calibration/camera.json")
    args = ap.parse_args()

    image = cv2.imread(args.image) if args.image else grab_camera_frame()
    if image is None:
        raise SystemExit(f"Bild konnte nicht geladen werden: {args.image}")
    calib = calibrate(image, lane=args.lane)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(calib, f, indent=2)
    base = os.path.splitext(args.out)[0]
    cv2.imwrite(base + "_frame.png", image)
    cv2.imwrite(base + "_overlay.png", draw_overlay(image, calib))
    print(f"Tags erkannt: {calib['n_tags']}, Tag-Fit: {calib['tag_fit_rms_px']:.2f} px, "
          f"Grobzuordnung: {calib['tag_alignment_error_mm']:.0f} mm, Schienenkontrast: {calib['rail_contrast']:.1f}")
    print(f"Gespeichert: {args.out}  ->  bitte {base}_overlay.png ansehen: Linien müssen auf den Schlitzen liegen")


if __name__ == "__main__":
    main()
