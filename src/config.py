"""Werte, die pro Aufbau angepasst werden: andere Spur, andere Kamera, anderer Raum.

Parameter der Algorithmen (Schwellwerte, Glättung usw.) bleiben in ihren Modulen.
"""

# Spur, auf der das Modell fährt, in Fahrtrichtung gesehen: "links" oder "rechts".
# Wird beim Einrichten der Strecke in track_map.json übernommen, weil das Polygon auf genau dieser
# Spur aufgenommen wird. Nach einer Änderung die Strecke neu einrichten.
LANE = "rechts"

# Kamera: Pfad, Index oder Name. None = Logitech Brio suchen
CAMERA_DEVICE = None
# Eine Auflösung für alles, damit Polygon und AprilTags dieselben Pixelkoordinaten haben.
# Nach einer Änderung die Strecke neu einrichten.
CAMERA_WIDTH_PX = 1280
CAMERA_HEIGHT_PX = 720
CAMERA_FPS = 60

# Für die Parallaxe-Korrektur, bei anderem Aufbau neu messen
CAMERA_HEIGHT_ABOVE_TRACK_CM = 108.0
DOT_HEIGHT_ABOVE_TRACK_CM = 2.0

# Farbbereich des blauen Punkts in HSV (OpenCV: H 0-179, S und V 0-255). Hängt vom Licht ab,
# in einem anderen Raum neu kalibrieren.
# Kalibriert für den dunkleren Punkt bei fester Belichtung von 3,9 ms (camera.DEFAULT_EXPOSURE).
# H oben und S unten mit Puffer: an einer Stelle der Strecke lag der Punkt bei H=118, S=116.
BLUE_DOT_HSV_LOW = (104, 90, 40)
BLUE_DOT_HSV_HIGH = (125, 255, 255)
