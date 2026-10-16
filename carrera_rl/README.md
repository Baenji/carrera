# carrera_rl – Messkette für die Simulation

Ziel: Die Simulation soll sich wie das echte Auto verhalten. Statt von Hand mit
Stoppuhr zu messen, fährt ein Skript automatisch Gas-Muster auf der echten Bahn,
die Kamera zeichnet auf, und die Modellparameter werden daraus berechnet.

```
Kamera kalibrieren  →  Messfahrten aufnehmen  →  Parameter anpassen  →  (Simulation / Training)
camera_calib.py        record.py                 sysid.py
```

## Einrichtung

```bash
pip install -r carrera_rl/requirements.txt
```

Alle Befehle werden aus dem Hauptordner des Repos ausgeführt.

**Arduino:** Die neue Firmware [`firmware/carrera_pwm_fast`](firmware/carrera_pwm_fast/carrera_pwm_fast.ino)
in der Arduino IDE aufspielen (gleiche Verdrahtung wie bisher). Die alte Firmware schickt
pro Befehl ~120 Zeichen Text mit 9600 Baud zurück und verzögert dadurch jedes Signal um
über 0,1 s. Die neue läuft mit 115200 Baud ohne Textausgabe und stoppt das Auto, wenn
0,5 s lang kein Befehl kommt.
⚠️ Das alte Programm (`quick_object_tracking.py`) sendet keine Wiederholungen und läuft
deshalb nicht mit der neuen Firmware. Für das alte Programm die alte Firmware verwenden.

## Ablauf

### 1. Kamera kalibrieren (einmal pro Kameraposition)

Kamera fest montieren, Auto von der Strecke nehmen, dann:

```bash
python -m carrera_rl.camera_calib --camera --out calibration/camera.json
```

Danach unbedingt `calibration/camera_overlay.png` ansehen: Die grüne Linie (gefahrene Spur)
und die magentafarbene (andere Spur) müssen auf den Schlitzen liegen. Der rote Punkt `s=0`
markiert den Anfang der Start/Ziel-Geraden. Wird die Kamera bewegt, neu kalibrieren.

### 2. Messfahrten aufnehmen

Das Auto braucht eine **grüne Markierung** (Farberkennung aus `src/config.py`).

```bash
# a) Gas langsam steigern bis zum Abflug -> Endgeschwindigkeiten + Abfluggrenze
python -m carrera_rl.record --program probe

# b) Sprünge zwischen Gasstufen -> Beschleunigen / Bremsen
python -m carrera_rl.record --program steps --max-throttle 45

# c) zufälliges Umschalten -> Verzögerung
python -m carrera_rl.record --program prbs --max-throttle 45
```

`--max-throttle` bei b) und c) etwa 5–10 Punkte unter dem Abflugwert aus a) wählen.
Nach einem Abflug fragt das Skript, ob das Auto wieder eingesetzt ist (Enter).
Abbrechen mit Strg+C, das Gas geht dann auf 0. Mit `--show` wird das Kamerabild angezeigt.

Jede Fahrt landet in `data/runs/<datum>_<programm>/` (frames.csv, commands.csv, events.csv, meta.json).

### 3. Parameter anpassen

```bash
python -m carrera_rl.sysid data/runs/<probe> data/runs/<steps> data/runs/<prbs> --out calibration/vehicle.json --plot
```

Ergebnis ist `calibration/vehicle.json` mit diesen Parametern:

| Parameter | Bedeutung |
|---|---|
| `v_max` | Endgeschwindigkeit bei 100 % Gas (mm/s) |
| `u0` | Totzone: darunter fährt das Auto nicht (%) |
| `gamma` | Form der Kennlinie Gas → Geschwindigkeit (1 = linear) |
| `tau_up`, `tau_down` | wie schnell das Auto beschleunigt / abbremst (s) |
| `curve_drag` | zusätzliches Abbremsen in Kurven |
| `delay` | Gesamtverzögerung Kamera → PC → Arduino → Motor (s) |
| `a_lat_max` | Querbeschleunigung, ab der das Auto abfliegt (mm/s²) |

`--plot` speichert einen Vergleich Messung/Simulation. Der Restfehler (RMS) sollte im
Bereich weniger Millimeter liegen.

## Ohne Hardware ausprobieren

```bash
python -m carrera_rl.fake_run --out data/fake_run
python -m carrera_rl.sysid data/fake_run --out data/fake_fit/vehicle.json
```

`fake_run` simuliert ein Auto mit bekannten Parametern (inkl. Kamerarauschen, Aussetzern
und Abflügen). `sysid` sollte diese Parameter zurückgewinnen. Tests: `pytest carrera_rl/tests`.

## Dateien

| Datei | Inhalt |
|---|---|
| `track.py` | Streckengeometrie: Layout, Spurlinie, Krümmung, Projektion Punkt → s |
| `vehicle.py` | 1D-Fahrzeugmodell und Simulation |
| `camera_calib.py` | Kamerapixel → Position auf der Spur (über AprilTags + Schienen) |
| `record.py` | automatische Messfahrten auf der echten Bahn |
| `sysid.py` | Parameteranpassung aus Messfahrten |
| `fake_run.py` | künstliche Messfahrten zum Testen |

## Streckendaten

Gemessen aus einem entzerrten Foto (±3 mm): lange Gerade 342 mm, kurze Gerade und
Startgerade je 114 mm, 90°-Kurven mit Spurradius 142,5 mm (innen) bzw. 199,5 mm (außen),
Spurabstand 57 mm. Rundenlänge: rechte Spur (innen in den 6 Rechtskurven) 4,25 m,
linke Spur 4,61 m. Wird die Strecke umgebaut, `LAYOUT` in `track.py` anpassen.

## Bekannte Grenzen

- `record.py` ist noch nicht an der echten Bahn getestet.
- Die Farbmarkierung sitzt auf dem Dach (~3 cm über der Bahn). Je nach Kamerawinkel
  entsteht dadurch ein kleiner, ortsabhängiger Versatz von wenigen Millimetern.
- Linsenverzeichnung (Weitwinkel) wird nicht herausgerechnet. Liegen die Linien im
  Overlay am Bildrand daneben, muss das ergänzt werden.
