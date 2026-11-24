"""Auto-Tracking per Referenzbild-Differenz (einfache Version).

Ablauf:
  1. Kamera öffnen, Automatik (Belichtung/Weißabgleich/Fokus) einschwingen lassen und dann sperren.
  2. Strecke OHNE Auto -> [b] -> Referenzbild = Mittel aus 30 Frames.
  3. Auto aufsetzen und fahren lassen.
  4. Jeder Frame wird mit dem Referenzbild verglichen; die größte zusammenhängende
     Differenzregion = Auto. Ihr Schwerpunkt wird als Punkt eingezeichnet.

Tasten im Fenster:
  b  Referenzbild aufnehmen (Strecke muss leer sein!)
  m  Differenzmaske ein/aus
  +/- Schwellwert
  q / ESC  beenden

Start: python experiments/car_diff_tracking/track_car.py

Plattformen:
  Linux:   V4L2-Backend, Brio wird über /dev/v4l/by-id gefunden.
  Windows: DirectShow-Backend. Brio wird per Name gefunden, wenn `pygrabber` installiert ist
           (pip install pygrabber), sonst Kamera-Index 0 -> ggf. --device 1 angeben.
           --exposure ist dort in log2(Sekunden) anzugeben (z.B. -7 ≈ 8 ms).
"""

from __future__ import annotations

import argparse
import glob
import sys
import time

import cv2
import numpy as np

WINDOW = "Car Diff Tracking"

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    # DirectShow statt MSMF: öffnet schneller und reicht Belichtung/Weißabgleich/Fokus an die Kamera durch
    BACKEND = cv2.CAP_DSHOW
    AE_AUTO, AE_MANUAL = 0.75, 0.25  # Konvention des DirectShow-Backends
else:
    BACKEND = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    AE_AUTO, AE_MANUAL = 3, 1  # V4L2: 3 = auto (aperture priority), 1 = manuell


# --------------------------------
# Kamera
# --------------------------------


def find_brio() -> str | int:
    """Sucht die Logitech Brio. Fallback: Kamera-Index 0."""
    if IS_WINDOWS:
        try:
            from pygrabber.dshow_graph import FilterGraph  # optional, nur Windows
        except ImportError:
            print(
                "[kamera] pygrabber nicht installiert -> nehme Index 0 (sonst --device 1, 2, ...)"
            )
            return 0
        # Reihenfolge entspricht den DirectShow-Indizes von OpenCV
        for i, name in enumerate(FilterGraph().get_input_devices()):
            if "brio" in name.lower():
                return i
        return 0
    # Linux: index0 = eigentlicher Farbstream
    hits = sorted(glob.glob("/dev/v4l/by-id/*BRIO*-video-index0"))
    return hits[0] if hits else 0


def open_camera(
    device: str | int, width: int, height: int, fps: int
) -> cv2.VideoCapture:
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    cap = cv2.VideoCapture(device, BACKEND)
    if not cap.isOpened():
        raise SystemExit(f"Kamera {device!r} konnte nicht geöffnet werden.")
    # MJPG ist nötig, damit die Brio 720p/1080p mit hoher FPS liefert (YUYV ist viel langsamer)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def lock_camera(
    cap: cv2.VideoCapture, exposure: float | None, settle_s: float = 2.0
) -> None:
    """Automatik einschwingen lassen und dann einfrieren.

    Wichtig für die Differenzmethode: Würde die Kamera Belichtung/Weißabgleich nachregeln
    (z.B. weil ein dunkles Auto ins Bild fährt), ändert sich das ganze Bild und der
    Vergleich mit dem Referenzbild liefert überall Unterschiede.
    """
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AE_AUTO)
    cap.set(cv2.CAP_PROP_AUTO_WB, 1)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < settle_s:
        cap.read()

    exp = exposure if exposure is not None else cap.get(cv2.CAP_PROP_EXPOSURE)
    wb = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
    focus = cap.get(cv2.CAP_PROP_FOCUS)
    steps = [
        ("Belichtung", cv2.CAP_PROP_AUTO_EXPOSURE, AE_MANUAL),
        ("Belichtung", cv2.CAP_PROP_EXPOSURE, exp),
        ("Weißabgleich", cv2.CAP_PROP_AUTO_WB, 0),
        ("Weißabgleich", cv2.CAP_PROP_WB_TEMPERATURE, wb),
        ("Fokus", cv2.CAP_PROP_AUTOFOCUS, 0),
        ("Fokus", cv2.CAP_PROP_FOCUS, focus),
    ]
    failed = sorted({name for name, prop, val in steps if not cap.set(prop, val)})
    unit = "log2 s" if IS_WINDOWS else "x100µs"
    print(
        f"[kamera] gesperrt: exposure={exp:g} ({unit})  wb={wb:.0f}K  focus={focus:.0f}"
    )
    if failed:
        print(f"[kamera] WARNUNG: konnte nicht sperren: {', '.join(failed)}")


def read_frame(cap: cv2.VideoCapture) -> np.ndarray:
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Kein Frame von der Kamera erhalten.")
    return frame


# --------------------------------
# Tracking
# --------------------------------


class DiffTracker:
    def __init__(self, threshold: int, min_area: int, blur: int, scale: float):
        self.threshold = threshold
        self.min_area = min_area  # in Pixeln des Originalbilds
        self.blur = blur | 1  # muss ungerade sein
        self.scale = scale  # Verarbeitung auf verkleinertem Bild -> deutlich schneller
        self.reference: np.ndarray | None = None
        self.kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def prep(self, frame: np.ndarray) -> np.ndarray:
        if self.scale != 1.0:
            frame = cv2.resize(
                frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA
            )
        # Leichtes Weichzeichnen unterdrückt Sensorrauschen und JPEG-Artefakte
        return cv2.GaussianBlur(frame, (self.blur, self.blur), 0)

    def set_reference(self, frames: list[np.ndarray]) -> None:
        """Referenzbild = Mittelwert über Frames der leeren Strecke."""
        mean = np.mean([self.prep(f).astype(np.float32) for f in frames], axis=0)
        self.reference = cv2.convertScaleAbs(mean)

    def process(self, frame: np.ndarray) -> tuple[tuple[int, int] | None, np.ndarray]:
        """Gibt (Mittelpunkt des Autos oder None, Differenzmaske in Originalauflösung) zurück."""
        assert self.reference is not None
        cur = self.prep(frame)
        # Differenz pro Farbkanal, dann Maximum über die Kanäle:
        # so fällt das Auto auch auf, wenn es nur in einem Kanal vom Referenzbild abweicht
        d = cv2.absdiff(cur, self.reference)
        diff = cv2.max(cv2.max(d[:, :, 0], d[:, :, 1]), d[:, :, 2])
        _, mask = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, self.kernel_open
        )  # einzelne Rauschpixel weg
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, self.kernel_close
        )  # Löcher im Auto schließen

        center = None
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            m = cv2.moments(c) # m00 = Fläche, m01 = Summe(y-coords), m10 = Summe(x-coords)
            if cv2.contourArea(c) >= self.min_area * self.scale**2 and m["m00"] > 0:
                center = (
                    int(round(m["m10"] / m["m00"] / self.scale)), # durchschnittliche x-Koordinate
                    int(round(m["m01"] / m["m00"] / self.scale)), # durchschnittliche y-Koordinate
                )

        if self.scale != 1.0:
            mask = cv2.resize(
                mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        return center, mask


# --------------------------------
# Main
# --------------------------------


def put_text(img: np.ndarray, lines: list[str], org=(10, 25)) -> None:
    x, y = org
    for line in lines:
        cv2.putText(
            img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA
        )
        cv2.putText(
            img,
            line,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        y += 24


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--device",
        default=None,
        help="Kamera (Pfad oder Index). Default: Brio automatisch suchen",
    )
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument(
        "--exposure",
        type=float,
        default=None,
        help="Feste Belichtung. Linux: 100µs-Einheiten (z.B. 100 = 10ms, flickerfrei bei 50Hz-Licht). "
        "Windows: log2(Sekunden), z.B. -7 ≈ 8ms. Default: Wert der Automatik übernehmen",
    )
    ap.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="Mindestdifferenz (0-255) für 'anders als Referenz'",
    )
    ap.add_argument(
        "--min-area",
        type=int,
        default=300,
        help="Mindestfläche (px) einer Region, um als Auto zu gelten",
    )
    ap.add_argument(
        "--blur",
        type=int,
        default=5,
        help="Gauß-Kernel (ungerade, bezogen aufs verkleinerte Bild)",
    )
    ap.add_argument(
        "--scale",
        type=float,
        default=0.5,
        help="Verkleinerungsfaktor für die Verarbeitung",
    )
    ap.add_argument(
        "--ref-frames", type=int, default=30, help="Anzahl Frames für das Referenzbild"
    )
    args = ap.parse_args()

    device = args.device if args.device is not None else find_brio()
    print(f"[kamera] öffne {device}")
    cap = open_camera(device, args.width, args.height, args.fps)
    lock_camera(cap, args.exposure)

    tracker = DiffTracker(args.threshold, args.min_area, args.blur, args.scale)
    show_mask = False
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    try:
        while True:
            frame = read_frame(cap)

            if tracker.reference is None:
                view = frame
                put_text(
                    view,
                    [
                        "Strecke leeren (kein Auto!), dann [b] fuer Referenzbild",
                        "[q] beenden",
                    ],
                )
            else:
                center, mask = tracker.process(frame)
                view = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if show_mask else frame
                if center is not None:
                    cv2.circle(view, center, 8, (0, 0, 255), -1)
                    cv2.circle(view, center, 9, (255, 255, 255), 2)
                put_text(
                    view,
                    [
                        f"pos={center}" if center else "kein Auto erkannt",
                        f"thr={tracker.threshold} | [b] Referenz [m] Maske [+/-] Schwelle [q] Ende",
                    ],
                )

            cv2.imshow(WINDOW, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("b"):
                tracker.set_reference([read_frame(cap) for _ in range(args.ref_frames)])
                print(f"[ref] Referenzbild aus {args.ref_frames} Frames gemittelt")
            elif key == ord("m"):
                show_mask = not show_mask
            elif key in (ord("+"), ord("=")):
                tracker.threshold = min(255, tracker.threshold + 5)
            elif key == ord("-"):
                tracker.threshold = max(5, tracker.threshold - 5)
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
