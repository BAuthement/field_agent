"""Donor report PDF generation with ReportLab."""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle, HRFlowable)

ACCENT = colors.HexColor("#1b5e20")
GOLD = colors.HexColor("#b8860b")
LIGHT = colors.HexColor("#f1f8e9")

TYPE_LABELS = {
    "en": {"gospel_conversation": "Gospel conversations", "discipleship_meeting": "Discipleship meetings",
           "training_session": "Training sessions", "church_plant": "Church plant activities",
           "baptism": "Baptisms", "prayer": "Prayer times", "humanitarian": "Humanitarian aid visits", "other": "Other activities"},
    "es": {"gospel_conversation": "Conversaciones del evangelio", "discipleship_meeting": "Reuniones de discipulado",
           "training_session": "Sesiones de capacitaci\u00f3n", "church_plant": "Actividades de plantaci\u00f3n",
           "baptism": "Bautismos", "prayer": "Tiempos de oraci\u00f3n", "humanitarian": "Visitas de ayuda humanitaria", "other": "Otras actividades"},
}


def generate_report(entries, user, start, end, lang="en"):
    """entries: list of dicts within [start, end]. Returns PDF bytes."""
    labels = TYPE_LABELS[lang]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title2", parent=styles["Title"], textColor=ACCENT, fontSize=22, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=ACCENT, fontSize=14, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("Body2", parent=styles["BodyText"], fontSize=10.5, leading=15)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=9, textColor=colors.grey)

    story = []
    heading = "Field Report" if lang == "en" else "Informe de Campo"
    story.append(Paragraph(heading, title))
    story.append(Paragraph("MissionaryAgents \u2014 NoPlaceLeft Academy", small))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=GOLD, thickness=1.5))
    story.append(Spacer(1, 10))

    place = user.get("field_location") or ("Field location not set" if lang == "en" else "Lugar no registrado")
    meta = [
        [("Missionary:" if lang == "en" else "Misionero:"), user["name"]],
        [("Field:" if lang == "en" else "Campo:"), place],
        [("Period:" if lang == "en" else "Per\u00edodo:"), f"{start} \u2013 {end}"],
        [("Generated:" if lang == "en" else "Generado:"), date.today().isoformat()],
    ]
    mt = Table([[Paragraph(f"<b>{k}</b>", body), Paragraph(v, body)] for k, v in meta], colWidths=[1.4 * inch, 5.1 * inch])
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), LIGHT),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(mt)

    counts = {}
    people = 0
    for e in entries:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
        people += e["people_count"] or 0

    story.append(Paragraph("Summary" if lang == "en" else "Resumen", h2))
    rows = [[Paragraph(f"<b>{labels.get(t, t)}</b>", body), Paragraph(str(n), body)] for t, n in sorted(counts.items())]
    rows.append([Paragraph(f"<b>{'Total activities' if lang == 'en' else 'Actividades totales'}</b>", body),
                 Paragraph(f"<b>{len(entries)}</b>", body)])
    rows.append([Paragraph(f"<b>{'People reached' if lang == 'en' else 'Personas alcanzadas'}</b>", body),
                 Paragraph(f"<b>{people}</b>", body)])
    st = Table(rows, colWidths=[4.5 * inch, 2.0 * inch])
    st.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(st)

    highlights = [e for e in entries if (e.get("notes") or "").strip()][:10]
    if highlights:
        story.append(Paragraph("Highlights" if lang == "en" else "Testimonios", h2))
        for e in highlights:
            note = (e["notes"] or "").strip().replace("\n", " ")
            loc = f" \u2014 {e['location']}" if e.get("location") else ""
            story.append(Paragraph(f"<b>{e['date']}</b>{loc}: {note}", body))
            story.append(Spacer(1, 4))

    story.append(Paragraph("Timeline" if lang == "en" else "Cronolog\u00eda", h2))
    trows = [[Paragraph(f"<b>{'Date' if lang == 'en' else 'Fecha'}</b>", small),
              Paragraph(f"<b>{'Activity' if lang == 'en' else 'Actividad'}</b>", small),
              Paragraph(f"<b>{'People' if lang == 'en' else 'Personas'}</b>", small)]]
    for e in sorted(entries, key=lambda x: x["date"]):
        trows.append([Paragraph(e["date"], small),
                      Paragraph(labels.get(e["type"], e["type"]), small),
                      Paragraph(str(e["people_count"] or 0), small)])
    tt = Table(trows, colWidths=[1.2 * inch, 4.0 * inch, 1.3 * inch])
    tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(tt)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", color=GOLD, thickness=1))
    story.append(Spacer(1, 6))
    thanks = ("Thank you for praying and giving. Every conversation recorded here carries your partnership into the harvest."
              if lang == "en" else
              "Gracias por orar y ofrendar. Cada conversaci\u00f3n registrada aqu\u00ed lleva su compa\u00f1erismo a la cosecha.")
    story.append(Paragraph(thanks, small))
    story.append(Paragraph("Curriculum \u00a9 NoPlaceLeft Academy \u2014 missionaryagents.org", small))

    doc.build(story)
    return buf.getvalue()
