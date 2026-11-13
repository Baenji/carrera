"""Auto-Tracking per Hintergrund-Differenz (ohne Farbmarkierung) + gelernte Streckenmaske.

Ablauf (manuell):
  1. Kamera öffnen, Automatik (Belichtung/Weißabgleich/Fokus) einschwingen lassen und dann sperren.
  2. Strecke OHNE Auto -> [b] -> Hintergrund = Mittel aus mehreren Frames.
  3. [l] Lernmodus: Auto von Hand ein paar Runden fahren.
     Jede erkannte Auto-Silhouette wird aufsummiert -> daraus entsteht die Spurmaske
     (nur die Spur, auf der das Auto fährt). Sie wird als PNG gespeichert und beim
     nächsten Start geladen.
  4. Tracking: Es zählen nur Differenz-Regionen, die zum größten Teil auf der Spurmaske
     liegen. Der Punkt wird aber aus der vollständigen Region berechnet.

Tasten im Fenster:
  b  Hintergrund aufnehmen (Strecke muss leer sein!)
  l  Spurmaske lernen (Auto dabei von Hand fahren)
  k  Spurmaske anzeigen ein/aus     x  Spurmaske verwerfen
  m  Differenzmaske ein/aus         t  Spur (Trail) ein/aus
  u  langsames Nachführen des Hintergrunds ein/aus (gegen Lichtdrift)
  +/- Schwellwert                   s  Screenshot
  q / ESC  beenden

Start (im conda env "carrera", aus dem Repo-Root):
  python experiments/car_diff_tracking/track_car.py

Plattformen:
  Linux:   V4L2-Backend, Brio wird über /dev/v4l/by-id gefunden.
  Windows: DirectShow-Backend. Brio wird per Name gefunden, wenn `pygrabber` installiert ist
           (pip install pygrabber), sonst Kamera-Index 0 -> ggf. --device 1 angeben.
           --exposure ist dort in log2(Sekunden) anzugeben (z.B. -7 ≈ 8 ms).
"""

from __future__ import annotations

import argparse
import csv
import glob
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
WINDOW = "Car Diff Tracking"

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    # DirectShow statt MSMF: öffnet schneller und reicht Belichtung/Weißabgleich/Fokus an die Kamera durch
    BACKEND = cv2.CAP_DSHOW
    AE_AUTO, AE_MANUAL = 0.75, 0.25   # Konvention des DirectShow-Backends
else:
    BACKEND = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    AE_AUTO, AE_MANUAL = 3, 1         # V4L2: 3 = auto (aperture priority), 1 = manuell

# UI-Callback: bekommt das anzuzeigende Bild, gibt den Tastencode zurück (-1 = keine Taste).
# Im Headless-Betrieb einfach None übergeben.
UI = Callable[[np.ndarray], int] | None


class Aborted(Exception):
    pass


def ellipse(r: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r))


# cv2.imread/imwrite können unter Windows keine Pfade mit Umlauten o.ä. -> über Bytes gehen
def imread_any(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        return cv2.imdecode(np.fromfile(str(path), np.uint8), flags)
    except OSError:
        return None


def imwrite_any(path: Path, img: np.ndarray) -> bool:
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return ok


# --------------------------------------------------------------------------- Kamera

def find_brio() -> str | int:
    """Sucht die Logitech Brio. Fallback: Kamera-Index 0."""
    if IS_WINDOWS:
        try:
            from pygrabber.dshow_graph import FilterGraph  # optional, nur Windows
        except ImportError:
            print("[kamera] pygrabber nicht installiert -> nehme Index 0 (sonst --device 1, 2, ...)")
            return 0
        # Reihenfolge entspricht den DirectShow-Indizes von OpenCV
        for i, name in enumerate(FilterGraph().get_input_devices()):
            if "brio" in name.lower():
                return i
        return 0
    # Linux: index0 = eigentlicher Farbstream
    hits = sorted(glob.glob("/dev/v4l/by-id/*BRIO*-video-index0"))
    return hits[0] if hits else 0


def open_camera(device: str | int, width: int, height: int, fps: int) -> cv2.VideoCapture:
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


def lock_camera(cap: cv2.VideoCapture, exposure: float | None, settle_s: float = 2.0) -> None:
    """Automatik einschwingen lassen und dann einfrieren.

    Wichtig für die Differenzmethode: Würde die Kamera Belichtung/Weißabgleich nachregeln
    (z.B. weil ein dunkles Auto ins Bild fährt), ändert sich das ganze Bild und der
    Vergleich mit dem Hintergrund liefert überall Unterschiede.
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
        ("Belichtung", cv2.CAP_PROP_AUTO_EXPOSURE, AE_MANUAL), ("Belichtung", cv2.CAP_PROP_EXPOSURE, exp),
        ("Weißabgleich", cv2.CAP_PROP_AUTO_WB, 0), ("Weißabgleich", cv2.CAP_PROP_WB_TEMPERATURE, wb),
        ("Fokus", cv2.CAP_PROP_AUTOFOCUS, 0), ("Fokus", cv2.CAP_PROP_FOCUS, focus),
    ]
    failed = sorted({name for name, prop, val in steps if not cap.set(prop, val)})
    unit = "log2 s" if IS_WINDOWS else "x100µs"
    print(f"[kamera] gesperrt: exposure={exp:g} ({unit})  wb={wb:.0f}K  focus={focus:.0f}")
    if failed:
        # Backend/Kamera unterstützt das Sperren nicht -> Differenzbild kann bei Lichtwechsel "aufblühen"
        print(f"[kamera] WARNUNG: konnte nicht sperren: {', '.join(failed)}")


def read_frame(cap: cv2.VideoCapture) -> np.ndarray:
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Kein Frame von der Kamera erhalten.")
    return frame


# --------------------------------------------------------------------------- Tracking

@dataclass
class Detection:
    center: tuple[int, int]   # Originalauflösung
    area: float               # Originalauflösung (px)
    contour: np.ndarray       # Originalauflösung
    contour_small: np.ndarray  # Verarbeitungsauflösung
    on_track: float | None    # Anteil der Region auf der Spurmaske (None = keine Maske)


class DiffTracker:
    def __init__(self, threshold: int, min_area: int, blur: int, bg_alpha: float, scale: float,
                 min_overlap: float):
        self.threshold = threshold
        self.min_area = min_area          # in Pixeln des Originalbilds
        self.blur = blur | 1              # muss ungerade sein
        self.bg_alpha = bg_alpha
        self.scale = scale                # Verarbeitung auf verkleinertem Bild -> deutlich schneller
        self.min_overlap = min_overlap
        self.bg_float: np.ndarray | None = None    # für langsames Nachführen
        self.background: np.ndarray | None = None  # uint8, vorverarbeitet
        self.track_mask: np.ndarray | None = None  # uint8 0/255, Verarbeitungsauflösung
        self.adapt = False
        self.k_open = ellipse(3)
        self.k_close = ellipse(9)

    # ---- Vorverarbeitung / Hintergrund

    def prep(self, frame: np.ndarray) -> np.ndarray:
        if self.scale != 1.0:
            frame = cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        # Leichtes Weichzeichnen unterdrückt Sensorrauschen und JPEG-Artefakte
        return cv2.GaussianBlur(frame, (self.blur, self.blur), 0)

    def set_background_prepped(self, bg: np.ndarray) -> None:
        self.bg_float = bg.astype(np.float32)
        self.background = cv2.convertScaleAbs(self.bg_float)

    def set_background(self, frames: list[np.ndarray]) -> None:
        """Mittelwert -> für Frames einer leeren Strecke."""
        self.set_background_prepped(np.mean([self.prep(f).astype(np.float32) for f in frames], axis=0))

    # ---- Spurmaske

    def set_track_mask_full(self, mask_full: np.ndarray) -> None:
        h, w = self.background.shape[:2] if self.background is not None else (
            int(round(mask_full.shape[0] * self.scale)), int(round(mask_full.shape[1] * self.scale)))
        self.track_mask = cv2.resize(mask_full, (w, h), interpolation=cv2.INTER_NEAREST)

    def track_mask_full(self, shape: tuple[int, int]) -> np.ndarray | None:
        if self.track_mask is None:
            return None
        return cv2.resize(self.track_mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)

    def _overlap(self, c: np.ndarray) -> float:
        """Anteil der (gefüllten) Kontur, der auf der Spurmaske liegt. Rechnet nur im Bounding-Box-ROI."""
        x, y, w, h = cv2.boundingRect(c)
        blob = np.zeros((h, w), np.uint8)
        cv2.drawContours(blob, [c - (x, y)], -1, 255, -1)
        total = cv2.countNonZero(blob)
        if total == 0:
            return 0.0
        inside = cv2.countNonZero(cv2.bitwise_and(blob, self.track_mask[y:y + h, x:x + w]))
        return inside / total

    # ---- Hauptschritt

    def process(self, frame: np.ndarray, use_mask: bool = True) -> tuple[Detection | None, np.ndarray]:
        assert self.background is not None
        cur = self.prep(frame)
        # Differenz pro Farbkanal, dann Maximum über die Kanäle:
        # so fällt das Auto auch auf, wenn es nur in einem Kanal vom Hintergrund abweicht
        d = cv2.absdiff(cur, self.background)
        diff = cv2.max(cv2.max(d[:, :, 0], d[:, :, 1]), d[:, :, 2])
        _, mask = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.k_open)    # einzelne Rauschpixel weg
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.k_close)  # Löcher im Auto schließen

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area_small = self.min_area * self.scale ** 2
        best, best_area, best_ov = None, 0.0, None
        masked = use_mask and self.track_mask is not None
        for c in contours:
            a = cv2.contourArea(c)
            if a < min_area_small or a <= best_area:
                continue
            ov = None
            if masked:
                # Maske entscheidet nur, OB die Region das Auto ist. Die Region selbst wird nicht
                # beschnitten -> Punkt verrutscht nicht, wenn das Auto über den Rand ragt.
                ov = self._overlap(c)
                if ov < self.min_overlap:
                    continue
            best, best_area, best_ov = c, a, ov

        det = None
        if best is not None:
            m = cv2.moments(best)
            if m["m00"] > 0:
                cx, cy = m["m10"] / m["m00"] / self.scale, m["m01"] / m["m00"] / self.scale
                contour = (best.astype(np.float32) / self.scale).astype(np.int32)
                det = Detection((int(round(cx)), int(round(cy))), best_area / self.scale ** 2,
                                contour, best, best_ov)

        if self.adapt:
            # Hintergrund langsam nachführen, aber NICHT dort, wo gerade etwas erkannt wird
            # (sonst "brennt" ein stehendes Auto in den Hintergrund ein)
            keep = cv2.dilate(mask, self.k_close, iterations=3)
            cv2.accumulateWeighted(cur, self.bg_float, self.bg_alpha, mask=cv2.bitwise_not(keep))
            self.background = cv2.convertScaleAbs(self.bg_float)

        if self.scale != 1.0:
            mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST)
        return det, mask


# --------------------------------------------------------------------------- Hintergrund & Lernen

def put_text(img: np.ndarray, lines: list[str], org=(10, 25)) -> None:
    x, y = org
    for line in lines:
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        y += 24


def _show(ui: UI, view: np.ndarray) -> None:
    if ui is not None and ui(view) in (ord("q"), 27):
        raise Aborted()


def capture_background(cap, tracker: DiffTracker, n: int, ui: UI = None) -> None:
    """Leere Strecke: Mittelwert über n Frames."""
    frames = []
    for i in range(n):
        f = read_frame(cap)
        frames.append(f)
        if ui:
            v = f.copy()
            put_text(v, [f"Hintergrund (leere Strecke) ... {i + 1}/{n}"])
            _show(ui, v)
    tracker.set_background(frames)
    print(f"[bg] Hintergrund aus {n} Frames gemittelt")


@dataclass
class LearnResult:
    laps: int
    seconds: float
    frames_used: int
    reason: str


def learn_track_mask(cap, tracker: DiffTracker, laps: int, timeout: float, min_hits: int, margin: int,
                     ui: UI = None) -> LearnResult:
    """Summiert die Auto-Silhouetten über `laps` Runden und baut daraus die Spurmaske.

    Rundenerkennung: Runde zählt, wenn das Auto nach >= 60 % der ersten Rundenlänge (bzw.
    vor der ersten Runde nach einer Mindeststrecke) wieder in die Nähe des Startpunkts kommt.
    """
    assert tracker.background is not None
    h, w = tracker.background.shape[:2]
    counts = np.zeros((h, w), np.uint16)
    blob = np.zeros((h, w), np.uint8)
    start: tuple[int, int] | None = None
    last: tuple[int, int] | None = None
    dist = 0.0              # zurückgelegte Strecke seit Rundenbeginn (px, Originalauflösung)
    lap_len: float | None = None
    done_laps, used = 0, 0
    near_r = 60             # px, "wieder am Start"
    t0 = time.time()
    reason = "ok"

    while done_laps < laps:
        frame = read_frame(cap)
        now = time.time()
        det, _ = tracker.process(frame, use_mask=False)
        if det is not None:
            blob[:] = 0
            cv2.drawContours(blob, [det.contour_small], -1, 1, -1)
            counts += blob
            used += 1
            if start is None:
                start = last = det.center
            else:
                dist += float(np.hypot(det.center[0] - last[0], det.center[1] - last[1]))
                last = det.center
                min_dist = 0.6 * lap_len if lap_len else 8 * near_r
                if dist > min_dist and np.hypot(det.center[0] - start[0], det.center[1] - start[1]) < near_r:
                    done_laps += 1
                    lap_len = lap_len or dist
                    print(f"[lernen] Runde {done_laps}/{laps} ({dist:.0f} px, {now - t0:.1f}s)")
                    dist = 0.0
        if now - t0 > timeout:
            reason = f"Timeout nach {timeout:.0f}s"
            break
        if ui:
            v = frame.copy()
            heat = cv2.resize((counts > 0).astype(np.uint8) * 255, (frame.shape[1], frame.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
            v[heat > 0] = (0.5 * v[heat > 0] + (0, 127, 0)).astype(np.uint8)
            if det is not None:
                cv2.circle(v, det.center, 8, (0, 0, 255), -1)
            put_text(v, [f"Lerne Spurmaske: Runde {done_laps}/{laps}  ({now - t0:.0f}s)", "[q] abbrechen"])
            _show(ui, v)

    if used == 0:
        return LearnResult(done_laps, time.time() - t0, used, reason + " - keine Detektionen, Maske unverändert")

    # Pixel, die mehrfach vom Auto bedeckt waren = Spur. Einzelne Ausreißer (Hand, Schatten) fallen raus.
    m = (counts >= min_hits).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ellipse(15))  # Lücken zwischen Frames schließen
    n_cc, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n_cc > 1:  # nur die größte zusammenhängende Fläche behalten
        m = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) * 255
    margin_small = max(1, int(round(margin * tracker.scale)))
    m = cv2.dilate(m, ellipse(2 * margin_small + 1))
    tracker.track_mask = m
    return LearnResult(done_laps, time.time() - t0, used, reason)


def save_mask(tracker: DiffTracker, path: Path, shape: tuple[int, int]) -> None:
    if imwrite_any(path, tracker.track_mask_full(shape)):
        print(f"[maske] gespeichert: {path}")
    else:
        print(f"[maske] FEHLER beim Speichern: {path}")


def draw_mask_outline(view: np.ndarray, mask_full: np.ndarray) -> None:
    cnts, _ = cv2.findContours(mask_full, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(view, cnts, -1, (0, 200, 0), 1)


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("Kamera")
    g.add_argument("--device", default=None, help="Kamera (Pfad oder Index). Default: Brio automatisch suchen")
    g.add_argument("--width", type=int, default=1280)
    g.add_argument("--height", type=int, default=720)
    g.add_argument("--fps", type=int, default=60)
    g.add_argument("--exposure", type=float, default=None,
                   help="Feste Belichtung. Linux: 100µs-Einheiten (z.B. 100 = 10ms, flickerfrei bei 50Hz-Licht). "
                        "Windows: log2(Sekunden), z.B. -7 ≈ 8ms. Default: Wert der Automatik übernehmen")
    g = ap.add_argument_group("Erkennung")
    g.add_argument("--threshold", type=int, default=30, help="Mindestdifferenz (0-255) für 'anders als Hintergrund'")
    g.add_argument("--min-area", type=int, default=300, help="Mindestfläche (px) einer Region, um als Auto zu gelten")
    g.add_argument("--blur", type=int, default=5, help="Gauß-Kernel (ungerade, bezogen aufs verkleinerte Bild)")
    g.add_argument("--scale", type=float, default=0.5, help="Verkleinerungsfaktor für die Verarbeitung")
    g.add_argument("--bg-frames", type=int, default=30, help="Anzahl Frames für das Hintergrundbild")
    g.add_argument("--bg-alpha", type=float, default=0.01, help="Lernrate für das Nachführen ([u])")
    g.add_argument("--min-overlap", type=float, default=0.7,
                   help="Mindestanteil einer Region auf der Spurmaske, um als Auto zu gelten")
    g = ap.add_argument_group("Spurmaske / Lernen")
    g.add_argument("--mask", type=Path, default=HERE / "track_mask.png", help="Datei der Spurmaske (laden/speichern)")
    g.add_argument("--learn-laps", type=int, default=2)
    g.add_argument("--learn-timeout", type=float, default=120.0, help="Sekunden")
    g.add_argument("--min-hits", type=int, default=2, help="Wie oft ein Pixel vom Auto bedeckt sein muss")
    g.add_argument("--margin", type=int, default=6, help="Rand um die gelernte Spur (px, Originalauflösung)")
    g = ap.add_argument_group("Ausgabe")
    g.add_argument("--trail", type=int, default=60, help="Länge der gezeichneten Spur in Frames")
    g.add_argument("--csv", default=None, help="Positionen in diese CSV-Datei schreiben")
    args = ap.parse_args()

    device = args.device if args.device is not None else find_brio()
    print(f"[kamera] öffne {device}")
    cap = open_camera(device, args.width, args.height, args.fps)
    lock_camera(cap, args.exposure)
    shape = (args.height, args.width)

    tracker = DiffTracker(args.threshold, args.min_area, args.blur, args.bg_alpha, args.scale, args.min_overlap)
    if args.mask.exists():
        m = imread_any(args.mask, cv2.IMREAD_GRAYSCALE)
        if m is not None and m.shape == shape:
            tracker.set_track_mask_full(m)
            print(f"[maske] geladen: {args.mask}")
        else:
            print(f"[maske] {args.mask} passt nicht zur Auflösung, ignoriert")

    trail: deque[tuple[int, int]] = deque(maxlen=args.trail)
    show_mask = False
    show_track = True
    show_trail = True
    csv_file = open(args.csv, "w", newline="") if args.csv else None
    writer = csv.writer(csv_file) if csv_file else None
    if writer:
        writer.writerow(["t", "frame", "x", "y", "area", "on_track"])

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def ui(view: np.ndarray) -> int:
        cv2.imshow(WINDOW, view)
        return cv2.waitKey(1) & 0xFF

    def run_learning() -> None:
        try:
            res = learn_track_mask(cap, tracker, args.learn_laps, args.learn_timeout, args.min_hits,
                                   args.margin, ui=ui)
            print(f"[lernen] {res.laps} Runden, {res.frames_used} Frames, {res.seconds:.1f}s: {res.reason}")
            if tracker.track_mask is not None and res.frames_used:
                save_mask(tracker, args.mask, shape)
        except Aborted:
            print("[lernen] abgebrochen")

    t_start = t_last = time.perf_counter()
    fps = 0.0
    frame_idx = 0
    try:
        while True:
            frame = read_frame(cap)
            frame_idx += 1
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - t_last, 1e-6))
            t_last = now

            if tracker.background is None:
                view = frame
                put_text(view, ["Strecke leeren (kein Auto!), dann [b] fuer Hintergrund", "[q] beenden"])
            else:
                t0 = time.perf_counter()
                det, mask = tracker.process(frame)
                proc_ms = (time.perf_counter() - t0) * 1000

                view = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if show_mask else frame
                if show_track and tracker.track_mask is not None:
                    draw_mask_outline(view, tracker.track_mask_full(shape))
                if det is not None:
                    trail.append(det.center)
                    cv2.drawContours(view, [det.contour], -1, (0, 255, 255), 1)
                    cv2.circle(view, det.center, 8, (0, 0, 255), -1)
                    cv2.circle(view, det.center, 9, (255, 255, 255), 2)
                if show_trail and len(trail) > 1:
                    cv2.polylines(view, [np.array(trail, np.int32)], False, (255, 0, 255), 2)

                if writer:
                    writer.writerow([f"{now - t_start:.4f}", frame_idx,
                                     det.center[0] if det else "", det.center[1] if det else "",
                                     f"{det.area:.0f}" if det else "",
                                     f"{det.on_track:.2f}" if det and det.on_track is not None else ""])

                if det:
                    ov = f" auf Spur={det.on_track:.0%}" if det.on_track is not None else " (keine Spurmaske)"
                    status = f"pos={det.center} area={det.area:.0f}{ov}"
                else:
                    status = "kein Auto erkannt"
                put_text(view, [
                    f"{fps:5.1f} fps | proc {proc_ms:4.1f} ms | thr={tracker.threshold} "
                    f"| adapt={'an' if tracker.adapt else 'aus'}",
                    status,
                    "[b] Hintergrund [l] Lernen [k] Maske zeigen [x] Maske weg [m] Diff [t] Spur [u] Nachf. "
                    "[+/-] Schwelle [s] Shot [q] Ende",
                ])

            key = ui(view)
            if key in (ord("q"), 27):
                break
            elif key == ord("b"):
                capture_background(cap, tracker, args.bg_frames, ui)
                trail.clear()
            elif key == ord("l"):
                if tracker.background is None:
                    print("[lernen] erst Hintergrund aufnehmen ([b])")
                else:
                    run_learning()
                    trail.clear()
            elif key == ord("k"):
                show_track = not show_track
            elif key == ord("x"):
                tracker.track_mask = None
                print("[maske] verworfen (Datei bleibt erhalten)")
            elif key == ord("m"):
                show_mask = not show_mask
            elif key == ord("t"):
                show_trail = not show_trail
                trail.clear()
            elif key == ord("u"):
                tracker.adapt = not tracker.adapt
            elif key in (ord("+"), ord("=")):
                tracker.threshold = min(255, tracker.threshold + 5)
            elif key == ord("-"):
                tracker.threshold = max(5, tracker.threshold - 5)
            elif key == ord("s"):
                name = time.strftime("shot_%Y%m%d_%H%M%S.png")
                imwrite_any(Path(name), view)
                print(f"[shot] {name} gespeichert")
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    except Aborted:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
