# Streckenerkennung per AprilTags (tag36h11)

Erkennt die Strecke aus den AprilTags auf den Schienenteilen und gibt die Reihenfolge der Teile aus.

```
tag_list = [0, 1, 3, 4, 4, 3, 4, 4, 2, 2, 4, 4, 1, 4, 4]
turns    = [None, None, None, 'R', 'R', None, 'L', 'R', None, None, 'R', 'R', None, 'L', 'R']
```

`tag_list` enthält die Tag-IDs in Fahrtrichtung, beginnend beim Start. `turns` sagt für jede Kurve, ob sie
links (`L`) oder rechts (`R`) herum geht. Das steht nicht in der `tag_list`, weil alle Kurven ID 4 haben.

## Tags und Klebe-Regeln

| ID | Teil | Länge | Oberkante des Tags zeigt |
|---|---|---|---|
| 0 | Start (mit Stromanschluss, genau einmal pro Strecke) | 114 mm | in Fahrtrichtung |
| 1 | kurze Gerade | 114 mm | in Fahrtrichtung (verkehrt herum stört nicht) |
| 2 | mittlere Gerade | 171 mm | in Fahrtrichtung (verkehrt herum stört nicht) |
| 3 | lange Gerade | 342 mm | in Fahrtrichtung (verkehrt herum stört nicht) |
| 4 | Kurve 90° | | zum Kurvenmittelpunkt |

Die Tags kleben mittig auf dem Teil, zwischen den Spuren. Druckvorlage: Branch `ak`,
`Documentation/generate_apriltags_pdf.py`.

## Starten

```bash
conda activate carrera            # braucht OpenCV, NumPy, pupil-apriltags
python experiments/track_detection/track_from_tags.py              # Kamera, Standbild in 4K
python experiments/track_detection/track_from_tags.py foto.png     # vorhandenes Foto auswerten
```

Die Logitech Brio wird wie in `car_diff_tracking/track_blue_dot.py` automatisch gefunden: unter Linux
über `/dev/v4l/by-id`, unter Windows per Name (braucht `pip install pygrabber`), unter macOS über ihren
Namen mit PyAV (braucht `pip install av`). Ohne PyAV geht es auf dem Mac auch über OpenCV mit
Kamera-Index, z. B. `--device 1`.

Mit Kamera werden 10 Frames aufgenommen. Ein Tag zählt, wenn er in mindestens der Hälfte davon erkannt
wurde. Das Foto wird als `strecke_foto.png` gespeichert, das Ergebnisbild als `strecke_ergebnis.png`
(beides im aktuellen Ordner, bitte nicht committen). Auf dem Ergebnisbild stehen Position in der Runde,
ID und Kurvenrichtung an jedem Tag.

| Option | Standard | Bedeutung |
|---|---|---|
| `--device` | Brio automatisch | Kamera als Index, Pfad oder Name (macOS) |
| `--width` / `--height` | 3840 / 2160 | Auflösung fürs Standbild |
| `--frames` | 10 | Anzahl Frames, über die gemittelt wird |
| `--no-window` | aus | Ergebnis nur speichern, nicht anzeigen |

## So entsteht die Reihenfolge

Für jedes Tag wird aus seiner Position, seiner Drehung und der Teillänge berechnet, wo die beiden Enden
seines Teils liegen. Bei einer Kurve liegt der Mittelpunkt in Richtung der Oberkante, die Enden 45° davor
und dahinter. Ab dem Start (Oberkante = Fahrtrichtung) wird immer das Teil angehängt, dessen Ende am
Ausgang des letzten Teils liegt. An welchem Ende man in eine Kurve hineinfährt, ergibt links oder rechts.

## Fehlermeldungen

| Meldung | Bedeutung |
|---|---|
| `kein Anschluss gefunden ... Fehlt dort ein Tag?` | Ein Tag wurde nicht erkannt (verdeckt, Spiegelung, zu klein im Bild). Die Meldung nennt das Teil davor. |
| `Die Runde schließt nicht` | Die Kette kommt nicht zum Start zurück, meist fehlt ebenfalls ein Tag. |
| `Tag(s) gehören nicht zur Runde` | Tags neben der Strecke, z. B. lose Teile im Bild. |
| `Rechts - Links = ..., erwartet ±4` | Ein Kurven-Tag ist vermutlich verdreht aufgeklebt. |
| `nur ... px pro Tag-Zelle` | Auflösung zu gering. Höhere Auflösung nehmen oder Kamera näher. |

## Im eigenen Code verwenden

```python
from track_from_tags import detect_tags, merge_frames, build_tag_list
from pupil_apriltags import Detector

detector = Detector(families="tag36h11", quad_decimate=1.0)
tags = merge_frames([detect_tags(gray, detector) for gray in graubilder])
tag_list, turns, _ = build_tag_list(tags)      # wirft TrackError, wenn die Strecke nicht aufgeht
```

## Offene Punkte

- `CURVE_RADIUS_MM = 173` ist geschätzt (innere Spur 144 mm + halber Spurabstand 29 mm). Gemeint ist der
  Abstand von der Tag-Mitte zum Kurvenmittelpunkt. Am einfachsten messen: 4 Kurven zum Kreis stecken,
  Abstand gegenüberliegender Tag-Mitten halbieren. Abweichungen von ±13 mm wurden getestet und stören nicht.
- Getestet ist das Skript bisher nur mit synthetischen Bildern, noch nicht mit der echten Kamera.
