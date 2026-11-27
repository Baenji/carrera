"""Kamera öffnen, Belichtung, Weißabgleich und Fokus sperren, Bilder lesen.

Übernommen aus experiments/car_diff_tracking/track_blue_dot.py.

Plattformen:
  Linux:   V4L2-Backend, Brio wird über /dev/v4l/by-id gefunden.
  Windows: DirectShow-Backend. Brio wird per Name gefunden, wenn `pygrabber` installiert ist
           (pip install pygrabber), sonst Kamera-Index 0.
           Die Belichtung ist dort in log2(Sekunden) anzugeben (z.B. -7 ≈ 8 ms).
  macOS:   Frames über PyAV (pip install av) statt OpenCV, weil OpenCV auf dem Mac nie einen
           Modus mit mehr als 30 fps wählt (Brio über PyAV: 720p mit 60 oder 90 fps).
           Die Kamera wird über ihren Namen geöffnet ("Logitech BRIO",
           andere Namen zeigt `ffmpeg -f avfoundation -list_devices true -i ""`).
           Belichtung usw. über uvc-util, muss einmal gebaut werden
           (siehe experiments/car_diff_tracking/README.md).
           Die Belichtung ist dort wie unter Linux in 100 µs anzugeben.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WINDOWS:
    # DirectShow statt MSMF: öffnet schneller und reicht Belichtung/Weißabgleich/Fokus an die Kamera durch
    BACKEND = cv2.CAP_DSHOW
    AE_AUTO, AE_MANUAL = 0.75, 0.25  # Konvention des DirectShow-Backends
    DEFAULT_EXPOSURE = -8  # log2(Sekunden): 2^-8 s ≈ 3,9 ms (wie 39 unter Linux)
elif IS_MAC:
    # Kein OpenCV-Backend: Frames kommen über PyAV, siehe MacCamera
    DEFAULT_EXPOSURE = 39  # uvc-util nutzt dieselbe Einheit wie Linux (100 µs): 3,9 ms
else:
    BACKEND = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    AE_AUTO, AE_MANUAL = 3, 1  # V4L2: 3 = auto (aperture priority), 1 = manuell
    DEFAULT_EXPOSURE = 39  # Einheiten von 100 µs: 3,9 ms, im Test besser als die Automatik


def find_brio() -> str | int:
    """Sucht die Logitech Brio. Fallback: Kamera-Index 0."""
    if IS_WINDOWS:
        try:
            from pygrabber.dshow_graph import FilterGraph  # optional, nur Windows
        except ImportError:
            print("[kamera] pygrabber nicht installiert -> nehme Index 0")
            return 0
        # Reihenfolge entspricht den DirectShow-Indizes von OpenCV
        for index, name in enumerate(FilterGraph().get_input_devices()):
            if "brio" in name.lower():
                return index
        return 0
    if IS_MAC:
        return "Logitech BRIO"  # PyAV öffnet die Kamera über ihren genauen Namen
    # Linux: index0 = eigentlicher Farbstream
    brio_paths = sorted(glob.glob("/dev/v4l/by-id/*BRIO*-video-index0"))
    return brio_paths[0] if brio_paths else 0


class MacCamera:
    """Kamera auf macOS über PyAV (ffmpeg, avfoundation).

    Hat dieselben Methoden read() und release() wie cv2.VideoCapture, damit der restliche
    Code nicht wissen muss, woher die Frames kommen.
    """

    def __init__(self, device: str, width: int, height: int, fps: int):
        import av  # nur auf macOS nötig

        try:
            self.container = av.open(
                device,
                format="avfoundation",
                options={"framerate": str(fps), "video_size": f"{width}x{height}"},
            )
        except av.error.FFmpegError as error:
            raise SystemExit(
                f"Kamera {device!r} konnte nicht geöffnet werden ({error}). Name prüfen mit: "
                'ffmpeg -f avfoundation -list_devices true -i ""\n'
                "Unterstützte Auflösungen/fps: ffmpeg -f avfoundation -video_size 1x1 "
                f'-i "{device}"'
            )
        self.stream = self.container.streams.video[0]
        print(f"[kamera] Modus: {self.stream.width}x{self.stream.height} @ {fps} fps (PyAV)")

    def read(self) -> tuple[bool, np.ndarray]:
        while True:
            try:
                packet = next(self.container.demux(self.stream))
            except BlockingIOError:
                # avfoundation meldet so "noch kein neuer Frame da" -> kurz warten, nochmal
                time.sleep(0.001)
                continue
            for frame in packet.decode():
                return True, frame.to_ndarray(format="bgr24")

    def release(self) -> None:
        self.container.close()


def open_camera(
    device: str | int, width: int, height: int, fps: int
) -> cv2.VideoCapture | MacCamera:
    if IS_MAC:
        return MacCamera(str(device), width, height, fps)
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    camera = cv2.VideoCapture(device, BACKEND)
    if not camera.isOpened():
        raise SystemExit(f"Kamera {device!r} konnte nicht geöffnet werden.")
    # MJPG ist nötig, damit die Brio 720p/1080p mit hoher FPS liefert (YUYV ist viel langsamer)
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    camera.set(cv2.CAP_PROP_FPS, fps)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    actual_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(
        f"[kamera] Modus: {actual_width}x{actual_height} @ {camera.get(cv2.CAP_PROP_FPS):.0f} fps"
    )
    return camera


def run_uvc_util(*arguments: str) -> str:
    """Ruft uvc-util für die erste UVC-Kamera auf (Index 0) und gibt die Ausgabe zurück."""
    result = subprocess.run(["uvc-util", "-I", "0", *arguments], capture_output=True, text=True)
    return result.stdout


def get_uvc_value(control: str) -> str:
    """Liest einen Wert, z.B. get_uvc_value("focus-abs") -> "10". uvc-util gibt "name = wert" aus."""
    return run_uvc_util("-g", control).split("=")[-1].strip()


def lock_camera_mac(camera: MacCamera, exposure: float | None, settle_seconds: float) -> None:
    """Wie lock_camera(), aber über uvc-util, weil OpenCV auf dem Mac nichts davon setzen kann."""
    if shutil.which("uvc-util") is None:
        print(
            "[kamera] WARNUNG: uvc-util nicht gefunden (siehe README). "
            "Belichtung/Weißabgleich/Fokus bleiben auf Automatik."
        )
        return
    # Automatik an (Belichtungsmodus 8 = Automatik der Brio) und einschwingen lassen
    run_uvc_util(
        "-s", "auto-exposure-mode=8", "-s", "auto-white-balance-temp=1", "-s", "auto-focus=1"
    )
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < settle_seconds:
        camera.read()

    exposure = int(exposure) if exposure is not None else int(get_uvc_value("exposure-time-abs"))
    white_balance = get_uvc_value("white-balance-temp")
    focus = get_uvc_value("focus-abs")
    # Modus 1 = manuell. Reihenfolge wichtig: erst Automatik aus, dann Wert setzen
    run_uvc_util(
        "-s", "auto-exposure-mode=1", "-s", f"exposure-time-abs={exposure}",
        "-s", "auto-white-balance-temp=0", "-s", f"white-balance-temp={white_balance}",
        "-s", "auto-focus=0", "-s", f"focus-abs={focus}",
    )  # fmt: skip
    print(
        f"[kamera] gesperrt: exposure={get_uvc_value('exposure-time-abs')} (x100µs)  "
        f"wb={get_uvc_value('white-balance-temp')}K  focus={get_uvc_value('focus-abs')}"
    )
    if get_uvc_value("auto-exposure-mode") != "1":
        print("[kamera] WARNUNG: Belichtung konnte nicht gesperrt werden")


def lock_camera(
    camera: cv2.VideoCapture | MacCamera, exposure: float | None, settle_seconds: float = 2.0
) -> None:
    """Automatik einschwingen lassen und dann einfrieren.

    Wichtig für die Differenzmethode: Würde die Kamera Belichtung/Weißabgleich nachregeln
    (z.B. weil ein dunkles Auto ins Bild fährt), ändert sich das ganze Bild und der
    Vergleich mit dem Referenzbild liefert überall Unterschiede.
    """
    if IS_MAC:
        lock_camera_mac(camera, exposure, settle_seconds)
        return
    camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, AE_AUTO)
    camera.set(cv2.CAP_PROP_AUTO_WB, 1)
    camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    start_time = time.perf_counter()
    while time.perf_counter() - start_time < settle_seconds:
        camera.read()

    exposure = exposure if exposure is not None else camera.get(cv2.CAP_PROP_EXPOSURE)
    white_balance = camera.get(cv2.CAP_PROP_WB_TEMPERATURE)
    focus = camera.get(cv2.CAP_PROP_FOCUS)
    steps = [
        ("Belichtung", cv2.CAP_PROP_AUTO_EXPOSURE, AE_MANUAL),
        ("Belichtung", cv2.CAP_PROP_EXPOSURE, exposure),
        ("Weißabgleich", cv2.CAP_PROP_AUTO_WB, 0),
        ("Weißabgleich", cv2.CAP_PROP_WB_TEMPERATURE, white_balance),
        ("Fokus", cv2.CAP_PROP_AUTOFOCUS, 0),
        ("Fokus", cv2.CAP_PROP_FOCUS, focus),
    ]
    failed = sorted({name for name, property_id, value in steps if not camera.set(property_id, value)})
    unit = "log2 s" if IS_WINDOWS else "x100µs"
    print(
        f"[kamera] gesperrt: exposure={exposure:g} ({unit})  wb={white_balance:.0f}K  focus={focus:.0f}"
    )
    if failed:
        print(f"[kamera] WARNUNG: konnte nicht sperren: {', '.join(failed)}")


def read_frame(camera: cv2.VideoCapture | MacCamera) -> np.ndarray:
    """Wartet auf das nächste Bild der Kamera und gibt es zurück."""
    ok, frame = camera.read()
    if not ok:
        raise SystemExit("Kein Frame von der Kamera erhalten.")
    return frame
