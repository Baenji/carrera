"""Strecke aus den AprilTags (tag36h11) erkennen und als tag_list ausgeben.

Ergebnis (im Terminal und in strecke.json):
  tag_list  Streckenteile in Fahrtrichtung, beginnend beim Start, z. B. [1, 3, "R", "R", "L", 3, ...]
            1 / 2 / 3 = kurze / mittlere / lange Gerade, "L" / "R" = Links- / Rechtskurve.
            Der Start steht als 1 an erster Stelle, weil er so lang ist wie eine kurze Gerade.

Wie die Reihenfolge entsteht:
  Aus Position und Drehung jedes Tags und den Teilemaßen wird berechnet, wo die beiden Enden
  seines Streckenteils liegen. Ab dem Start-Tag wird immer das Teil angehängt, dessen Ende am
  Ausgang des vorherigen Teils liegt.

Klebe-Regeln (Oberkante = die Seite, die im offiziellen Tag-Bild oben ist):
  Start (ID 0) und Geraden: Oberkante in Fahrtrichtung.
  Kurve (ID 4): Oberkante zum Kurvenmittelpunkt.
  Tags mittig auf dem Teil, zwischen den Spuren.

Aufruf (conda-Env "carrera", braucht OpenCV, NumPy und pupil-apriltags):
  python experiments/track_detection/track_from_tags.py              # Kamera, Standbild in 4K
  python experiments/track_detection/track_from_tags.py foto.png     # vorhandenes Foto
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from pupil_apriltags import Detector

# Tag-ID -> (Name, Länge in mm). Maße laut CLAUDE.md (Set "DTM High Speed Showdown").
PARTS = {
    0: ("Start", 114.0),
    1: ("kurze Gerade", 114.0),
    2: ("mittlere Gerade", 171.0),
    3: ("lange Gerade", 342.0),
    4: ("Kurve", None),  # 90°
}
START_ID, CURVE_ID = 0, 4
# Kurvenradien gemessen: innere Spur 144 mm (Bogen 226,2 mm), äußere Spur 201 mm (Bogen 315,7 mm).
# Das Tag klebt mittig zwischen den Spuren, sitzt also 172,5 mm vom Kurvenmittelpunkt entfernt.
CURVE_RADIUS_MM = (144.0 + 201.0) / 2
TAG_BLACK_MM = 26.4  # Kante des schwarzen Quadrats (33-mm-Tag = 10 Zellen à 3,3 mm, davon 8 schwarz umrandet)
# So weit dürfen die berechneten Enden zweier zusammengesteckter Teile auseinanderliegen (schief geklebte
# Tags, Perspektive). Kleiner als die kürzeste Gerade (114 mm), damit ein fehlendes Teil immer auffällt.
MAX_GAP_MM = 80.0


class TrackError(Exception):
    """Die Strecke ließ sich nicht eindeutig zusammensetzen."""


# --------------------------------
# Tags erkennen
# --------------------------------


def detect_tags(gray: np.ndarray, detector: Detector) -> list[dict]:
    """Nur fehlerfrei gelesene Tags (hamming == 0) mit bekannter ID."""
    tags = []
    for d in detector.detect(gray):
        if d.hamming != 0 or d.tag_id not in PARTS:
            continue
        c = d.corners  # pupil_apriltags: [unten links, unten rechts, oben rechts, oben links]
        up = (c[2] + c[3]) / 2 - d.center  # Richtung der Oberkante
        side_px = np.mean([np.linalg.norm(c[i] - c[i - 1]) for i in range(4)])
        tags.append(
            {
                "id": d.tag_id,
                "center": d.center,
                "up": up / np.linalg.norm(up),
                "px_per_mm": side_px / TAG_BLACK_MM,
            }
        )
    return tags


def merge_frames(per_frame: list[list[dict]]) -> list[dict]:
    """Erkennungen mehrerer Frames zusammenfassen. Ein Tag zählt, wenn er in mindestens der
    Hälfte der Frames an derselben Stelle gefunden wurde. Das hilft gegen Flackern."""
    groups: list[list[dict]] = []
    for tags in per_frame:
        for t in tags:
            for g in groups:
                same_place = np.linalg.norm(g[0]["center"] - t["center"]) < 5 * t["px_per_mm"]
                if g[0]["id"] == t["id"] and same_place:
                    g.append(t)
                    break
            else:
                groups.append([t])
    merged = []
    for g in groups:
        if 2 * len(g) >= len(per_frame):
            up = np.mean([t["up"] for t in g], axis=0)
            merged.append(
                {
                    "id": g[0]["id"],
                    "center": np.mean([t["center"] for t in g], axis=0),
                    "up": up / np.linalg.norm(up),
                    "px_per_mm": float(np.mean([t["px_per_mm"] for t in g])),
                }
            )
    return merged


# --------------------------------
# Strecke zusammensetzen
# --------------------------------


def rotate(v: np.ndarray, deg: float) -> np.ndarray:
    a = np.radians(deg)
    return np.array([v[0] * np.cos(a) - v[1] * np.sin(a), v[0] * np.sin(a) + v[1] * np.cos(a)])


def piece_ends(tag: dict) -> list[np.ndarray]:
    """Die beiden Enden des Streckenteils in Pixeln. Bei Geraden [hinten, vorne] in Fahrtrichtung."""
    s = tag["px_per_mm"]
    if tag["id"] == CURVE_ID:
        to_center = tag["up"] * CURVE_RADIUS_MM * s
        curve_center = tag["center"] + to_center
        # Das Tag sitzt in der Mitte des 90°-Bogens, die Enden liegen 45° davor und dahinter
        return [curve_center - rotate(to_center, 45), curve_center - rotate(to_center, -45)]
    half = tag["up"] * PARTS[tag["id"]][1] / 2 * s
    return [tag["center"] - half, tag["center"] + half]


def build_tag_list(tags: list[dict]) -> tuple[list[int | str], list[dict]]:
    """Tags in Fahrtrichtung ordnen. Gibt (tag_list, geordnete Tags) zurück, tag_list wie oben beschrieben."""
    starts = [t for t in tags if t["id"] == START_ID]
    if len(starts) != 1:
        raise TrackError(f"{len(starts)} Start-Tags (ID {START_ID}) gefunden, erwartet genau 1.")
    start = starts[0]
    mm = float(np.median([t["px_per_mm"] for t in tags]))  # nur um Lücken in mm anzugeben
    start_back, exit_pt = piece_ends(start)
    ordered, turns = [start], [None]
    rest = [t for t in tags if t is not start]

    while True:
        # Welches noch freie Teil hat ein Ende am Ausgang des letzten Teils?
        cands = [(np.linalg.norm(e - exit_pt), t, k) for t in rest for k, e in enumerate(piece_ends(t))]
        gap, best, k = min(cands, key=lambda c: c[0]) if cands else (np.inf, None, 0)
        closing_gap = np.linalg.norm(start_back - exit_pt)
        if closing_gap <= gap:  # das nächste Ende ist das hintere Ende des Starts
            if closing_gap / mm > MAX_GAP_MM:
                raise TrackError(f"Die Runde schließt nicht: {closing_gap / mm:.0f} mm Lücke vor dem Start.")
            break
        if gap / mm > MAX_GAP_MM:
            name = PARTS[ordered[-1]["id"]][0]
            raise TrackError(
                f"Nach Teil {len(ordered)} ({name}) kein Anschluss gefunden, das nächste Ende ist "
                f"{gap / mm:.0f} mm entfernt. Fehlt dort ein Tag oder wurde es nicht erkannt?"
            )
        ends = piece_ends(best)
        entry, exit_pt = ends[k], ends[1 - k]
        turn = None
        if best["id"] == CURVE_ID:
            # Liegt der Kurvenmittelpunkt rechts der Fahrtrichtung -> Rechtskurve (Bild-y zeigt nach unten)
            d = exit_pt - entry
            turn = "R" if d[0] * best["up"][1] - d[1] * best["up"][0] > 0 else "L"
        ordered.append(best)
        turns.append(turn)
        rest = [t for t in rest if t is not best]

    if rest:
        print(f"[WARNUNG] {len(rest)} Tag(s) gehören nicht zur Runde, IDs {[t['id'] for t in rest]}")
    if abs(turns.count("R") - turns.count("L")) != 4:
        print(f"[WARNUNG] Rechts - Links = {turns.count('R') - turns.count('L')}, erwartet ±4. Kurven-Tag verdreht?")
    tag_list = []
    for t, turn in zip(ordered, turns):
        if turn:  # Kurve -> "L" oder "R"
            tag_list.append(turn)
        elif t["id"] == START_ID:  # Start ist so lang wie die kurze Gerade (ID 1)
            tag_list.append(1)
        else:
            tag_list.append(t["id"])
    return tag_list, ordered


# --------------------------------
# Kamera und Anzeige
# --------------------------------


IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WINDOWS:
    BACKEND = cv2.CAP_DSHOW
else:
    BACKEND = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY


def find_brio() -> str | int:
    """Sucht die Logitech Brio. Fallback: Kamera-Index 0. (aus car_diff_tracking/track_blue_dot.py)"""
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
    if IS_MAC:
        return "Logitech BRIO"  # PyAV öffnet die Kamera über ihren genauen Namen
    # Linux: index0 = eigentlicher Farbstream
    hits = sorted(glob.glob("/dev/v4l/by-id/*BRIO*-video-index0"))
    return hits[0] if hits else 0


class MacCamera:
    """Kamera auf macOS über PyAV, weil OpenCV die Brio dort nicht per Name öffnen kann.
    Gleiche Methoden read() und release() wie cv2.VideoCapture. (aus car_diff_tracking/track_blue_dot.py)"""

    def __init__(self, device: str, width: int, height: int, fps: int):
        try:
            import av  # nur auf macOS nötig
        except ImportError:
            raise SystemExit(
                "PyAV fehlt: pip install av\n"
                "Oder ohne PyAV über OpenCV mit Kamera-Index starten, z. B. --device 1"
            )
        try:
            self.container = av.open(
                device, format="avfoundation", options={"framerate": str(fps), "video_size": f"{width}x{height}"}
            )
        except av.error.FFmpegError as e:
            raise SystemExit(
                f"Kamera {device!r} konnte nicht geöffnet werden ({e}). Name prüfen mit: "
                'ffmpeg -f avfoundation -list_devices true -i ""'
            )
        self.stream = self.container.streams.video[0]

    def read(self) -> tuple[bool, np.ndarray]:
        while True:
            try:
                packet = next(self.container.demux(self.stream))
            except BlockingIOError:  # avfoundation: noch kein neuer Frame da -> kurz warten
                time.sleep(0.001)
                continue
            for frame in packet.decode():
                return True, frame.to_ndarray(format="bgr24")

    def release(self) -> None:
        self.container.close()


def capture_frames(device: str, width: int, height: int, n: int) -> list[np.ndarray]:
    if IS_MAC and not device.isdigit():
        cap = MacCamera(device, width, height, fps=30)  # die Brio kann 4K nur mit 30 fps
    else:
        cap = cv2.VideoCapture(int(device) if device.isdigit() else device, BACKEND)
        if not cap.isOpened():
            raise SystemExit(f"Kamera {device!r} konnte nicht geöffnet werden.")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 2.0:  # Belichtungsautomatik einschwingen lassen
        cap.read()
    frames = [f for ok, f in (cap.read() for _ in range(n)) if ok]
    cap.release()
    if not frames:
        raise SystemExit("Kein Bild von der Kamera erhalten.")
    h, w = frames[0].shape[:2]
    print(f"[kamera] {w}x{h}, {len(frames)} Frames")
    return frames


def draw(img: np.ndarray, tags: list[dict], ordered: list[dict], tag_list: list) -> np.ndarray:
    out = img.copy()
    fs = max(img.shape[1] / 2000, 0.5)  # Schriftgröße passend zur Bildbreite
    for t in tags:  # alle erkannten Tags: Pfeil = Oberkante
        c = t["center"]
        tip = c + t["up"] * 20 * t["px_per_mm"]
        cv2.arrowedLine(out, tuple(map(int, c)), tuple(map(int, tip)), (0, 200, 255), max(int(2 * fs), 1))
    pts = np.array([t["center"] for t in ordered], np.int32)
    if len(pts) > 1:
        cv2.polylines(out, [pts], True, (0, 255, 0), max(int(3 * fs), 1))
    for i, (t, entry) in enumerate(zip(ordered, tag_list)):
        label = "0: Start" if i == 0 else f"{i}: {entry}"
        org = tuple(map(int, t["center"] + np.array([15, -15]) * fs))
        cv2.putText(out, label, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), int(5 * fs) + 1)
        cv2.putText(out, label, org, cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), int(2 * fs) + 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="Foto der Strecke. Ohne Angabe wird die Kamera benutzt.")
    ap.add_argument("--device", help="Kamera als Index, Pfad oder Name (macOS). Standard: Brio automatisch")
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--height", type=int, default=2160)
    ap.add_argument("--frames", type=int, default=10, help="Anzahl Frames, über die gemittelt wird")
    ap.add_argument("--no-window", action="store_true", help="Ergebnis nur speichern, nicht anzeigen")
    args = ap.parse_args()

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            raise SystemExit(f"Bild {args.image!r} konnte nicht gelesen werden.")
        frames = [frame]
    else:
        device = args.device if args.device is not None else str(find_brio())
        print(f"[kamera] Gerät: {device}")
        frames = capture_frames(device, args.width, args.height, args.frames)
        cv2.imwrite("strecke_foto.png", frames[-1])
        print("[kamera] Foto gespeichert: strecke_foto.png (zum erneuten Auswerten ohne Kamera)")

    detector = Detector(families="tag36h11", nthreads=4, quad_decimate=1.0, refine_edges=1, decode_sharpening=0.25)
    tags = merge_frames([detect_tags(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), detector) for f in frames])
    counts = {i: sum(t["id"] == i for t in tags) for i in PARTS}
    print(f"{len(tags)} Tags erkannt: " + ", ".join(f"{PARTS[i][0]} {n}" for i, n in counts.items()))
    if tags:
        cell_px = np.median([t["px_per_mm"] for t in tags]) * TAG_BLACK_MM / 8
        if cell_px < 3:
            print(f"[WARNUNG] nur {cell_px:.1f} px pro Tag-Zelle, unter 3 px wird die Erkennung unzuverlässig")

    ordered, tag_list, code = [], [], 0
    result_json = Path("strecke.json")
    names = {1: "kurze Gerade", 2: "mittlere Gerade", 3: "lange Gerade", "L": "Linkskurve", "R": "Rechtskurve"}
    try:
        tag_list, ordered = build_tag_list(tags)
        print(f"\ntag_list = {tag_list}\n")
        print(" -> ".join(["Start"] + [names[x] for x in tag_list[1:]]))
        result_json.write_text(json.dumps({"tag_list": tag_list}) + "\n")
        print(f"Ergebnis gespeichert: {result_json}")
    except TrackError as e:
        print(f"[FEHLER] {e}")
        if result_json.exists():  # sonst würde eine alte Strecke versehentlich weiterverwendet
            result_json.unlink()
            print(f"[FEHLER] alte {result_json} gelöscht")
        code = 1

    result = draw(frames[-1], tags, ordered, tag_list)
    cv2.imwrite("strecke_ergebnis.png", result)
    print("Ergebnisbild gespeichert: strecke_ergebnis.png")
    if not args.no_window:
        scale = min(1.0, 1400 / result.shape[1])
        cv2.imshow("Streckenerkennung", cv2.resize(result, None, fx=scale, fy=scale))
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return code


if __name__ == "__main__":
    sys.exit(main())
