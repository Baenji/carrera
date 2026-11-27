# Carrera RL

Ein RL-Agent fährt ein Auto auf einer echten Carrera-GO-Bahn. Eine Webcam filmt die Strecke von oben,
ein Arduino stellt die Bahnspannung ein. Trainiert wird in einer eigenen Simulation (Gymnasium und
Stable-Baselines3).

## Ordner

| Ordner | Inhalt |
|---|---|
| `src/` | Gesamtsystem: Wahrnehmung, Steuerung, Arduino |
| `sim/` | Simulation, Training und Auswertung der Modelle, siehe `sim/readme.md` |
| `experiments/` | Eigenständige Experimente, jedes mit eigener README |
| `archiv/` | Code des Vorjahresteams, wird nicht weiterentwickelt |

## Installation

Gebraucht wird Python 3.11. Alle Pakete stehen in `requirements.txt`, die Datei gilt für Windows,
macOS und Linux. Pakete, die nur ein Betriebssystem braucht, installiert pip dort automatisch mit.

Mit venv, aus dem Hauptordner des Repos:

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Oder mit conda:

```bash
conda create -n carrera python=3.11
conda activate carrera
pip install -r requirements.txt
```

Wer ein neues Paket braucht, trägt es mit Version in `requirements.txt` ein, damit alle denselben
Stand haben.

## Besonderheiten je Betriebssystem

### macOS

Die Kamera wird über PyAV gelesen, weil OpenCV auf dem Mac höchstens 30 fps liefert. PyAV kommt mit
`requirements.txt`.

Belichtung, Weißabgleich und Fokus setzt das Kommandozeilen-Tool
[uvc-util](https://github.com/jtfrey/uvc-util). Ohne es läuft alles, aber die Kamera bleibt auf
Automatik. Die Farbwerte für den blauen Punkt sind für eine feste Belichtung eingestellt, das Auto wird
dann womöglich schlecht erkannt. Einmalig mit aktivem Environment bauen:

```bash
git clone --depth 1 https://github.com/jtfrey/uvc-util.git /tmp/uvc-util
cd /tmp/uvc-util/src && gcc -o "$VIRTUAL_ENV/bin/uvc-util" -framework IOKit -framework Foundation \
    uvc-util.m UVCController.m UVCType.m UVCValue.m      # bei conda: "$CONDA_PREFIX/bin/uvc-util"
uvc-util -d                                              # sollte die Brio anzeigen
```

Danach steht das Terminal in `/tmp/uvc-util/src`. Der Ordner heißt ebenfalls `src`, ist aber der
falsche. Zurück ins Repo wechseln, siehe [Starten](#starten).

Auf Macs mit Intel-Prozessor lassen sich nicht alle Pakete installieren.

### Windows

Die Kamera läuft über DirectShow. Die Brio wird über ihren Namen gefunden, dafür ist `pygrabber` da
(kommt mit `requirements.txt`).

Arduino-Nachbauten mit CH340-Chip brauchen eventuell einen eigenen USB-Treiber, sonst taucht kein
COM-Port auf.

### Linux

Die Kamera läuft über V4L2, die Brio wird unter `/dev/v4l/by-id` gefunden.

Für den Zugriff auf den Arduino muss der eigene Benutzer in der Gruppe `dialout` sein (danach einmal
ab- und wieder anmelden):

```bash
sudo usermod -aG dialout $USER
```

## Aufbau

- Logitech Brio fest über der Strecke montiert. Wird sie bewegt, muss die Strecke neu eingerichtet werden.
- AprilTags (tag36h11) auf allen Streckenteilen, nach den Klebe-Regeln in
  `experiments/track_detection/README.md`.
- Blauer Punkt auf dem Auto.
- Das Auto fährt auf der Spur, die in `src/config.py` steht (zurzeit `"rechts"` in Fahrtrichtung).

## Starten

Die Module importieren sich gegenseitig (`import config`, `from perception import ...`). Das klappt
nur, wenn man im Ordner `src/` des Repos steht. Kamera und Arduino müssen angeschlossen sein:

```bash
cd <Pfad zum Repo>/src
pwd                  # muss auf .../carrera/src enden
python main.py       # Menü: Strecke einrichten, fahren, beenden
```

Training und Auswertung der Modelle sind in `sim/readme.md` beschrieben.

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

## Einstellungen

Alles, was pro Aufbau angepasst wird, steht in `src/config.py`: Spur, Kamera und Auflösung, Kamerahöhe
für die Parallaxe-Korrektur und der Farbbereich des blauen Punkts. Nach einer Änderung von Spur oder
Auflösung die Strecke neu einrichten.

## Häufige Fehler

| Meldung | Ursache und Lösung |
|---|---|
| `No module named 'perception'` | Falscher Ordner. Mit `pwd` prüfen, in `src/` des Repos wechseln. |
| `Noch keine Strecke eingerichtet.` | Erst `python -m perception.perception --einrichten`. |
| `Die Strecke wurde für Spur ... eingerichtet` | In `config.py` steht eine andere Spur als beim Einrichten. Strecke neu einrichten. |
| `uvc-util nicht gefunden` | uvc-util bauen (siehe macOS), sonst bleibt die Kamera auf Automatik. |
| `kein Anschluss gefunden ... Fehlt dort ein Tag?` | Ein Tag ist verdeckt oder zu klein im Bild. Auto und Hände weg, mehr Licht. Erscheint auch `px pro Tag-Zelle`, reicht die Auflösung nicht. |
| `Runde nicht innerhalb von 60 s geschlossen.` | Das Auto wurde unterwegs nicht erkannt oder war zu langsam. Einrichten neu starten. |
| Kamera lässt sich nicht öffnen | Es darf nur ein Programm die Kamera benutzen. Andere Tracking-Skripte und Kamera-Apps schließen. |
