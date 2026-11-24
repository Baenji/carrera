# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projektkontext

Data-Science-Schwerpunktprojekt (Betreuung: K. Radke): Eine RL-Steuerung soll ein Auto auf einer echten Carrera-GO-Bahn möglichst schnell um die Strecke bringen (Webcam von oben, Arduino regelt die Bahnspannung). Ziel ist ein Showcase für den OpenCampus, bei dem Besucher mit dem Handregler gegen das Modell fahren.

- **Phase 1 (RL-Bootcamp):** Gridworld, Q-Learning vs. SARSA. Abgeschlossen, Code liegt nicht in diesem Repo.
- **Phase 2 (Carrera):** läuft. Das Team baut **von Grund auf neu**. Ziel ist ein Agent, der auf **beliebigen Strecken** fährt (streckenrelativer State mit Vorausschau), nicht nur auf einer auswendig gelernten.
- **Leitprinzip: Lernprojekt.** Lösungen so simpel wie möglich und nur so komplex wie nötig. Keine Frameworks, Abstraktionsschichten oder Features „für später“, solange sie nicht gebraucht werden. Lieber ein kleines, verständliches Skript als eine elegante Architektur, die das Team nicht nachvollziehen kann.

## Notion

Lesen ist jederzeit erlaubt. **Schreiben (Seiten, Tasks, Kommentare) nur nach ausdrücklicher Genehmigung des Users.**

- Projektseite: https://app.notion.com/p/3f0946076ebb80c0b193ff822ef01146
- **Wiki:** https://app.notion.com/p/3fb946076ebb80eea905e5fadcfd03ff. Wichtige Seiten: Architektur, Simulation (Gymnasium-Env-Entwurf), State Repräsentation, Rewardfunktion, Crash Modellierung, Streckenerkennung, Überarbeitung Streckenerkennung (Streckenteile und Maße), Car Tracking, Bekannte Probleme (Vorprojekt).
- **Architektur:** https://app.notion.com/p/409946076ebb8056b4f5f6ab2d2ac1f6
- **Task Board:** https://app.notion.com/p/3fb946076ebb802aa5a8c68ee039aa0d

Vor Design-Vorschlägen die passende Wiki-Seite lesen. Dort stehen der aktuelle Stand und die Entscheidungen des Teams.

## Vorläufige Architektur (Stand Notion, 2026-11)

Priorisierte NFRs: 1. Fehlertoleranz, 2. Performance, 3. Benutzbarkeit. Daraus folgt:

- Kurze Erkennungsaussetzer werden geglättet, bevor sie den Agenten erreichen. „Auto nicht erkannt“ ist ein eigener Zustand und keine Position (0,0) wie im Vorprojekt.
- Der Echtzeitpfad (Kamera → State → Agent → Throttle) ist kurz und vom Frontend entkoppelt.
- Es gibt ein GUI.

Komponenten:

```
Kamera --Bild--> Wahrnehmung (Strecke + Auto erkennen, State berechnen)
       --State--> Steuerung & Agent --Throttle--> Hardware (Arduino, Bahn)
Training/Simulation (Gymnasium-Env + Stable-Baselines3) ··Modell··> Steuerung
Frontend <··Telemetrie / Befehle & Config··> Steuerung
```

Geplante Bausteine laut Wiki:

- **Simulation:** eigenes Gymnasium-Env statt Godot. Aktion ist ein kontinuierlicher Throttle in [-1, 1]. Beobachtung: Rest der aktuellen Kurve, Distanz zur nächsten Kurve, Geschwindigkeit, evtl. letzte Aktion(en). Die Episode endet bei einem Crash oder nach einer Zeitgrenze. Physikalische Konstanten (Höchstgeschwindigkeit, Abfluggeschwindigkeit in der Kurve) müssen an der echten Bahn gemessen werden.
- **Streckenerkennung:** AprilTags liefern Reihenfolge und Typ der Segmente. Die Position ergibt sich als Anteil an der Gesamtstrecke. Gemessene Teile (Set „DTM High Speed Showdown“): Start-Gerade 114 mm, lange Gerade 342 mm, mittlere Gerade 171 mm, kurze Gerade 114 mm, Kurve innen π/2 · 144 mm ≈ 226 mm.
- **Car Tracking:** Experiment mit Referenzbild-Differenz statt Farbmaske, siehe unten.

## Repo-Struktur

- `experiments/`: neue, eigenständige Experimente des Teams.
  - `car_diff_tracking/`: Auto-Tracking per Differenz zu einem Bild der leeren Strecke. `track_car.py` ist die einfache Version (Klasse `DiffTracker`), `track_car_advanced.py` lernt zusätzlich eine Spurmaske, führt das Referenzbild nach und loggt nach CSV. Bedienung steht in der README des Ordners.
- `archiv/`: kompletter Code und Doku des **Vorjahresteams** (Godot-Simulator, Tracking-App, Launcher, Arduino-Firmware, Modelle). Wird nicht weiterentwickelt und dient nur als Steinbruch und Nachschlagewerk. Weiterhin gut verwendbar sind die AprilTag-Erkennung (`archiv/src/tracking/`) und die Arduino-Schaltung bzw. -Firmware (`archiv/src/hardware/arduino/`, `archiv/arduino_geschwindigkeit_skaliert/`).
  - Doku: `archiv/Documentation/main.pdf` (Quelle `main.typ`, Typst) mit Schaltplan und Diagrammen.
  - Gemessene Rundenzeit des Vorprojekts (≈1,48 s) und Teilemaße: `archiv/CarreraSimulator/track_parts/help.txt`.
- `.claude/literature/geron_ch18_reinforcement_learning.txt`: Géron, *Hands-On ML* (2. Aufl.), Kapitel 18 „Reinforcement Learning“. Weitere Ressourcen: OpenAI Spinning Up, Hugging Face Deep RL Course, Sutton & Barto, Doku von Gymnasium und Stable-Baselines3.

## Doku-Stil

Konzept-Dokus (Beispiel: `experiments/car_diff_tracking/DOKU.md`) sind Markdown-Dateien neben dem Code, auf Deutsch. Die README daneben bleibt für Bedienung und Installation.

- Konzepte und Entscheidungen erklären („warum so“), kaum Code.
- Viel visualisieren: Mermaid-Diagramme direkt im Markdown, dazu Screenshots aus dem echten System.
- Den Weg zur Lösung nur kurz zeigen (Diagramm von links nach rechts, pro Schritt Idee ⇒ Problem). Ausführlich wird nur das Endprodukt erklärt.
- Ein Übersichtsdiagramm des Endprodukts, die Abschnittsüberschriften entsprechen seinen Kästen. Keine Schrittnummern im Diagramm und im Text.
- Nichts doppelt darstellen, z. B. keine Kurzfassung, die ein Diagramm weiter unten wiederholt.
- Nur das eigene Thema. Wo die Komponente in der Gesamtarchitektur sitzt, gehört in eine Doku eine Ebene höher.
- Prinzipien vor konkreten Zahlen. Werte nur, wo sie zum Verständnis nötig sind, die Standardwerte gesammelt in einer Tabelle.
- Schlichter Text: keine Emojis, kein Fettdruck, keine Gedankenstriche (vorher den humanizer-Skill drüberlaufen lassen).
- Diagrammfarben kontrastreich wählen, sie müssen im hellen und im dunklen Modus lesbar sein.

## Setup

Es gibt keine Tests, keinen Linter und noch keine gemeinsame `requirements.txt` für den Neubau.

```bash
source .venv/bin/activate      # Python 3.11 (lokal; im Team wird teils conda-Env "carrera" genutzt)
python experiments/car_diff_tracking/track_car.py   # Tracking-Experiment, braucht OpenCV + NumPy und eine Kamera
```

## Lehren aus dem Vorprojekt

Bekannte Fehler im Code unter `archiv/`. Die vollständige Liste steht im Wiki unter „Bekannte Probleme“ und „Car Tracking“. Beim Übernehmen von Teilen nicht wiederholen:

- Die Beobachtung war praktisch leer (`discrete_progress_ratio` immer 0, `is_out` im selben Frame zurückgesetzt). Der Agent sah nur die Geschwindigkeit und fuhr „blind“. Die Modelle in `archiv/models/` sind deshalb wenig aussagekräftig.
- Wurde das Auto nicht gefunden, floss `(0, 0)` bzw. die letzte Position als echte Messung in den Fortschritt ein.
- Die Crash-Erkennung prüfte effektiv nur die Geschwindigkeit.
- `track_mapper.py` überschrieb die erkannte Strecke mit einer fest codierten Testliste. `TrackBuilder.gd` baute Start/Ziel und kurze Geraden nie.
- Der Fortschritt wurde auf einem Polygon durch die AprilTag-Mittelpunkte berechnet statt auf der echten Streckengeometrie.
- Arduino: Es gibt zwei Firmware-Varianten, PWM (`scaled_pwm_controller/`, Pin 11, 9600 Baud, Befehle `<0-100>\n` und `STATUS\n`) und Digitalpoti MCP4151 über SPI (`arduino_geschwindigkeit_skaliert.ino`). Welche real verbaut ist, ist noch offen.
