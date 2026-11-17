"""Auto-Tracking über einen blauen Punkt auf dem Auto (Iteration von track_car.py).

Unterschied zu track_car.py: Nicht die größte Differenzregion gilt als Auto, sondern die Stelle,
an der ein blauer Punkt liegt. Hände, Schatten und blaue Dinge neben der Strecke werden ignoriert.

Ablauf:
  1. Kamera öffnen, Automatik (Belichtung/Weißabgleich/Fokus) einschwingen lassen und dann sperren.
  2. Strecke OHNE Auto -> [b] -> Referenzbild = Mittel aus 30 Frames.
  3. Auto aufsetzen und fahren lassen.
  4. Jeder Frame wird mit dem Referenzbild verglichen -> Differenzmaske (alles, was neu ist).
  5. Im Originalbild werden die blauen Pixel gesucht (HSV-Farbbereich). Blau UND Differenzmaske
     = blaue Pixel, die nicht schon im Referenzbild waren. Der größte solche Fleck ist der Punkt
     auf dem Auto, sein Schwerpunkt ist die Position.

Tasten im Fenster:
  b    Referenzbild aufnehmen (Strecke muss leer sein!)
  m    Ansicht wechseln: Kamerabild -> Differenzmaske -> Blau-Maske
  +/-  Schwellwert der Differenzmaske
  Klick ins Bild: HSV-Wert an dieser Stelle ausgeben (zum Kalibrieren von BLUE_LOW/BLUE_HIGH)
  q / ESC  beenden

Start: python experiments/car_diff_tracking/track_blue_dot.py

Plattformen:
  Linux:   V4L2-Backend, Brio wird über /dev/v4l/by-id gefunden.
  Windows: DirectShow-Backend. Brio wird per Name gefunden, wenn `pygrabber` installiert ist
           (pip install pygrabber), sonst Kamera-Index 0 -> ggf. --device 1 angeben.
           --exposure ist dort in log2(Sekunden) anzugeben (z.B. -7 ≈ 8 ms).
  macOS:   AVFoundation-Backend, Brio wird per Name gefunden (über system_profiler).
           Einschränkung: OpenCV kann dort nur Auflösung und FPS setzen. Belichtung, Weißabgleich
           und Fokus bleiben auf Automatik, und die Brio liefert nur 30 fps.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import time

import cv2
import numpy as np

WINDOW = "Blue Dot Tracking"

# Farbbereich des blauen Punkts in HSV (OpenCV: H 0-179, S und V 0-255).
BLUE_LOW = (104, 110, 40)
BLUE_HIGH = (118, 255, 255)

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WINDOWS:
    # DirectShow statt MSMF: öffnet schneller und reicht Belichtung/Weißabgleich/Fokus an die Kamera durch
    BACKEND = cv2.CAP_DSHOW
    AE_AUTO, AE_MANUAL = 0.75, 0.25  # Konvention des DirectShow-Backends
elif IS_MAC:
    BACKEND = cv2.CAP_AVFOUNDATION  # kann nur Auflösung und FPS setzen, siehe lock_camera()
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
    if IS_MAC:
        # OpenCV nummeriert die Kameras auf dem Mac nach ihrer Unique ID sortiert
        try:
            out = subprocess.run(
                ["system_profiler", "SPCameraDataType", "-json"],
                capture_output=True,
                text=True,
            ).stdout
            cams = sorted(
                json.loads(out)["SPCameraDataType"],
                key=lambda c: c["spcamera_unique-id"],
            )
        except (OSError, ValueError, KeyError):
            print(
                "[kamera] Kameraliste nicht lesbar -> nehme Index 0 (sonst --device 1, 2, ...)"
            )
            return 0
        for i, cam in enumerate(cams):
            if "brio" in cam["_name"].lower():
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
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[kamera] Modus: {w}x{h} @ {cap.get(cv2.CAP_PROP_FPS):.0f} fps")
    return cap


def lock_camera(
    cap: cv2.VideoCapture, exposure: float | None, settle_s: float = 2.0
) -> None:
    """Automatik einschwingen lassen und dann einfrieren.

    Wichtig für die Differenzmethode: Würde die Kamera Belichtung/Weißabgleich nachregeln
    (z.B. weil ein dunkles Auto ins Bild fährt), ändert sich das ganze Bild und der
    Vergleich mit dem Referenzbild liefert überall Unterschiede.
    """
    if IS_MAC:
        print(
            "[kamera] WARNUNG: macOS kann Belichtung/Weißabgleich/Fokus über OpenCV nicht sperren, "
            "die Automatik bleibt an. Werte ggf. in Logi Tune fest einstellen."
        )
        if exposure is not None:
            print("[kamera] --exposure wird auf macOS ignoriert")
        return
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


def exposure_ms(cap: cv2.VideoCapture) -> float | None:
    """TEMPORÄR: aktuelle Belichtungszeit der Kamera in ms. macOS: nicht auslesbar -> None."""
    if IS_MAC:
        return None
    v = cap.get(cv2.CAP_PROP_EXPOSURE)
    # Windows: log2(Sekunden), Linux: Einheiten von 100 µs
    return 2**v * 1000 if IS_WINDOWS else v / 10


def read_frame(cap: cv2.VideoCapture) -> np.ndarray:
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Kein Frame von der Kamera erhalten.")
    return frame


# --------------------------------
# Tracking
# --------------------------------


class DiffTracker:
    """Liefert die Differenzmaske: weiß = anders als das Referenzbild der leeren Strecke."""

    def __init__(self, threshold: int, blur: int, scale: float):
        self.threshold = threshold
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

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Gibt die Differenzmaske in Originalauflösung zurück."""
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

        if self.scale != 1.0:
            mask = cv2.resize(
                mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        return mask


def find_blue_dot(
    frame: np.ndarray, diff_mask: np.ndarray, min_area: int = 15
) -> tuple[tuple[int, int] | None, int, np.ndarray]:
    """Gibt (Mittelpunkt des blauen Punkts oder None, Radius in px, Blau-Maske) zurück.

    frame:     BGR-Bild in Originalauflösung. Nicht verkleinern, der Punkt ist nur wenige Pixel groß.
    diff_mask: Differenzmaske vom DiffTracker in derselben Auflösung
    min_area:  Mindestanzahl blauer Pixel, damit einzelne Rauschpixel nicht als Punkt zählen
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, BLUE_LOW, BLUE_HIGH)
    # Nur Blau, das nicht schon im Referenzbild war (z.B. blaue Dinge neben der Strecke)
    blue = cv2.bitwise_and(blue, diff_mask)

    # Zusammenhängende Flecken mit Pixelanzahl und Schwerpunkt. Label 0 ist der Hintergrund.
    n, _, stats, centroids = cv2.connectedComponentsWithStats(blue)
    if n < 2:
        return None, 0, blue
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))  # größter Fleck
    if stats[i, cv2.CC_STAT_AREA] < min_area:
        return None, 0, blue
    x, y = centroids[i]
    # Radius = halbe Breite bzw. Höhe des Flecks (bei Bewegungsunschärfe: halbe Länge der Spur)
    radius = int(np.ceil(max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) / 2))
    return (int(round(x)), int(round(y))), radius, blue


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
        "Windows: log2(Sekunden), z.B. -7 ≈ 8ms. macOS: wird ignoriert. "
        "Kurz halten, sonst verschmiert der blaue Punkt. Default: Wert der Automatik übernehmen",
    )
    ap.add_argument(
        "--threshold",
        type=int,
        default=30,
        help="Mindestdifferenz (0-255) für 'anders als Referenz'",
    )
    ap.add_argument(
        "--min-dot-area",
        type=int,
        default=15,
        help="Mindestfläche (px) des blauen Punkts",
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
        help="Verkleinerungsfaktor für die Differenzmaske",
    )
    ap.add_argument(
        "--ref-frames", type=int, default=30, help="Anzahl Frames für das Referenzbild"
    )
    args = ap.parse_args()

    device = args.device if args.device is not None else find_brio()
    print(f"[kamera] öffne {device}")
    cap = open_camera(device, args.width, args.height, args.fps)
    lock_camera(cap, args.exposure)

    tracker = DiffTracker(args.threshold, args.blur, args.scale)
    view_mode = 0  # 0 = Kamerabild, 1 = Differenzmaske, 2 = Blau-Maske
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    frame = None  # wird in der Schleife gesetzt, on_click liest immer das aktuelle Bild

    def on_click(event, x, y, flags, param):
        """Gibt den HSV-Wert (Median eines 5x5-Felds) an der Klickstelle aus."""
        if event != cv2.EVENT_LBUTTONDOWN or frame is None:
            return
        patch = frame[max(y - 2, 0) : y + 3, max(x - 2, 0) : x + 3]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
        h, s, v = np.median(hsv, axis=0).astype(int)
        print(f"[hsv] ({x}, {y}): H={h} S={s} V={v}")

    cv2.setMouseCallback(WINDOW, on_click)

    # TEMPORÄR: Belichtungszeit jede Sekunde ins Terminal loggen
    last_log = 0.0
    if IS_MAC:
        print("[belichtung] auf macOS über OpenCV nicht auslesbar")

    try:
        while True:
            frame = read_frame(cap)

            # TEMPORÄR: Belichtungszeit loggen
            if not IS_MAC and time.perf_counter() - last_log >= 1.0:
                last_log = time.perf_counter()
                print(f"[belichtung] {exposure_ms(cap):.2f} ms")
            # Auf eine Kopie zeichnen, damit der Klick die echten Farben misst
            view = frame.copy()

            if tracker.reference is None:
                lines = [
                    "Strecke leeren (kein Auto!), dann [b] fuer Referenzbild",
                    "[q] beenden",
                ]
            else:
                diff_mask = tracker.process(frame)
                center, radius, blue_mask = find_blue_dot(
                    frame, diff_mask, args.min_dot_area
                )
                if view_mode == 1:
                    view = cv2.cvtColor(diff_mask, cv2.COLOR_GRAY2BGR)
                elif view_mode == 2:
                    view = cv2.cvtColor(blue_mask, cv2.COLOR_GRAY2BGR)
                if center is not None:
                    # Dünner Ring knapp außerhalb des blauen Flecks, Mittelpunkt als einzelnes Pixel
                    cv2.circle(view, center, radius + 2, (0, 0, 255), 1, cv2.LINE_AA)
                    view[center[1], center[0]] = (0, 0, 255)
                lines = [
                    f"pos={center}" if center else "kein blauer Punkt erkannt",
                    f"thr={tracker.threshold} | [b] Referenz [m] Ansicht [+/-] Schwelle "
                    "[Klick] HSV [q] Ende",
                ]

            put_text(view, lines)
            cv2.imshow(WINDOW, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("b"):
                tracker.set_reference([read_frame(cap) for _ in range(args.ref_frames)])
                print(f"[ref] Referenzbild aus {args.ref_frames} Frames gemittelt")
            elif key == ord("m"):
                view_mode = (view_mode + 1) % 3
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
