"""Rule-based in-app assistant. Works fully offline over the user's own data.
No external AI API keys required."""
import random
import re
from datetime import date, timedelta

from curriculum import get_curriculum, next_lesson_for

ENCOURAGEMENTS = {
    "en": [
        "\u201cTherefore go and make disciples of all nations...\u201d \u2014 Matthew 28:19. You are living this today.",
        "\u201cThe harvest is plentiful, but the workers are few.\u201d \u2014 Luke 10:2. Thank God you said yes.",
        "Faithfulness in small things \u2014 every conversation, every prayer \u2014 is how movements begin.",
        "\u201cLet us not become weary in doing good, for at the proper time we will reap a harvest.\u201d \u2014 Galatians 6:9",
    ],
    "es": [
        "\u00abPor tanto, id y haced disc\u00edpulos a todas las naciones...\u00bb \u2014 Mateo 28:19. T\u00fa est\u00e1s viviendo esto hoy.",
        "\u00abLa mies es mucha, pero los obreros pocos.\u00bb \u2014 Lucas 10:2. Gracias a Dios que dijiste s\u00ed.",
        "La fidelidad en lo peque\u00f1o \u2014 cada conversaci\u00f3n, cada oraci\u00f3n \u2014 es como comienzan los movimientos.",
        "\u00abNo nos cansemos de hacer el bien, porque a su tiempo cosecharemos.\u00bb \u2014 G\u00e1latas 6:9",
    ],
}

TYPE_LABELS = {
    "en": {"gospel_conversation": "gospel conversations", "discipleship_meeting": "discipleship meetings",
           "training_session": "training sessions", "church_plant": "church plant activities",
           "baptism": "baptisms", "prayer": "prayer times", "humanitarian": "humanitarian aid visits", "other": "other activities"},
    "es": {"gospel_conversation": "conversaciones del evangelio", "discipleship_meeting": "reuniones de discipulado",
           "training_session": "sesiones de capacitaci\u00f3n", "church_plant": "actividades de plantaci\u00f3n",
           "baptism": "bautismos", "prayer": "tiempos de oraci\u00f3n", "humanitarian": "visitas de ayuda humanitaria", "other": "otras actividades"},
}


def _entries_in_range(db_entries, days):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [e for e in db_entries if e["date"] >= cutoff]


def summarize(entries, days, lang):
    sel = _entries_in_range(entries, days)
    labels = TYPE_LABELS[lang]
    if not sel:
        if lang == "es":
            return f"No tienes actividades registradas en los \u00faltimos {days} d\u00edas. \u00a1Sal y registra tu primera obra de esta semana!"
        return f"You have no logged activities in the last {days} days. Go out and log your first one this week!"
    counts = {}
    people = 0
    for e in sel:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
        people += e["people_count"] or 0
    parts = [f"{n} {labels.get(t, t)}" for t, n in sorted(counts.items())]
    if lang == "es":
        s = f"En los \u00faltimos {days} d\u00edas registraste {len(sel)} actividades: " + ", ".join(parts) + f", alcanzando a {people} personas."
        fups = [e for e in sel if e["follow_up"]]
        if fups:
            s += f" Tienes {len(fups)} seguimientos pendientes \u2014 \u00a1no los dejes enfriar!"
        return s
    s = f"In the last {days} days you logged {len(sel)} activities: " + ", ".join(parts) + f", reaching {people} people."
    fups = [e for e in sel if e["follow_up"]]
    if fups:
        s += f" You have {len(fups)} pending follow-ups \u2014 don't let them go cold!"
    return s


def donor_draft(entries, user, days, lang):
    sel = _entries_in_range(entries, days)
    name = user["name"]
    place = user["field_location"] or ("the field" if lang == "en" else "el campo")
    if lang == "es":
        lines = [f"Queridos compa\u00f1eros en la misi\u00f3n,", "",
                 f"Les escribo desde {place} con gratitud por su fidelidad. Esto es lo que Dios ha hecho en los \u00faltimos {days} d\u00edas:"]
    else:
        lines = ["Dear partners in the mission,", "",
                 f"Writing to you from {place} with gratitude for your faithfulness. Here is what God has done in the last {days} days:"]
    if not sel:
        lines.append("- " + ("A\u00fan estoy sembrando y orando; pronto compartir\u00e9 testimonios." if lang == "es"
                              else "Still sowing and praying; testimonies coming soon."))
    else:
        counts = {}
        people = 0
        for e in sel:
            counts[e["type"]] = counts.get(e["type"], 0) + 1
            people += e["people_count"] or 0
        labels = TYPE_LABELS[lang]
        for t, n in sorted(counts.items()):
            lines.append(f"- {n} {labels.get(t, t)}")
        lines.append("- " + (f"{people} personas alcanzadas en total." if lang == "es" else f"{people} people reached in total."))
        highlights = [e for e in sel if (e["notes"] or "").strip()][:3]
        if highlights:
            lines.append("")
            lines.append("Testimonios:" if lang == "es" else "Highlights:")
            for e in highlights:
                note = (e["notes"] or "").strip().replace("\n", " ")
                if len(note) > 220:
                    note = note[:217] + "..."
                lines.append(f"\u2022 {e['date']}: {note}")
    lines += ["", ("Gracias por orar y por ofrendar. Cada conversaci\u00f3n aqu\u00ed lleva su nombre escrito en el cielo."
                   if lang == "es" else "Thank you for praying and giving. Every conversation here carries your name written in heaven."),
              "", ("Con gratitud," if lang == "es" else "With gratitude,"), name]
    return "\n".join(lines)


def quiz(entries_unused, progress, lang):
    lvl, les = next_lesson_for(progress)
    if not les:
        return ("¡Felicidades! Has completado todas las lecciones disponibles. Pide a tu entrenador el Nivel 4."
                if lang == "es" else "Congratulations! You have completed every available lesson. Ask your coach about Level 4.")
    goal = (les.get("look_forward") or "").strip()
    if len(goal) > 400:
        goal = goal[:397] + "..."
    if lang == "es":
        return (f"\U0001f4d6 Pregunta de repaso \u2014 {lvl['name']}, lecci\u00f3n {les['number']}: \u00ab{les['title']}\u00bb\n\n"
                f"Seg\u00fan esta lecci\u00f3n, \u00bfcu\u00e1l es tu meta de obediencia (M.E.T.A.)? Escr\u00edbela con tus palabras y luego comp\u00e1rala:\n\n{goal}")
    return (f"\U0001f4d6 Review question \u2014 {lvl['name']}, Lesson {les['number']}: \u00ab{les['title']}\u00bb\n\n"
            f"According to this lesson, what is your obedience G.O.A.L.? Write it in your own words, then compare:\n\n{goal}")


def log_help(lang):
    if lang == "es":
        return ("Para registrar tu obra ve a Registrar y elige el tipo:\n"
                "\u2022 Conversaci\u00f3n del evangelio \u2014 compartiste las buenas nuevas\n"
                "\u2022 Reuni\u00f3n de discipulado \u2014 3/3 con creyentes\n"
                "\u2022 Sesi\u00f3n de capacitaci\u00f3n \u2014 entrenaste a otros\n"
                "\u2022 Actividad de plantaci\u00f3n \u2014 tu casa de paz / iglesia\n"
                "\u2022 Bautismo \u2014 \u00a1celebra cada uno!\n"
                "Marca \u00abnecesita seguimiento\u00bb cuando alguien quede pendiente de visitar.")
    return ("To log your work go to Log Work and pick the type:\n"
            "\u2022 Gospel conversation \u2014 you shared the good news\n"
            "\u2022 Discipleship meeting \u2014 3/3 with believers\n"
            "\u2022 Training session \u2014 you trained others\n"
            "\u2022 Church plant activity \u2014 your house of peace / church\n"
            "\u2022 Baptism \u2014 celebrate each one!\n"
            "Tick \u201cneeds follow-up\u201d whenever someone is waiting on a visit.")


def answer(message, entries, progress, user, lang):
    """Route a free-text message to the right helper."""
    msg = (message or "").lower()
    quick = (message or "").strip().lower()

    if quick in ("weekly", "week", "resumen", "semana"):
        return summarize(entries, 7, lang)
    if quick in ("donor", "donante", "donantes"):
        return donor_draft(entries, user, 30, lang)
    if quick in ("quiz", "evalua", "evaluame", "eval\u00fame"):
        return quiz(entries, progress, lang)
    if quick in ("loghelp", "ayuda_registro"):
        return log_help(lang)
    if quick in ("encourage", "animo", "\u00e1nimo"):
        return random.choice(ENCOURAGEMENTS[lang])

    has = lambda *words: any(w in msg for w in words)

    if has("week", "semana", "7 days", "resum"):
        return summarize(entries, 7, lang)
    if has("month", "mes", "30 days"):
        return summarize(entries, 30, lang)
    if has("donor", "donante", "donantes", "update", "letter", "carta", "informe"):
        m = re.search(r"(\d+)\s*(day|d\u00eda)", msg)
        days = int(m.group(1)) if m else 30
        return donor_draft(entries, user, days, lang)
    if has("quiz", "test", "exam", "repaso", "eval"):
        return quiz(entries, progress, lang)
    if has("log", "registr", "add entr", "a\u00f1adir"):
        return log_help(lang)
    if has("train", "capacit", "lesson", "lecci", "study", "estudi", "next"):
        lvl, les = next_lesson_for(progress)
        if not les:
            return quiz(entries, progress, lang)
        done = len(progress)
        if lang == "es":
            return (f"Tu pr\u00f3xima lecci\u00f3n es {lvl['name']} \u2014 lecci\u00f3n {les['number']}: \u00ab{les['title']}\u00bb. "
                    f"Llevas {done} lecciones completadas. \u00a1Ve a Capacitaci\u00f3n para estudiarla!")
        return (f"Your next lesson is {lvl['name']} \u2014 Lesson {les['number']}: \u00ab{les['title']}\u00bb. "
                f"You have completed {done} lessons. Head to Training to study it!")
    if has("follow", "seguimiento", "pending", "pendiente"):
        fups = [e for e in entries if e["follow_up"]]
        if not fups:
            return "No pending follow-ups. \u00a1Todo al d\u00eda!" if lang == "es" else "No pending follow-ups. All caught up!"
        lines = [("Tienes estos seguimientos pendientes:" if lang == "es" else "These follow-ups are pending:")]
        for e in fups[:8]:
            lines.append(f"\u2022 {e['date']} \u2014 {(e['location'] or '').strip()} \u2014 {((e['notes'] or '')[:80]).strip()}")
        return "\n".join(lines)
    if has("baptism", "bautismo"):
        n = sum(1 for e in entries if e["type"] == "baptism")
        return (f"\u00a1Has registrado {n} bautismos! Cada uno es una eternidad cambiada." if lang == "es"
                else f"You have logged {n} baptisms! Each one is an eternity changed.")
    if has("hello", "hi", "hola", "hey", "buenas"):
        return ("¡Hola! Soy tu asistente de campo. Puedo resumir tu semana, redactar tu informe para donantes, evaluarte en tu capacitación o ayudarte a registrar tu obra."
                if lang == "es" else
                "Hello! I'm your field assistant. I can summarize your week, draft your donor update, quiz you on training, or help you log work.")
    if has("thank", "gracias"):
        return "¡A Dios sea la gloria! Aquí estoy cuando me necesites." if lang == "es" else "To God be the glory! I'm here whenever you need me."

    if lang == "es":
        return ("Puedo ayudarte con: resumir tu semana o mes, redactar tu carta para donantes, evaluarte en tu capacitaci\u00f3n, "
                "mostrar tus seguimientos pendientes o animarte. Prueba los botones de abajo.")
    return ("I can help you: summarize your week or month, draft your donor letter, quiz you on training, "
            "show pending follow-ups, or encourage you. Try the buttons below.")
