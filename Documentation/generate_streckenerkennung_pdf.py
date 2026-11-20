#!/usr/bin/env python3
"""
Generate a human-readable, professional 3-page PDF for Carrera Track Recognition documentation.
Optimized for clarity, readability, and intuitive understanding (no cryptic LaTeX code).
"""
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable, PageBreak
)
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 44  # compact margin for better use of space
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic total page count in footers and running headers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(MARGIN, PAGE_HEIGHT - 30, "Carrera GO RL – Streckenerkennung (Projekt-Wiki)")
            self.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 30, "TH Aschaffenburg | Data Science")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(MARGIN, PAGE_HEIGHT - 34, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 34)

        # Running Footer (all pages)
        page_str = f"Seite {self._pageNumber} von {total_pages}"
        self.drawRightString(PAGE_WIDTH - MARGIN, 28, page_str)
        self.drawString(MARGIN, 28, "Autonome Slot-Car Steuerung mittels Reinforcement Learning")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(MARGIN, 38, PAGE_WIDTH - MARGIN, 38)

        self.restoreState()


def build_pdf(output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN
    )

    styles = getSampleStyleSheet()

    # Color definitions
    c_primary = colors.HexColor("#1E3A8A")   # Navy 900
    c_secondary = colors.HexColor("#2563EB") # Blue 600
    c_dark = colors.HexColor("#0F172A")      # Slate 900
    c_body = colors.HexColor("#334155")      # Slate 700
    c_muted = colors.HexColor("#64748B")     # Slate 500
    c_bg_light = colors.HexColor("#F8FAFC")  # Slate 50
    c_bg_subtle = colors.HexColor("#F1F5F9") # Slate 100
    c_border = colors.HexColor("#CBD5E1")    # Slate 300

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=c_primary,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=c_secondary,
        spaceAfter=4
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_muted,
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=c_primary,
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=c_secondary,
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        fontName='Helvetica',
        fontSize=8.3,
        leading=11.5,
        textColor=c_body,
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=body_style,
        leftIndent=10,
        firstLineIndent=-7,
        spaceAfter=2
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        fontName='Courier',
        fontSize=7.2,
        leading=9.5,
        textColor=c_dark
    )

    th_style = ParagraphStyle(
        'TH_Custom',
        fontName='Helvetica-Bold',
        fontSize=7.8,
        leading=10,
        textColor=colors.white
    )

    td_style = ParagraphStyle(
        'TD_Custom',
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_dark
    )

    td_bold = ParagraphStyle(
        'TDBold_Custom',
        parent=td_style,
        fontName='Helvetica-Bold'
    )

    callout_style = ParagraphStyle(
        'Callout_Custom',
        fontName='Helvetica',
        fontSize=7.8,
        leading=11,
        textColor=colors.HexColor("#78350F")
    )

    callout_title = ParagraphStyle(
        'CalloutTitle_Custom',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#92400E")
    )

    story = []

    # =========================================================================
    # SEITE 1: ÜBERBLICK, SYSTEMARCHITEKTUR & SENSORIK
    # =========================================================================
    header_table_data = [
        [
            Paragraph("Streckenerkennung & Rekonstruktion", title_style),
            Paragraph("<b>Projekt-Wiki Dokumentation</b><br/>Carrera GO Reinforcement Learning", ParagraphStyle('RightMeta', parent=meta_style, alignment=2))
        ],
        [
            Paragraph("Kamerabasiertes Streckenlayout, Schienenerkennung und Rundenfortschritt", subtitle_style),
            Paragraph("TH Aschaffenburg • Schwerpunkt Data Science", ParagraphStyle('RightMeta2', parent=meta_style, alignment=2))
        ]
    ]
    header_table = Table(header_table_data, colWidths=[CONTENT_WIDTH * 0.65, CONTENT_WIDTH * 0.35])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.2, color=c_primary, spaceBefore=3, spaceAfter=6))

    story.append(Paragraph("1. Systemüberblick & Funktionszweck", h1_style))
    story.append(Paragraph(
        "Die Streckenerkennung verbindet die reale Carrera GO Rennbahn mit der virtuellen Godot-Simulationsumgebung "
        "und dem Reinforcement-Learning-Agenten (Stable-Baselines3). Das System erfüllt zwei klar getrennte Kernaufgaben:",
        body_style
    ))

    task_data = [
        [
            Paragraph("<b>A. Statische Streckenrekonstruktion (Einmalig beim Systemstart)</b><br/>"
                      "Die Deckenkamera scannt die Markierungen (AprilTags) auf allen Schienenteilen. Das Python-System "
                      "ermittelt die Reihenfolge der Schienen (Start, Geraden, Kurven inkl. Links- oder Rechtskrümmung) "
                      "und sendet diese Sequenz als Liste an den Godot-Simulator. Dieser baut die virtuelle 3D-Strecke "
                      "daraufhin automatisch und modular zusammen.", body_style),
            Paragraph("<b>B. Dynamischer Rundenfortschritt (Kontinuierlich während der Fahrt)</b><br/>"
                      "Aus den Mittelpunkten der Schienenteile wird ein virtueller Streckengraph (<code>TrackGraph</code>) "
                      "erstellt. Über eine Farberkennung wird das Auto in Echtzeit lokalisiert und auf diesen Streckengraph "
                      "projiziert. So wird für jeden Zeitpunkt exakt berechnet, wie viel Prozent der Runde absolviert "
                      "wurden (0–100 %) – eine zentrale Information für den lernenden KI-Fahrer.", body_style)
        ]
    ]
    task_table = Table(task_data, colWidths=[CONTENT_WIDTH * 0.5 - 4, CONTENT_WIDTH * 0.5 - 4])
    task_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#EFF6FF")),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (0, 0), 0.7, colors.HexColor("#BFDBFE")),
        ('BOX', (1, 0), (1, 0), 0.7, c_border),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(task_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Sensorik, Beleuchtung & Marker-Setup", h1_style))
    story.append(Paragraph(
        "<b>Kamera & Beleuchtung:</b> Über der Rennbahn ist eine <i>Logitech Brio 4K</i> Webcam montiert (FHD 1080p bei 60 Bildern pro Sekunde). "
        "Um Reaktionsverzögerungen (Latenz) auszuschließen, ist der interne Kameraspeicher auf genau 1 Bild begrenzt (<code>BUFFERSIZE = 1</code>). "
        "Eine Softbox sorgt für gleichmäßiges, diffuses Licht, damit keine störenden Glanzstellen auf der schwarzen Fahrbahn entstehen.",
        body_style
    ))

    story.append(Paragraph(
        "<b>Farbreferenzpunkte (HSV-Farbraum):</b> Durch die Nutzung des HSV-Farbraums (Farbton, Sättigung, Helligkeit) bleibt "
        "die Farberkennung auch bei wechselndem Lichteinfall stabil:<br/>"
        "• <i>Gelber Orientierungspunkt:</i> Liegt statisch neben der Startlinie. Er zeigt dem System, in welche Richtung das Auto losfährt.<br/>"
        "• <i>Grüner Fahrzeugmarker:</i> Ein auffälliger grüner Aufkleber auf dem Autodach wird verfolgt; der Schwerpunkt bildet die Autoposition.",
        body_style
    ))

    story.append(Paragraph(
        "<b>AprilTags (Familie tag16h5):</b> Jedes Schienenteil besitzt einen Barcode-Aufkleber (AprilTag). "
        "Damit ein Tag als sicher erkannt gilt, muss er in mindestens <b>15 aufeinanderfolgenden Kamerabildern</b> stabil sichtbar sein "
        "(<code>STABLE_TAG_FRAMES = 15</code>). Das verhindert Messfehler und Bildflackern zuverlässig:",
        body_style
    ))

    tag_table_data = [
        [Paragraph("Tag ID", th_style), Paragraph("Schienentyp / Name", th_style), Paragraph("Simulator-Kategorie (Godot)", th_style), Paragraph("Funktion & Erkennungslogik", th_style)],
        [Paragraph("<b>1</b>", td_bold), Paragraph("Start / Ziel", td_style), Paragraph("<code>PARTS.FINISH (1)</code>", td_style), Paragraph("Fester Start- und Zielpunkt; dient als Signal zur Schleifenschließung.", td_style)],
        [Paragraph("<b>2</b>", td_bold), Paragraph("Kurze Gerade", td_style), Paragraph("<code>PARTS.SHORT_STRAIGHT (2)</code>", td_style), Paragraph("Gerades Streckenstück kurzer Baulänge.", td_style)],
        [Paragraph("<b>3</b>", td_bold), Paragraph("Mittlere Gerade", td_style), Paragraph("<code>PARTS.MEDIUM_STRAIGHT (3)</code>", td_style), Paragraph("Gerades Streckenstück mittlerer Baulänge.", td_style)],
        [Paragraph("<b>4</b>", td_bold), Paragraph("Lange Gerade", td_style), Paragraph("<code>PARTS.LONG_STRAIGHT (4)</code>", td_style), Paragraph("Standard-Vollgerade der Carrera GO Bahn.", td_style)],
        [Paragraph("<b>5</b>", td_bold), Paragraph("Kurve", td_style), Paragraph("<code>PARTS.RIGHT_CURVE (5)</code><br/><code>PARTS.LEFT_CURVE (6)</code>", td_style), Paragraph("Ob es sich um eine Links- oder Rechtskurve handelt, ermittelt das System rechnerisch aus dem Kurvenknick.", td_style)]
    ]
    tag_table = Table(tag_table_data, colWidths=[CONTENT_WIDTH * 0.10, CONTENT_WIDTH * 0.24, CONTENT_WIDTH * 0.29, CONTENT_WIDTH * 0.37])
    tag_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tag_table)

    # =========================================================================
    # SEITE 2: KERNALGORITHMEN IM DETAIL (MENSCHENLESERLICH)
    # =========================================================================
    story.append(PageBreak())

    story.append(Paragraph("3. Kernalgorithmen verständlich erklärt", h1_style))

    story.append(Paragraph("3.1 Pfadfindung: Wie wird die Schienenreihenfolge ermittelt? (<code>map_track_order</code>)", h2_style))
    story.append(Paragraph(
        "Die Kamera sieht alle AprilTags zunächst als ungeordnete Punktmenge im Raum. "
        "Um die tatsächliche Fahrtroute Schritt für Schritt aufzubauen, nutzt <code>src/tracking/track_mapper.py</code> "
        "ein anschauliches Wegsuchverfahren:",
        body_style
    ))

    pfad_steps = [
        "<b>1. Startpunkt finden:</b> Das System sucht nach dem Start/Ziel-Tag (ID 1). Der Verbindungsvektor vom Start-Tag zum benachbarten gelben Referenzpunkt gibt die erste Vorwärtsrichtung vor.",
        "<b>2. Rückwärtsfahren verbieten (Ausschlussfilter):</b> Von der aktuellen Schiene aus wird zurückgeblickt. Alle Schienen, die 'hinter' der aktuellen Schiene liegen (Abweichung größer als 90° zur Vorwärtsrichtung), werden sofort aussortiert. Dadurch kann die Route niemals rückwärts laufen oder Abkürzungen nehmen.",
        "<b>3. Nächste Schiene wählen:</b> Unter allen vor dem Auto liegenden Schienenteilen wird dasjenige gewählt, das die geringste Luftlinien-Distanz hat.",
        "<b>4. Runde schließen:</b> Der Vorgang wiederholt sich Schiene für Schiene. Sobald der Sucher wieder bei Start/Ziel (ID 1) ankommt, ist der gesamte Rundkurs geschlossen und vollständig erfasst."
    ]
    for s in pfad_steps:
        story.append(Paragraph(s, bullet_style))
    story.append(Spacer(1, 3))

    story.append(Paragraph("3.2 Kurvenrichtung: Wie erkennt das System Links- vs. Rechtskurven?", h2_style))
    story.append(Paragraph(
        "Da alle Kurventeile den identischen AprilTag (ID 5) besitzen, prüft die Funktion <code>determine_turn_direction()</code> "
        "den Krümmungsverlauf anhand von drei aufeinanderfolgenden Streckenstücken: der Schiene <b>vor</b> der Kurve, der Kurve <b>selbst</b> und der Schiene <b>nach</b> der Kurve.",
        body_style
    ))

    math_box_data = [
        [
            Paragraph(
                "<b>Das Prinzip des Drehsinns (2D-Kreuzprodukt):</b><br/>"
                "1. Man ermittelt die <b>Einfahrtsrichtung</b> (von der vorherigen Schiene zur Kurve).<br/>"
                "2. Man ermittelt die <b>Ausfahrtsrichtung</b> (von der Kurve zur nächsten Schiene).<br/>"
                "3. Der Drehwert ergibt sich durch einfaches Überkreuz-Multiplizieren der Richtungen:<br/>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<b>Drehwert = (Einfahrt.X &times; Ausfahrt.Y) &minus; (Einfahrt.Y &times; Ausfahrt.X)</b><br/><br/>"
                "<b>Ergebnis & Zuordnung:</b><br/>"
                "• <b>Drehwert &gt; +0,25:</b> &nbsp; Die Strecke knickt nach <b>rechts</b> ab &nbsp;&rarr;&nbsp; Rechtskurve (<code>PARTS.RIGHT_CURVE = 5</code>)<br/>"
                "• <b>Drehwert &lt; &minus;0,25:</b> &nbsp; Die Strecke knickt nach <b>links</b> ab &nbsp;&rarr;&nbsp; Linkskurve (<code>PARTS.LEFT_CURVE = 6</code>)<br/>"
                "• <b>Werte nahe 0:</b> &nbsp; Die Strecke verläuft im Wesentlichen geradeaus (Schwellwert filtert Messungenauigkeiten heraus).",
                body_style
            )
        ]
    ]
    math_table = Table(math_box_data, colWidths=[CONTENT_WIDTH])
    math_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_subtle),
        ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor("#94A3B8")),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(math_table)
    story.append(Spacer(1, 3))

    story.append(Paragraph("3.3 Rundenfortschritt: Wie wird die Position des Autos bestimmt? (<code>TrackGraph</code>)", h2_style))
    story.append(Paragraph(
        "In <code>src/tracking/track_graph.py</code> wird die Rennstrecke als Kette gerader Abschnitte von Schienenmittelpunkt zu Schienenmittelpunkt dargestellt. "
        "Fährt das Auto über die Bahn, bestimmt das System die exakte Rundenposition:",
        body_style
    ))

    proj_box_data = [
        [
            Paragraph(
                "<b>Schritt-für-Schritt-Ablauf:</b><br/>"
                "1. <b>Fahrzeugortung:</b> Die Kamera erkennt das grüne Autodach und liefert dessen X/Y-Bildkoordinaten.<br/>"
                "2. <b>Lot fällen (Projektion):</b> Das System prüft alle Schienensegmente und fällt das mathematische Lot vom Auto auf die Strecke. "
                "Der Streckenabschnitt mit dem kürzesten Abstand ist der Bereich, auf dem sich das Auto gerade befindet.<br/>"
                "3. <b>Teilstrecke ermitteln:</b> Auf diesem Streckenabschnitt wird berechnet, wie weit das Auto zwischen Schienenanfang (0 %) und Schienenende (100 %) fortgeschritten ist.<br/>"
                "4. <b>Gesamtfortschritt berechnen:</b><br/>"
                "&nbsp;&nbsp;&nbsp;&nbsp;<b>Rundenfortschritt (%) = (Streckenlänge bis zur aktuellen Schiene + Teilstrecke) &divide; Gesamtlänge der Bahn &times; 100</b><br/><br/>"
                "<b>Bedeutung:</b> Direkt an der Startlinie startet der Wert bei <b>0,0 %</b> und steigt kontinuierlich bis <b>100,0 %</b> bei Zieldurchfahrt. "
                "Dieser Prozentwert wird 5-mal pro Sekunde (5 Hz) an den Simulator gesendet, damit der RL-Agent immer weiß, wo auf der Strecke er sich befindet.",
                body_style
            )
        ]
    ]
    proj_table = Table(proj_box_data, colWidths=[CONTENT_WIDTH])
    proj_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_light),
        ('BOX', (0, 0), (-1, -1), 0.7, c_border),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(proj_table)
    story.append(Spacer(1, 3))

    story.append(Paragraph("3.4 Unfallerkennung (Crash-Detection) & Auto-Reset", h2_style))
    story.append(Paragraph(
        "Ergänzend zur Streckenerkennung überwacht <code>src/tracking/crash_detection.py</code> das Fahrzeug auf Abflüge. Ein Unfall wird ausgelöst, wenn "
        "(1) die Geschwindigkeit abrupt auf 0 fällt, (2) die tatsächliche Position stark vom erwarteten Streckenverlauf abweicht oder "
        "(3) die grüne Dachfläche im Kamerabild verschwindet (z. B. Überschlag). Nach einem Crash fährt <code>auto_reset.py</code> das Fahrzeug "
        "mit gedrosselter Geschwindigkeit automatisch zurück zur Startlinie.",
        body_style
    ))

    # =========================================================================
    # SEITE 3: KOMPONENTENMATRIX, PROTOKOLL & PRAXISHINWEISE
    # =========================================================================
    story.append(PageBreak())

    story.append(Paragraph("4. Komponenten- & Dateimatrix", h1_style))
    file_table_data = [
        [Paragraph("Datei / Pfad", th_style), Paragraph("Komponente / Rolle", th_style), Paragraph("Kernaufgabe & Schnittstellen", th_style)],
        [
            Paragraph("<code>src/main.py</code>", td_bold),
            Paragraph("Hauptprogramm", td_style),
            Paragraph("Steuert die Hauptschleife: Liest Kamerabilder ein, startet das Strecken-Mapping und sendet Live-Daten an Godot.", td_style)
        ],
        [
            Paragraph("<code>src/config.py</code>", td_bold),
            Paragraph("Konfigurationsdatei", td_style),
            Paragraph("Enthält alle Schwellwerte: Farbgrenzen für Grün/Gelb, Schienennamen, AprilTag-IDs und Netzwerkports.", td_style)
        ],
        [
            Paragraph("<code>src/tracking/track_mapper.py</code>", td_bold),
            Paragraph("Streckenerkenner", td_style),
            Paragraph("Führt die Pfadfindung durch (<code>map_track_order</code>), sortiert Rückwärtsschienen aus und berechnet Kurvenknicke.", td_style)
        ],
        [
            Paragraph("<code>src/tracking/track_graph.py</code>", td_bold),
            Paragraph("Streckengraph", td_style),
            Paragraph("Speichert die Geometrie der Strecke und projiziert die Autoposition zur Berechnung des Rundenfortschritts (0–100 %).", td_style)
        ],
        [
            Paragraph("<code>src/tracking/apriltag_detector.py</code>", td_bold),
            Paragraph("AprilTag-Erkennung", td_style),
            Paragraph("Liest die Barcodes auf den Schienen über die Bibliothek <code>pupil_apriltags</code> (Familie tag16h5) aus.", td_style)
        ],
        [
            Paragraph("<code>src/camera/color_detector.py</code>", td_bold),
            Paragraph("Farberkennung", td_style),
            Paragraph("Isoliert den gelben Orientierungspunkt am Start und das grüne Autodach im HSV-Farbraum.", td_style)
        ],
        [
            Paragraph("<code>src/camera/camera_manager.py</code>", td_bold),
            Paragraph("Kamera-Manager", td_style),
            Paragraph("Verbindet die Webcam betriebssystemabhängig (Windows, Mac, Linux) mit 1-Frame-Puffer zur Latenzminimierung.", td_style)
        ],
        [
            Paragraph("<code>src/network/network_client.py</code>", td_bold),
            Paragraph("Netzwerk-Client", td_style),
            Paragraph("Sendet die erkannte Streckenreihenfolge, den Rundenfortschritt und Unfallmeldungen als JSON per TCP an Godot.", td_style)
        ],
        [
            Paragraph("<code>CarreraSimulator/Trackloader/remote_trackloader.gd</code>", td_bold),
            Paragraph("Streckenlader (Godot)", td_style),
            Paragraph("Nimmt die Schienenliste in der Simulation entgegen und stößt das Zusammenbauen der 3D-Welt an.", td_style)
        ],
        [
            Paragraph("<code>CarreraSimulator/Tracks/track_builder_2/TrackBuilder.gd</code>", td_bold),
            Paragraph("Streckenbauer (Godot)", td_style),
            Paragraph("Setzt die 3D-Schienenelemente (Geraden, Links-/Rechtskurven) passgenau aneinander, um die reale Bahn nachzubilden.", td_style)
        ]
    ]
    file_table = Table(file_table_data, colWidths=[CONTENT_WIDTH * 0.35, CONTENT_WIDTH * 0.20, CONTENT_WIDTH * 0.45])
    file_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_bg_light]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(file_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Netzwerkprotokoll (Python &harr; Godot)", h1_style))
    story.append(Paragraph(
        "Die Kommunikation läuft über eine TCP-Netzwerkverbindung auf Port <code>11360</code> mit einfachen Textnachrichten im JSON-Format:",
        body_style
    ))

    protocol_data = [
        [
            Paragraph("<b>Einmalig beim Systemstart: Streckenlayout (Python &rarr; Godot)</b>", body_style),
            Paragraph("<b>Kontinuierlich während der Fahrt: Fortschritt & Unfälle</b>", body_style)
        ],
        [
            Paragraph("<code>{\"track_order\": [1, 4, 5, 5, 6, 4, 6, 5, 5, 4, 2, 5, 4, 4, 4, 5]}</code>", code_style),
            Paragraph("<code>{\"progress\": 0.428}</code> &nbsp; <i>(Rate: 5-mal pro Sekunde)</i><br/><code>{\"crash_detected\": true}</code>", code_style)
        ]
    ]
    protocol_table = Table(protocol_data, colWidths=[CONTENT_WIDTH * 0.58, CONTENT_WIDTH * 0.42])
    protocol_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_bg_subtle),
        ('BOX', (0, 0), (-1, -1), 0.7, colors.HexColor("#94A3B8")),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('PADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(protocol_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("6. Wichtige Praxishinweise, Fallstricke & Checkliste", h1_style))

    limitation_data = [
        [
            Paragraph("<b>Kritische Hinweise für Inbetriebnahme & Entwicklung:</b>", callout_title)
        ],
        [
            Paragraph(
                "• <b>Fest verdrahtete Teststrecke in <code>track_mapper.py:353</code> (WICHTIG):</b><br/>"
                "&nbsp;&nbsp;Im Quellcode überschreibt Zeile 353 die automatisch erkannte Streckenabfolge fest mit Testwerten:<br/>"
                "&nbsp;&nbsp;<code>track_order_numbers = [1, 4, 5, 5, 6, 4, 6, 5, 5, 4, 2, 5, 4, 4, 4, 5]</code><br/>"
                "&nbsp;&nbsp;Um die echte, per Kamera gescannte Strecke an den Simulator zu senden, muss diese Zeile auskommentiert werden!<br/>"
                "• <b>Beleuchtung & Glanzstellen:</b> Helles Deckenlicht erzeugt weiße Reflexionen auf den schwarzen Schienen. "
                "Unbedingt die Softbox einschalten und die Kamerabelichtung manuell fixieren (unter Windows z. B. Exposure = -6).<br/>"
                "• <b>Fehldetektionen bei Holzmaserungen:</b> Die AprilTag-Familie <code>tag16h5</code> kann bei kontrastreichen "
                "Holzböden versehentlich falsche Schienen erkennen. Ein Wechsel auf die Familie <code>tag36h11</code> bietet eine deutlich höhere Fehlertoleranz.<br/>"
                "• <b>Gelber Richtungsmarker:</b> Bei warmer Raumbeleuchtung sollten die HSV-Grenzwerte in <code>config.py</code> überprüft werden.",
                callout_style
            )
        ]
    ]
    limitation_table = Table(limitation_data, colWidths=[CONTENT_WIDTH])
    limitation_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
        ('BOX', (0, 0), (-1, -1), 0.9, colors.HexColor("#D97706")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(limitation_table)

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully built: {output_path}")

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'Documentation/streckenerkennung.pdf'
    build_pdf(out)
