# Perception und State starten (src/)

Stand: 27.11.2026, Branch `state.py` (Commit 384d562). Getestet auf macOS mit der Logitech Brio.
Wenn sich `src/` seitdem stark verändert hat, kann diese Anleitung veraltet sein. Im Zweifel mit
`git log -- src/` nachsehen, was sich geändert hat.

Was hier läuft: Die Kamera erkennt die Strecke an den AprilTags und das Auto am blauen Punkt.
Daraus entstehen die Position in mm und die Geschwindigkeit (`perception/`) und daraus der State
für den Agenten (`state.py`). Das Training der Simulation ist davon getrennt, siehe `sim/readme.md`.

## Voraussetzungen

Aufbau:

- Logitech Brio fest über der Strecke montiert. Wird sie bewegt, muss die Strecke neu eingerichtet werden.
- AprilTags (tag36h11) auf allen Streckenteilen, nach den Klebe-Regeln in
  `experiments/track_detection/README.md`.
- Blauer Punkt auf dem Auto.
- Das Auto fährt auf der Spur, die in `config.py` steht (zurzeit `"rechts"` in Fahrtrichtung).

Software, einmalig im Environment `carrera` (Python 3.11):

```bash
conda create -n carrera python=3.11     # nur, wenn es das Environment noch nicht gibt
conda activate carrera
pip install opencv-python numpy pupil-apriltags
```

Zusätzlich je nach Betriebssystem:

| System | Was noch nötig ist |
|---|---|
| macOS | `pip install av` und das Tool uvc-util (siehe unten) |
| Windows | optional `pip install pygrabber`, damit die Brio automatisch gefunden wird |
| Linux | nichts, die Brio wird über `/dev/v4l/by-id` gefunden |

uvc-util unter macOS bauen (einmalig, mit aktivem Environment). Ohne uvc-util bleibt die Kamera auf
Belichtungsautomatik, die Farbwerte für den blauen Punkt sind aber für eine feste Belichtung
eingestellt. Das Auto wird dann womöglich schlecht erkannt.

```bash
git clone --depth 1 https://github.com/jtfrey/uvc-util.git /tmp/uvc-util
cd /tmp/uvc-util/src && gcc -o "$CONDA_PREFIX/bin/uvc-util" -framework IOKit -framework Foundation \
    uvc-util.m UVCController.m UVCType.m UVCValue.m
uvc-util -d                               # sollte die Brio anzeigen
```

Danach unbedingt zurück ins Repo wechseln, siehe nächster Abschnitt.

## Alle Befehle aus src/ starten

Die Module importieren sich gegenseitig (`import config`, `from perception import ...`). Das
klappt nur, wenn man im Ordner `src/` des Repos steht:

```bash
cd <Pfad zum Repo>/src
pwd                                       # muss auf .../carrera/src enden
```

Vorsicht: Nach dem Bau von uvc-util steht das Terminal in `/tmp/uvc-util/src`. Der Ordner heißt
ebenfalls `src`, ist aber der falsche.

## Strecke einrichten

Einmal pro Aufbau. Erneut nötig, wenn die Kamera bewegt, die Strecke umgebaut oder in `config.py`
die Spur oder die Auflösung geändert wurde.

```bash
python -m perception.perception --einrichten
```

1. Das Auto steht auf der Spur aus `config.py` und verdeckt kein Tag, keine Hände im Bild. Die Tags
   werden erkannt, ausgegeben werden `tag_list` und Spurlänge (aktuelle Strecke, Spur rechts: etwa 4269 mm).
2. Bei "Auto jetzt langsam eine Runde fahren lassen" mit dem Handregler eine langsame, gleichmäßige
   Runde fahren, höchstens 60 s. Ist das Auto wieder an der Stelle, an der es zuerst erkannt wurde,
   schließt sich die Runde von selbst.
3. Die Strecke wird in `perception/track_map.json` gespeichert. Die Datei hängt vom Kameraaufbau ab
   und ist deshalb nicht im Git.
4. Danach zeigt das Skript laufend Position und Geschwindigkeit. Mit `Ctrl+C` beenden.

## Messen

Mit eingerichteter Strecke, das Auto mit dem Handregler fahren:

```bash
python -m perception.perception           # Position in mm und Geschwindigkeit
python -m state                           # State: Kurvenrest, nächste Kurve, Geschwindigkeit (je 0 bis 1)
```

Beides mit `Ctrl+C` beenden. So sieht man, ob der State plausibel ist:

- Auf der Geraden nach dem Start ist der Kurvenrest 0, "nächste Kurve" fällt bis zur Kurveneinfahrt auf 0.
- In der ersten von zwei R-Kurven hintereinander sind Kurvenrest und nächste Kurve gleich.
- Kurz vor den drei langen Geraden steht "nächste Kurve" auf 1,00. Das ist richtig, die Distanz liegt
  dort über der Normierungsgrenze von 1200 mm.

## Häufige Fehler

| Meldung | Ursache und Lösung |
|---|---|
| `No module named 'perception'` | Falscher Ordner. Mit `pwd` prüfen, in `src/` des Repos wechseln. |
| `Noch keine Strecke eingerichtet.` | Erst `python -m perception.perception --einrichten`. |
| `Die Strecke wurde für Spur ... eingerichtet` | In `config.py` steht eine andere Spur als beim Einrichten. Strecke neu einrichten. |
| `uvc-util nicht gefunden` | uvc-util bauen (siehe oben), sonst bleibt die Kamera auf Automatik. |
| `kein Anschluss gefunden ... Fehlt dort ein Tag?` | Ein Tag ist verdeckt oder zu klein im Bild. Auto und Hände weg, mehr Licht. Erscheint auch `px pro Tag-Zelle`, reicht die Auflösung nicht. |
| `Runde nicht innerhalb von 60 s geschlossen.` | Das Auto wurde unterwegs nicht erkannt oder war zu langsam. Einrichten neu starten. |
| Kamera lässt sich nicht öffnen | Es darf nur ein Programm die Kamera benutzen. Andere Tracking-Skripte und Kamera-Apps schließen. |

## Einstellungen

Alles, was pro Aufbau angepasst wird, steht in `config.py`: Spur, Kamera und Auflösung, Kamerahöhe für
die Parallaxe-Korrektur und der Farbbereich des blauen Punkts. Nach einer Änderung von Spur oder
Auflösung die Strecke neu einrichten.
