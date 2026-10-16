"""
Kamera öffnen mit fester Auflösung und Bildrate.

Logitech BRIO (gemessen): 1920x1080 mit 30 fps, 1280x720 mit 60 fps.
Ohne explizit gesetzte Bildrate liefert sie unter macOS nur ~5 fps.
"""
import platform

import cv2

DEFAULT_INDEX = 0
DEFAULT_SIZE = (1280, 720)
DEFAULT_FPS = 60


def open_camera(index=DEFAULT_INDEX, width=DEFAULT_SIZE[0], height=DEFAULT_SIZE[1], fps=DEFAULT_FPS,
                n_warmup=20):
    system = platform.system()
    backend = {"Darwin": cv2.CAP_AVFOUNDATION, "Windows": cv2.CAP_DSHOW}.get(system, cv2.CAP_ANY)
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Kamera {index} lässt sich nicht öffnen (Kamera-Berechtigung? richtiger Index?)")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    frame = None
    for _ in range(n_warmup):  # Belichtung einschwingen lassen
        ok, f = cap.read()
        if ok:
            frame = f
    if frame is None:
        cap.release()
        raise RuntimeError(f"Kamera {index} liefert keine Bilder")
    if (frame.shape[1], frame.shape[0]) != (width, height):
        print(f"Warnung: {width}x{height} angefragt, Kamera liefert {frame.shape[1]}x{frame.shape[0]}")
    return cap


def grab_frame(index=DEFAULT_INDEX, width=DEFAULT_SIZE[0], height=DEFAULT_SIZE[1], fps=DEFAULT_FPS,
               n_warmup=40):
    cap = open_camera(index, width, height, fps, n_warmup=n_warmup)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("Kamera liefert keine Bilder")
    return frame


# Grüner Aufkleber auf dem Auto (gemessen mit BRIO, 16.10.2026: H~61, S~240, V~195)
CAR_HSV_LOW = (45, 120, 80)
CAR_HSV_HIGH = (85, 255, 255)


def find_car(frame, roi=None, hsv_low=CAR_HSV_LOW, hsv_high=CAR_HSV_HIGH, min_area=15):
    """
    Position des grünen Aufklebers im Bild.

    Args:
        roi: optionale Maske (uint8), nur dort wird gesucht, z.B. CameraCalibration.track_region()

    Returns:
        ((x, y) als float oder None, Maske)
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, hsv_low, hsv_high)
    if roi is not None:
        mask &= roi
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None, mask
    i = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())  # größter Fleck (0 = Hintergrund)
    if stats[i, cv2.CC_STAT_AREA] < min_area:
        return None, mask
    return (float(centroids[i, 0]), float(centroids[i, 1])), mask
