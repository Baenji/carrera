# Auto-Tracking per Hintergrund-Differenz

Experiment: Das Auto wird ohne Farbmarkierung erkannt. Stattdessen wird jedes Kamerabild mit einem
Bild der leeren Strecke verglichen. Die größte Region mit Unterschieden gilt als Auto.
Unabhängig vom alten Code in `src/tracking/`.

## Starten

```bash
conda activate carrera
python experiments/car_diff_tracking/track_car.py              # Brio wird automatisch gefunden
python experiments/car_diff_tracking/track_car.py --csv pos.csv  # Positionen mitloggen
```

1. Kein Auto auf der Strecke, keine Hand im Bild → **`b`** drücken (Hintergrund = Mittel aus 30 Frames)
2. Auto aufsetzen, **`l`** drücken und 2 Runden von Hand fahren → Spurmaske wird gelernt und als
   `track_mask.png` gespeichert (wird beim nächsten Start automatisch geladen)
3. Fahren → roter Punkt = erkannter Schwerpunkt, gelb = Kontur, lila = Spur, grün = Spurmaske

Tasten: `b` Hintergrund neu · `l` Spurmaske lernen · `k` Spurmaske zeigen · `x` Spurmaske verwerfen ·
`m` Differenzmaske · `t` Spur · `u` Hintergrund langsam nachführen · `+`/`-` Schwellwert · `s` Screenshot · `q` Ende

## Spurmaske (Lernmodus)

- Während des Lernens wird jede erkannte Auto-Silhouette aufsummiert. Pixel, die mindestens
  `--min-hits` mal bedeckt waren, ergeben die Maske. Danach Lücken schließen, nur die größte Fläche
  behalten und `--margin` px Rand zugeben.
- Runde = Auto kommt nach genügend zurückgelegter Strecke wieder in die Nähe des Startpunkts.
- Die Maske deckt nur die gefahrene Spur ab. Ein zweites Auto auf der anderen Spur stört deshalb nicht.
- Beim Tracking wird das Differenzbild **nicht** beschnitten. Eine Region zählt nur, wenn
  ≥ `--min-overlap` (70 %) davon auf der Maske liegen. Schatten und Hände neben der Strecke fallen raus,
  der Punkt verrutscht nicht, wenn das Auto über den Rand ragt.
- Kamera verschoben → Maske passt nicht mehr → neu lernen (`l`).

## Pipeline

1. Belichtung, Weißabgleich und Fokus der Kamera einschwingen lassen und dann **sperren**.
   Sonst regelt die Kamera nach, wenn das Auto ins Bild fährt, und das ganze Bild weicht vom Hintergrund ab.
2. Frame auf 50 % verkleinern + Gauß-Blur (gegen Rauschen und JPEG-Artefakte)
3. `absdiff` zum Hintergrund, Maximum über die BGR-Kanäle, Schwellwert
4. Morphologie: Opening (Rauschen weg), Closing (Löcher im Auto schließen)
5. Größte Kontur ≥ `--min-area` (mit Spurmaske: nur Konturen mit ≥ 70 % auf der Maske) → Schwerpunkt über Momente

Rechenzeit ca. 1–2 ms pro Frame (1280×720), die Kamera liefert 60 fps.

## Bekannte Schwachstellen / Stellschrauben

- **Licht ändert sich** (Sonne, Deckenlicht) → mit `u` nachführen oder `b` neu aufnehmen
- **Hand berührt das Auto** → beide verschmelzen zu einer Region mit wenig Anteil auf der Spur → kurz keine Erkennung
- **Beide Autos nebeneinander** → können zu einer Region verschmelzen → kurz keine Erkennung
- **Während des Lernens** sollte nichts anderes ins Bild greifen (dort gilt noch die größte Region)
- **50-Hz-Flackern** von Leuchtstoffröhren/LEDs kann Streifen erzeugen → `--exposure 100` (10 ms) bzw. `200` testen
- **Kamera wird angestoßen** → Hintergrund passt nicht mehr, `b` drücken
- **Auto steht länger still** und `u` ist an → wird nicht eingelernt (Bereich wird ausgespart), Lichtdrift dort aber auch nicht
- Schwellwert: zu niedrig = Rauschen/Schatten, zu hoch = dunkle Autoteile auf dunklem Asphalt fehlen
