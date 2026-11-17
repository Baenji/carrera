# Auto-Tracking per Referenzbild-Differenz

Erkennt das Auto ohne Farbmarkierung: Jedes Kamerabild wird mit einem Bild der leeren Strecke
verglichen. Die größte Region mit Unterschieden gilt als Auto, ihr Mittelpunkt wird als roter Punkt
eingezeichnet.

## Voraussetzungen

- python: Python 3.11, OpenCV, NumPy
- Kamera fest über der Strecke montiert (getestet mit Logitech Brio)
- Linux oder Windows

## Starten

```bash
conda activate carrera
python experiments/car_diff_tracking/track_car.py
```

Die Logitech Brio Kamera wird automatisch gefunden. Unter Windows funktioniert das nur mit `pip install pygrabber`.
Ohne das Paket wird Kamera 0 genommen, eine andere Kamera wählst du mit `--device 1`.

## Benutzung

1. Skript starten und ca. 2 s warten. Belichtung, Weißabgleich und Fokus werden eingestellt und dann gesperrt.
2. Auto von der Strecke nehmen, keine Hände oder Schatten im Bild → **`b`** drücken.
   Das Referenzbild wird aus 30 Frames gemittelt.
3. Auto aufsetzen und fahren. Der rote Punkt zeigt die erkannte Position.

Während der Fahrt gleicht sich das Referenzbild laufend an das aktuelle Bild an, überall außer in einem
Kreis um die letzte Auto-Position. Lichtänderungen, Schatten und neue Gegenstände verschwinden so nach
2–4 s von selbst, das Auto (auch ein stehendes) brennt nicht ein. `b` bleibt der manuelle Reset.

| Taste | Funktion |
|---|---|
| `b` | Referenzbild (neu) aufnehmen, Strecke muss leer sein |
| `m` | Differenzmaske anzeigen (weiß = anders als Referenz) |
| `+` / `-` | Schwellwert erhöhen / verringern |
| `q` / `ESC` | Beenden |

## Optionen

| Option | Standard | Bedeutung |
|---|---|---|
| `--device` | Brio automatisch | Kamera als Index oder Pfad |
| `--width` / `--height` / `--fps` | 1280 / 720 / 60 | Kameramodus |
| `--exposure` | von der Automatik | Feste Belichtung. Linux in 100 µs (`100` = 10 ms), Windows in log2 s (`-7` ≈ 8 ms) |
| `--threshold` | 30 | Ab welcher Farbdifferenz (0–255) ein Pixel als verändert gilt |
| `--min-area` | 300 | Mindestgröße (px) einer Region, um als Auto zu gelten |
| `--blur` | 5 | Glättung gegen Rauschen |
| `--scale` | 0.5 | Verkleinerung für die Verarbeitung (schneller) |
| `--ref-frames` | 30 | Anzahl Frames für das Referenzbild |
| `--ref-alpha` | 0.005 | Wie schnell sich das Referenzbild anpasst (`0` = aus). 0.005 ≈ 2 s Halbwertszeit bei 60 fps |
| `--protect-radius` | 70 | Radius (px) um das Auto, in dem das Referenzbild nicht angepasst wird. Muss größer als das Auto sein |

## Im eigenen Code verwenden

```python
from track_car import DiffTracker

tracker = DiffTracker(threshold=30, min_area=300, blur=5, scale=0.5, ref_alpha=0.005, protect_radius=70)
tracker.set_reference(frames_leere_strecke)   # Liste von BGR-Bildern
center, mask = tracker.process(frame)         # center = (x, y) oder None
```

## Tipps und Grenzen

- **Licht ändert sich, Schatten, neuer Gegenstand** → verschwindet nach 2–4 s von selbst. In dieser Zeit
  kann der Punkt falsch liegen.
- **Kamera wurde bewegt** → `b` drücken (geht auch von selbst, dauert aber und ist währenddessen unbrauchbar).
- **Stehender Gegenstand größer als das Auto, aber kleiner als der Schutzkreis** (z.B. eine Hand, die
  liegen bleibt) kann sich als „Auto“ selbst schützen → `b` drücken.
- **Zweites Auto bleibt lange stehen** → wird in die Referenz übernommen. Fährt es weg, bleibt dort kurz
  (≈ 2 s) ein „Geist“.
- **Rauschen oder Schatten werden erkannt** → Schwellwert erhöhen (`+`).
- **Teile des Autos fehlen in der Maske** → Schwellwert senken (`-`).
- **Bild flackert** (50-Hz-Licht) → feste Belichtung setzen, z.B. `--exposure 100` (Linux).
- Es wird immer die **größte** Veränderung genommen. Hände, Schatten oder ein zweites Auto, die größer
  sind als das eigene Auto, werden stattdessen erkannt.

## Advanced-Version (`track_car_advanced.py`)

Gleiche Bedienung, zusätzlich:

- **Spurmaske lernen (`l`)**: Du fährst 2 Runden, das Skript merkt sich die befahrene Spur und speichert
  sie als `track_mask.png`. Danach zählen nur noch Veränderungen auf dieser Spur. Hände, Schatten neben
  der Strecke und das Auto auf der anderen Spur werden ignoriert.
- **Fahrspur einzeichnen (`t`)**, **Screenshot (`s`)**, **Positionen als CSV loggen (`--csv datei.csv`)**.
