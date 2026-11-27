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
Automatik. Einmalig mit aktivem Environment bauen:

```bash
git clone --depth 1 https://github.com/jtfrey/uvc-util.git /tmp/uvc-util
cd /tmp/uvc-util/src && gcc -o "$VIRTUAL_ENV/bin/uvc-util" -framework IOKit -framework Foundation \
    uvc-util.m UVCController.m UVCType.m UVCValue.m      # bei conda: "$CONDA_PREFIX/bin/uvc-util"
uvc-util -d                                              # sollte die Brio anzeigen
```

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

## Starten

Das Gesamtsystem wird aus dem Ordner `src/` gestartet, Kamera und Arduino müssen angeschlossen sein:

```bash
cd src
python main.py       # Menü: Strecke einrichten, fahren, beenden
```

Was pro Aufbau angepasst wird (Spur, Kamera, Farbe des Markers), steht in `src/config.py`.

Training und Auswertung der Modelle sind in `sim/readme.md` beschrieben.
