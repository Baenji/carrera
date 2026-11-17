# Altprojekt (Vorjahresteam): Setup und Start

Dieser Ordner enthält den Code des Vorjahresteams. Die Anleitung beschreibt, wie man ihn wieder zum Laufen bringt. Die frühere englische README ist teilweise veraltet und liegt noch in der Git-History.

Alle Befehle werden **aus `archiv/` heraus** ausgeführt, außer es steht etwas anderes dabei.

## 1. Voraussetzungen

| Was | Wofür |
|---|---|
| Python 3.11 | Tracking-App und RL-Training |
| Godot 4.5 (`godot` muss im PATH liegen) | Simulator in `CarreraSimulator/` |
| USB-Webcam über der Bahn | nur für den Betrieb mit der echten Bahn |
| Arduino mit Firmware | nur zum Fahren auf der echten Bahn |

Unter macOS liegt Godot meist nicht im PATH. Abhilfe:

```bash
alias godot="/Applications/Godot.app/Contents/MacOS/Godot"
```

## 2. Python-Umgebung

```bash
cd <repo-root>
python3.11 -m venv .venv          # falls .venv noch nicht existiert
source .venv/bin/activate
pip install -e archiv
pip install pyyaml                # braucht der Launcher, fehlt in requirements.txt
pip install --no-deps "numpy==2.2.6"   # Modelle wurden mit NumPy 2 gespeichert, sonst: No module named 'numpy._core.numeric'

cd archiv
python -c "from src.config import TAG_MAP; print('ok')"
```

Zu den Versionen: godot-rl 0.8.2 erlaubt nur `stable-baselines3<=2.4.0`, und SB3 2.4.0 verlangt `numpy<2`. Die Modelle in `models/` lassen sich aber nur mit NumPy 2 laden. SB3 2.4.0 zusammen mit NumPy 2.2.6 funktioniert trotzdem. Die Warnung von `pip check` kann man ignorieren.

**Welches Modell?** Der aktuelle Godot-Code liefert 3 Beobachtungswerte. Dazu passen nur `simmodel_better8` bis `simmodel_better11`. `rlmodel_good` und `simmodel_good` stammen von einer älteren Version mit 6 Werten und brechen mit `Observation spaces do not match` ab.

Wurde `.venv` vor dem Verschieben nach `archiv/` mit `pip install -e .` eingerichtet, muss `pip install -e archiv` noch einmal laufen, sonst zeigt der editierbare Install auf den alten Pfad.

## 3. Godot-Projekt einmalig importieren

Der Import-Cache `CarreraSimulator/.godot/` ist nicht im Repo. Ohne ihn bricht `godot --path CarreraSimulator` mit `Unrecognized UID: "uid://b3axd7spkulbx"` ab. Einmalig (oder nach frischem Clone) ausführen:

```bash
godot --headless --path CarreraSimulator --import
```

Warnungen wie `invalid UID ... using text path instead` und ein `Pure virtual function called!` beim Beenden sind harmlos. Alternativ das Projekt einmal im Godot-Editor öffnen.

## 4. Konfiguration prüfen

In `src/config.py`:

- `CAM_INDEX = 1` ist die Nummer der Webcam. Am Laptop ist `0` meist die eingebaute Kamera, die externe hat dann `1`.
- `GREEN_*` und `YELLOW_*` sind die HSV-Schwellen für das Auto und die gelben Referenzpunkte. Bei anderem Licht müssen sie nachjustiert werden.
- `SIMULATION_PORT = 11360` ist der TCP-Port von Godot.

Unter macOS muss das Terminal Zugriff auf die Kamera haben (Systemeinstellungen → Datenschutz & Sicherheit → Kamera).

Den Arduino findet `Network` automatisch (`usbmodem`/`COM`-Port, 9600 Baud). Ohne Arduino läuft die App einfach ohne ihn weiter.

## 5. Die drei Prozesse

| # | Prozess | Rolle | Verbindung |
|---|---|---|---|
| A | SB3-Trainingsskript | PPO-Agent | TCP-Server, wartet auf Godot |
| B | Godot-Simulator | Umgebung bzw. Relais | Client zu A, Server auf Port 11360 für C |
| C | Tracking-App | Kamera, Streckenerkennung, Arduino | Client zu B |

**Die Startreihenfolge ist wichtig: A → B → C.** Godot versucht beim Start genau einmal, A zu erreichen. Klappt das nicht, beendet es sich mit `server disconnected status, closing` und `SCRIPT ERROR: ... _handshake (sync.gd:360)`. Terminal A erst starten und warten, bis `waiting for remote GODOT connection on port 11008` erscheint. Die Tracking-App verbindet sich ebenfalls nur einmal mit Godot und versucht es danach nicht erneut.

Jeder Prozess läuft in einem eigenen Terminal, in dem vorher `source ../.venv/bin/activate` ausgeführt und nach `archiv/` gewechselt wurde.

### Szenario 1: Echte Bahn, Modell fährt (3 Terminals)

> ⚠️ **Vorher patchen:** In `CarreraSimulator/Singletons/network_manager.gd` steht `var SIMULATION_MODE: bool = true`, und ohne `--sim` setzt nichts den Wert auf `false`. Godot ignoriert dann Fortschritt und Crash-Meldungen von der Kamera. Für den Betrieb an der echten Bahn den Default auf `false` setzen.

```bash
# Terminal A: Agent (wartet, bis Godot sich verbindet)
python CarreraSimulator/stable_baselines3_example.py \
    --resume_model_path=models/simmodel_better11.zip --inference
#   Weitertrainieren statt nur fahren:
#   --resume_model_path=models/simmodel_better11.zip --save_model_path=models/rlmodel.zip --timesteps=1_000

# Terminal B: Godot (ohne --sim, also RL-Modus)
godot --path CarreraSimulator

# Terminal C: Tracking-App
python quick_object_tracking.py
```

Danach:

1. Das Auto aufs Gleis stellen. Es sollte vorher stehen, denn die Spannung kommt sofort vom Modell.
2. Im Kamerafenster warten, bis die AprilTags stabil erkannt werden (`STABLE_TAG_FRAMES`). Die App schickt dann die Streckenreihenfolge an Godot, und Godot baut die Strecke.
3. **Achtung:** `track_mapper.py` sendet derzeit eine fest codierte Testreihenfolge statt der erkannten (`TODO: REMOVE HARDCODED TESTING VALUES`).
4. Taste **G** schaltet den Track-Graph ein bzw. aus. Den Fortschritt sendet die App nur, solange der Graph sichtbar ist. **ESC** beendet die App.

### Szenario 2: Training rein in der Simulation (2 Terminals, keine Kamera)

```bash
# Terminal A
python CarreraSimulator/stable_baselines3_example.py \
    --timesteps=30_000 --save_model_path=models/simmodel.zip

# Terminal B: --skip_start_screen nimmt eine fest codierte Strecke, ohne auf die Kamera zu warten
godot --sim --skip_start_screen --path CarreraSimulator
```

Mit `--sim` statt `--skip_start_screen` wartet Godot auf eine Streckenreihenfolge von der Tracking-App (dann zusätzlich Terminal C, wie in Szenario 1). Alles andere von der Kamera wird ignoriert.

Schneller trainieren geht mit einem exportierten Godot-Binary. Damit startet das Skript Godot selbst und braucht nur ein Terminal:

```bash
python CarreraSimulator/stable_baselines3_example.py --env_path=<export-binary> \
    --n_parallel=8 --speedup=32 --timesteps=500_000 --save_model_path=models/simmodel.zip
```

Ein Export liegt nicht im Repo. Er wird in Godot über Projekt → Exportieren erzeugt.

### Optional: TensorBoard (weiteres Terminal)

```bash
tensorboard --logdir=logs
```

## 6. Launcher (Alternative zu mehreren Terminals)

`launcher/launcher.py` startet die Prozesse eines Profils aus `launcher/config.yaml` nacheinander mit `cwd = archiv/`. Ctrl+C beendet alle.

```bash
python launcher/launcher.py --list
python launcher/launcher.py flex2      # Godot + Tracking
```

Einschränkungen:

- Der Launcher startet Godot **vor** dem SB3-Skript. Läuft das Skript noch nicht, beendet sich Godot (siehe oben). Für die Profile mit Training ist es daher sicherer, die Prozesse von Hand zu starten.
- Die Modellpfade in `config.yaml` zeigen auf den Repo-Root statt auf `models/`.
- `sb-full-train` erwartet `CarreraSimulator/export/CarreraSim.exe` (Windows, nicht im Repo).
- Das Profil `sim-retraining` verweist auf eine Komponente, die es nicht gibt, und bricht ab.

## 7. Arduino testen

```bash
python src/hardware/arduino/Arduino.py
```

**Das Auto fährt dabei kurz mit 50 %!** Vorher sicher aufs Gleis stellen. Firmware gibt es in zwei Varianten: `arduino_geschwindigkeit_skaliert/scaled_pwm_controller/` (PWM auf Pin 11, Befehle `<0-100>\n` und `STATUS\n`) und `arduino_geschwindigkeit_skaliert/arduino_geschwindigkeit_skaliert.ino` (Digitalpoti MCP4151). Welche davon verbaut ist, ist noch nicht geklärt.

## 8. Bekannte Probleme

Die vollständige Liste steht in `.claude/CLAUDE.md` und in Notion (Wiki → „Bekannte Probleme“). Für den Betrieb am wichtigsten:

- Die Beobachtung des Agenten ist praktisch leer (`discrete_progress_ratio` ist immer 0). Die mitgelieferten Modelle sind deshalb wenig aussagekräftig.
- `TrackBuilder.gd` baut Start/Ziel sowie kurze und mittlere Geraden nicht.
- Die Crash-Erkennung prüft effektiv nur die Geschwindigkeit.
