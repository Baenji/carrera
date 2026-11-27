"""Auto finden: blauer Punkt, der nicht schon im Referenzbild war, dann Parallaxe korrigieren.

Übernommen aus experiments/car_diff_tracking/track_blue_dot.py (DiffTracker, find_blue_dot) und
experiments/car_to_track/car_to_track.py (correct_parallax).

Ablauf pro Bild (find_car):
  1. Das Bild wird mit dem Referenzbild verglichen -> Differenzmaske (alles, was neu ist).
  2. Im Originalbild werden die blauen Pixel gesucht (HSV-Farbbereich). Blau UND Differenzmaske
     = blaue Pixel, die nicht schon im Referenzbild waren. Der größte solche Fleck ist der Punkt
     auf dem Auto, sein Schwerpunkt ist die Position.
  3. Das Referenzbild wird langsam an das aktuelle Bild angeglichen, überall außer in einem
     Kreis um die letzte Position des blauen Punkts. So verschwinden Schatten, Lichtänderungen
     und neue Gegenstände nach kurzer Zeit von selbst, das Auto brennt aber nicht ein.
  4. Der Punkt liegt höher als die Bahn und erscheint deshalb zum Bildrand hin nach außen
     verschoben. Die Position wird auf die Stelle der Bahn direkt darunter zurückgerechnet.
"""

from __future__ import annotations

import cv2
import numpy as np

# Farbbereich des blauen Punkts in HSV (OpenCV: H 0-179, S und V 0-255).
# Kalibriert für den dunkleren Punkt bei fester Belichtung von 3,9 ms (camera.DEFAULT_EXPOSURE).
# H oben und S unten mit Puffer: an einer Stelle der Strecke lag der Punkt bei H=118, S=116.
BLUE_LOW = (104, 90, 40)
BLUE_HIGH = (125, 255, 255)
MIN_DOT_AREA = 15  # px: Mindestanzahl blauer Pixel, damit einzelne Rauschpixel nicht als Punkt zählen

# Bei anderem Aufbau neu messen
CAMERA_HEIGHT = 108.0  # cm: Kamera über der Bahn
DOT_HEIGHT = 2.0  # cm: blauer Punkt über der Bahn


class DiffTracker:
    """Liefert die Differenzmaske: weiß = anders als das Referenzbild der leeren Strecke.

    Das Referenzbild wird über update_reference() laufend nachgeführt.
    """

    def __init__(
        self,
        threshold: int = 20,
        blur: int = 5,
        scale: float = 0.5,
        reference_alpha: float = 0.05,
        protect_radius: int = 70,
    ):
        self.threshold = threshold  # Mindestdifferenz (0-255) für "anders als Referenz"
        self.blur = blur | 1  # Gauß-Kernel, bezogen aufs verkleinerte Bild, muss ungerade sein
        self.scale = scale  # Verarbeitung auf verkleinertem Bild -> deutlich schneller
        # Anpassungsrate des Referenzbilds pro Frame (0 = aus).
        # 0.05 ≈ 0.2 s Halbwertszeit bei 60 fps, 0.005 ≈ 2 s
        self.reference_alpha = reference_alpha
        # Schutzkreis ums Auto (px im Originalbild), muss das ganze Auto abdecken
        self.protect_radius = protect_radius
        self.reference: np.ndarray | None = None  # uint8, zum Vergleichen
        # float32-Kopie fürs Nachführen: kleine Änderungen (alpha * Differenz < 0.5)
        # würden in uint8 weggerundet und das Referenzbild würde sich nie bewegen
        self.reference_float: np.ndarray | None = None
        self.last_center: tuple[int, int] | None = None  # letzte bekannte Auto-Position
        self.current_frame: np.ndarray | None = None  # zuletzt vorverarbeiteter Frame
        self.kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self.kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        if self.scale != 1.0:
            frame = cv2.resize(
                frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA
            )
        # Leichtes Weichzeichnen unterdrückt Sensorrauschen und JPEG-Artefakte
        return cv2.GaussianBlur(frame, (self.blur, self.blur), 0)

    def set_reference(self, frames: list[np.ndarray]) -> None:
        """Referenzbild = Mittelwert über mehrere Frames (Rauschen mittelt sich heraus).

        Die Strecke muss dafür nicht leer sein: Was dabei im Bild war (Hand, stehendes Auto),
        wird durch update_reference() nach kurzer Zeit herausgerechnet. Ein Auto, das schon
        beim Start auf der Strecke steht, wird allerdings erst erkannt, sobald es losfährt.
        """
        self.reference_float = np.mean(
            [self.preprocess(frame).astype(np.float32) for frame in frames], axis=0
        ).astype(np.float32)
        self.reference = cv2.convertScaleAbs(self.reference_float)
        self.last_center = None

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Gibt die Differenzmaske in Originalauflösung zurück."""
        assert self.reference is not None
        current_frame = self.current_frame = self.preprocess(frame)
        # Differenz pro Farbkanal, dann Maximum über die Kanäle:
        # so fällt das Auto auch auf, wenn es nur in einem Kanal vom Referenzbild abweicht
        difference = cv2.absdiff(current_frame, self.reference)
        max_difference = cv2.max(
            cv2.max(difference[:, :, 0], difference[:, :, 1]), difference[:, :, 2]
        )
        _, mask = cv2.threshold(max_difference, self.threshold, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel_open)  # einzelne Rauschpixel weg
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel_close)  # Löcher im Auto schließen

        if self.scale != 1.0:
            mask = cv2.resize(
                mask, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        return mask

    def update_reference(self, car_position: tuple[int, int] | None) -> None:
        """Referenzbild an den zuletzt mit process() verarbeiteten Frame angleichen.

        car_position: aktuelle Position des blauen Punkts (Originalkoordinaten) oder None.
        Wird nach find_blue_dot() aufgerufen, weil erst dann bekannt ist, wo das Auto ist.
        Der Schutzkreis liegt um den blauen Punkt und nicht um die größte Differenzfläche,
        damit immer unser Auto geschützt wird und nicht z.B. eine Hand oder das zweite Auto.
        """
        if car_position is not None:
            self.last_center = car_position
        if self.reference_alpha <= 0 or self.current_frame is None:
            return
        # Referenz langsam an das aktuelle Bild angleichen (gleitender Mittelwert):
        #   ref = (1 - alpha) * ref + alpha * aktuelles Bild
        # Überall, außer in einem Kreis um die letzte Auto-Position. Wird der Punkt gerade
        # nicht erkannt (z.B. Bewegungsunschärfe), bleibt der Kreis an der letzten Position.
        update_mask = np.full(self.current_frame.shape[:2], 255, np.uint8)
        if self.last_center is not None:
            protected_center = (
                int(self.last_center[0] * self.scale),
                int(self.last_center[1] * self.scale),
            )
            cv2.circle(update_mask, protected_center, int(self.protect_radius * self.scale), 0, -1)
        cv2.accumulateWeighted(
            self.current_frame, self.reference_float, self.reference_alpha, mask=update_mask
        )
        self.reference = cv2.convertScaleAbs(self.reference_float)


def find_blue_dot(frame: np.ndarray, diff_mask: np.ndarray) -> tuple[int, int] | None:
    """Gibt den Mittelpunkt des blauen Punkts in px zurück oder None.

    frame:     BGR-Bild in Originalauflösung. Nicht verkleinern, der Punkt ist nur wenige Pixel groß.
    diff_mask: Differenzmaske vom DiffTracker in derselben Auflösung
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, BLUE_LOW, BLUE_HIGH)
    # Nur Blau, das nicht schon im Referenzbild war (z.B. blaue Dinge neben der Strecke)
    blue_mask = cv2.bitwise_and(blue_mask, diff_mask)

    # Zusammenhängende Flecken mit Pixelanzahl und Schwerpunkt. Label 0 ist der Hintergrund.
    label_count, _, stats, centroids = cv2.connectedComponentsWithStats(blue_mask)
    if label_count < 2:
        return None
    largest_label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[largest_label, cv2.CC_STAT_AREA] < MIN_DOT_AREA:
        return None
    center_x, center_y = centroids[largest_label]
    return int(round(center_x)), int(round(center_y))


def correct_parallax(
    position: tuple[int, int], frame_shape: tuple[int, ...]
) -> tuple[int, int]:
    """Rechnet die Position des Punkts auf die Stelle der Bahn direkt darunter zurück.

    Der Punkt erscheint um den Faktor H / (H - h) weiter von der Bildmitte entfernt als die
    Bahn unter ihm (H = CAMERA_HEIGHT, h = DOT_HEIGHT), also wird er um (H - h) / H zur
    Bildmitte hin gezogen.
    Annahme: Die Kamera schaut senkrecht nach unten (Bildmitte = Stelle unter der Kamera).
    """
    scale = (CAMERA_HEIGHT - DOT_HEIGHT) / CAMERA_HEIGHT
    center_x, center_y = frame_shape[1] / 2, frame_shape[0] / 2
    return (
        round(center_x + (position[0] - center_x) * scale),
        round(center_y + (position[1] - center_y) * scale),
    )


def find_car(tracker: DiffTracker, frame: np.ndarray) -> tuple[int, int] | None:
    """Gibt die Stelle der Bahn unter dem blauen Punkt in px zurück oder None, wenn nicht erkannt."""
    diff_mask = tracker.process(frame)
    dot_center = find_blue_dot(frame, diff_mask)
    tracker.update_reference(dot_center)
    if dot_center is None:
        return None
    return correct_parallax(dot_center, frame.shape)
