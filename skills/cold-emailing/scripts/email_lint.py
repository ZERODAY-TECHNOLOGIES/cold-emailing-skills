#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_lint.py - verifică un email (cold, follow-up sau răspuns) înainte de a fi salvat.

Detectează:
  ERORI   - em dash / en dash (interzise), placeholder-e necompletate, subiect lipsă
  AVERTIZĂRI - clișee de tip AI, cuvinte "spam", lungime, prea multe linkuri/semne de exclamare,
               cratimă cu spații folosită ca dash, prea mult "noi/eu" față de "dvs./tu" etc.
  INFO    - lipsa unei formule de opt-out, enumerări în trei, punct și virgulă etc.

Utilizare:
  python3 email_lint.py --subject "Subiect" --body-file corp.txt --kind initial
  echo '{"subject": "...", "body": "...", "kind": "follow_up"}' | python3 email_lint.py --stdin
Ieșire: JSON {ok, score, errors[], warnings[], info[], stats{}}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

# --------------------------------------------------------------------------------------
# Liste de reguli
# --------------------------------------------------------------------------------------

FORBIDDEN_DASHES = {
    "—": "em dash (—)",
    "–": "en dash (–)",
    "―": "horizontal bar (―)",
    "‒": "figure dash (‒)",
    "﹘": "small em dash (﹘)",
    "⸺": "two-em dash (⸺)",
    "⸻": "three-em dash (⸻)",
}

# Clișee tipice pentru texte generate de AI sau pentru cold email-uri slabe.
CLICHES = [
    # Română
    "sper ca acest e-mail va gaseste bine", "sper ca acest email va gaseste bine",
    "sper ca acest mesaj va gaseste bine", "sper ca sunteti bine", "sper ca esti bine",
    "in era digitala", "in peisajul actual", "in contextul actual", "intr-o lume in continua schimbare",
    "intr-o lume tot mai", "solutii inovatoare", "solutii inovative", "de ultima generatie",
    "lider de piata", "partener de incredere", "nu ezitati sa", "nu ezita sa", "va stam la dispozitie",
    "valoare adaugata", "sinergie", "sinergii", "la urmatorul nivel", "revolutiona", "revolutionar",
    "abordare holistica", "experienta vasta", "solutii personalizate", "solutii complete",
    "perfect integrat", "fara cusur", "mi-am permis sa va contactez", "imi permit sa va contactez",
    "doar am vrut sa verific", "revin cu un scurt reminder", "va scriu pentru a va prezenta",
    "as dori sa va prezint", "suntem o companie", "suntem o firma", "compania noastra ofera",
    "cu stima si respect", "in speranta unui raspuns favorabil", "astept cu nerabdare raspunsul",
    "puncte de durere", "potential maxim", "este important de mentionat", "merita mentionat",
    "in concluzie", "mai mult decat atat", "nu in ultimul rand",
    # English
    "i hope this email finds you well", "i hope this finds you well", "i hope you're doing well",
    "i hope you are doing well", "in today's fast-paced", "in today's digital", "in today's world",
    "ever-evolving", "ever-changing landscape", "leverage", "seamless", "seamlessly", "game-changer",
    "game changer", "cutting-edge", "state-of-the-art", "revolutionize", "unlock the power",
    "unlock your", "elevate your", "delve", "synergy", "synergies", "holistic", "streamline",
    "empower", "take it to the next level", "next level", "touch base", "circle back",
    "just following up", "just checking in", "just wanted to", "i wanted to reach out",
    "i'm reaching out", "i am reaching out", "don't hesitate to", "do not hesitate to",
    "best-in-class", "world-class", "tailored solutions", "innovative solutions",
    "navigate the complexities", "it's worth noting", "rest assured", "furthermore", "moreover",
    "in conclusion", "pain points", "value proposition", "look no further", "robust solution",
    "i came across your company", "quick question", "hope all is well", "bumping this",
    "bumping this up", "per my last email", "as per my previous email", "looking forward to hearing from you",
]

# Cuvinte/expresii care declanșează filtre anti-spam sau sună a marketing agresiv.
SPAM_WORDS = [
    "gratuit", "gratis", "100%", "garantat", "garantie totala", "oferta limitata", "actioneaza acum",
    "actionati acum", "castiga", "castigati", "bani rapid", "fara risc", "fara obligatii",
    "apasa aici", "click aici", "urgent", "cel mai bun pret", "pret imbatabil", "reducere uriasa",
    "free", "guaranteed", "act now", "limited time", "risk-free", "risk free", "no obligation",
    "click here", "best price", "lowest price", "100% free", "earn money", "make money",
    "double your", "special promotion", "exclusive deal", "$$$", "€€€", "winner", "congratulations",
]

# Formule de opt-out (recomandate în UE pentru cold email B2B).
OPT_OUT_PHRASES = [
    "dezabonare", "dezabona", "nu mai doriti", "nu mai doresti", "nu mai primiti", "nu mai primesti",
    "nu va mai scriu", "nu iti mai scriu", "nu va mai deranjez", "nu te mai deranjez",
    "daca nu este relevant", "daca nu e relevant", "daca nu e cazul", "daca nu este cazul",
    "spuneti-mi si nu", "spune-mi si nu", "scoate", "scot de pe lista",
    "unsubscribe", "opt out", "opt-out", "rather not hear", "won't email you again", "won't email again",
    "i won't email", "i won't follow up", "just say so", "just let me know", "not a priority",
    "won't reach out again", "not relevant", "let me know and i'll stop", "i'll stop",
    "abmelden", "nicht mehr kontaktieren", "desabonner", "ne plus recevoir",
]

BAD_OPENINGS = [
    r"^(ma numesc|numele meu este|sunt \w+ de la|va scriu din partea|va scriu pentru a)",
    r"^(my name is|i am \w+ from|i'm \w+ from|i hope|i wanted to|i am writing to|i'm writing to)",
    r"^(sper ca)",
]

NOT_JUST_PATTERNS = [
    r"\bnu (este |e )?(vorba )?doar (despre |de )?\w+.{0,40}\bci( si)?\b",
    r"\bnot (just|only) (about )?\w+.{0,40}\bit'?s\b",
    r"\bit'?s not (just )?about\b",
    r"\bnu doar\b.{0,60}\bci si\b",
]

SELF_WORDS = {
    "eu", "noi", "nostru", "noastra", "nostri", "noastre", "meu", "mea", "mei", "mele",
    "we", "our", "ours", "us", "my", "me", "i",
    "wir", "unser", "unsere", "unseren", "ich", "nous", "notre", "nos", "je",
}
YOU_WORDS = {
    "tu", "dumneavoastra", "dvs", "voi", "vostru", "voastra", "tau", "tale", "iti", "te",
    "you", "your", "yours", "sie", "ihr", "ihre", "ihnen", "du", "dein", "deine",
    "vous", "votre", "vos",
}

PLACEHOLDER_PATTERNS = [
    (r"\{\{[^}]*\}\}", "placeholder {{...}}"),
    (r"\{[A-Za-z_]{2,30}\}", "placeholder {...}"),
    (r"\[(?:[A-ZĂÂÎȘȚ][\wăâîșțĂÂÎȘȚ ]{1,30}|[a-z_ ]{2,30})\]", "placeholder [...]"),
    (r"<[A-Z_]{3,}>", "placeholder <...>"),
    (r"\bTODO\b", "TODO rămas în text"),
    (r"\bXXX+\b", "XXX rămas în text"),
    (r"\blorem ipsum\b", "lorem ipsum"),
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U0001F900-\U0001F9FF]"
)

WORD_LIMITS = {
    # kind: (minim recomandat, maxim recomandat)
    "initial": (40, 150),
    "follow_up": (15, 100),
    "reply": (10, 220),
}


# --------------------------------------------------------------------------------------
# Utilitare
# --------------------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Litere mici, fără diacritice, apostrofuri drepte."""
    text = text.replace("’", "'").replace("‘", "'").replace("´", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def phrase_hits(norm_text: str, phrases) -> list[str]:
    hits = []
    for p in phrases:
        pn = normalize(p)
        pattern = r"(?<![\w])" + re.escape(pn) + r"(?![\w])"
        if re.search(pattern, norm_text):
            hits.append(p)
    return hits


def words(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:['\-][\w]+)*", text, flags=re.UNICODE)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def strip_greeting_and_signature(body: str) -> str:
    """Aproximează 'miezul' emailului: fără prima linie de salut și fără semnătură."""
    lines = [l for l in body.strip().splitlines()]
    if lines and re.match(
        r"^\s*(buna|salut|hello|hi|hey|dear|stimat|stimata|stimate|hallo|guten|bonjour|ciao|hola|buongiorno)",
        normalize(lines[0]),
    ):
        lines = lines[1:]
    text = "\n".join(lines).strip()
    # taie semnătura la primul "Cu stimă/Mulțumesc/Best/Thanks" de pe linie separată
    m = re.search(
        r"\n\s*(cu (stima|drag|bine|respect)|toate cele bune|o zi buna|multumesc|mersi|best|thanks|cheers|regards|kind regards|mit freundlichen|cordialement)[^\n]*\n",
        normalize(text) + "\n",
    )
    if m:
        text = text[: m.start()]
    return text.strip()


# --------------------------------------------------------------------------------------
# Lint
# --------------------------------------------------------------------------------------

def lint_email(subject: str | None, body: str | None, kind: str = "initial", language: str | None = None) -> dict:
    subject = subject or ""
    body = body or ""
    kind = kind if kind in WORD_LIMITS else "initial"
    errors: list[dict] = []
    warnings: list[dict] = []
    info: list[dict] = []

    def add(bucket, code, msg, **extra):
        item = {"code": code, "message": msg}
        item.update(extra)
        bucket.append(item)

    full = subject + "\n" + body

    # ---- ERORI ----
    for ch, name in FORBIDDEN_DASHES.items():
        count = full.count(ch)
        if count:
            snippets = []
            for m in re.finditer(re.escape(ch), full):
                s = full[max(0, m.start() - 25): m.end() + 25].replace("\n", " ")
                snippets.append(s)
                if len(snippets) >= 3:
                    break
            add(errors, "forbidden_dash", f"{name} apare de {count} ori. Reformulează cu virgulă, punct sau două propoziții.",
                examples=snippets)
    if re.search(r"\w ?-- ?\w", full):
        add(errors, "double_hyphen_dash", "'--' folosit ca înlocuitor de em dash. Reformulează.")

    for pat, label in PLACEHOLDER_PATTERNS:
        found = re.findall(pat, full, flags=re.IGNORECASE if "lorem" in pat else 0)
        if found:
            add(errors, "placeholder", f"{label}: {', '.join(sorted(set(found))[:5])}")

    if not body.strip():
        add(errors, "empty_body", "Corpul emailului este gol.")
    if kind == "initial" and not subject.strip():
        add(errors, "empty_subject", "Emailul inițial nu are subiect.")

    # ---- AVERTIZĂRI ----
    norm_full = normalize(full)
    norm_body = normalize(body)

    cl = phrase_hits(norm_full, CLICHES)
    if cl:
        add(warnings, "cliche", "Clișee/expresii tipice AI sau marketing: " + "; ".join(cl[:10]), phrases=cl)

    sp = phrase_hits(norm_full, SPAM_WORDS)
    if sp:
        add(warnings, "spam_words", "Cuvinte care pot declanșa filtre spam: " + ", ".join(sp), phrases=sp)

    spaced = re.findall(r"(?<=[A-Za-zĂÂÎȘȚăâîșțşţ,]) - (?=[A-Za-zĂÂÎȘȚăâîșțşţ])", body)
    if spaced:
        add(warnings, "spaced_hyphen", f"Cratimă cu spații folosită ca dash ({len(spaced)}x). Folosește virgulă sau punct.")

    body_words = words(body)
    wc = len(body_words)
    lo, hi = WORD_LIMITS[kind]
    if wc > hi:
        add(warnings, "too_long", f"Corpul are {wc} cuvinte; pentru '{kind}' ținta e sub {hi}.")
    elif wc < lo and body.strip():
        add(info, "very_short", f"Corpul are doar {wc} cuvinte; verifică dacă are destul context.")

    long_sents = [s for s in sentences(body) if len(words(s)) > 30]
    if long_sents:
        add(warnings, "long_sentences", f"{len(long_sents)} propoziții au peste 30 de cuvinte. Sparge-le.",
            examples=[s[:120] for s in long_sents[:2]])

    excl = body.count("!") + subject.count("!")
    if excl > 1:
        add(warnings, "exclamations", f"{excl} semne de exclamare. Maxim unul, ideal zero.")
    if "!" in subject:
        add(warnings, "subject_exclamation", "Subiectul conține '!'.")

    links = re.findall(r"https?://\S+|www\.\S+", body)
    if kind == "initial" and len(links) > 1:
        add(warnings, "too_many_links", f"{len(links)} linkuri în primul email. Maxim unul (ideal zero) pentru livrabilitate.")
    elif kind == "initial" and len(links) == 1:
        add(info, "has_link", "Un link în primul email. Fără link livrabilitatea e de obicei mai bună.")

    if EMOJI_RE.search(full):
        add(warnings, "emoji", "Conține emoji. Evită-le în cold email B2B.")

    caps = [w for w in words(body) if len(w) > 3 and w.isupper() and not re.search(r"\d", w)]
    caps = [w for w in caps if w not in {"SRL", "GDPR", "HTML", "SaaS", "CEO", "CTO", "CFO", "COO", "HR", "IT", "ERP", "CRM", "B2B", "B2C", "API", "UE", "EU", "USA", "NATO", "ANAF", "ONRC", "ISO"}]
    if len(caps) > 1:
        add(warnings, "all_caps", "Cuvinte scrise integral cu majuscule: " + ", ".join(caps[:5]))

    if re.search(r"\*\*[^*]+\*\*|__[^_]+__", body):
        add(warnings, "markdown", "Conține formatare markdown (**bold**). Emailul trebuie să fie text simplu.")

    bullets = [l for l in body.splitlines() if re.match(r"^\s*([-*•●▪]|\d+[.)])\s+", l)]
    if kind == "initial" and len(bullets) >= 3:
        add(warnings, "bullets", f"{len(bullets)} linii tip listă. Un cold email arată mai uman ca paragraf scurt.")

    if re.search(r"(?<!\w)#\w+", body):
        add(info, "hashtag", "Conține hashtag-uri.")

    # subiect
    if subject:
        if len(subject) > 60:
            add(warnings, "subject_long", f"Subiectul are {len(subject)} caractere; ținta e sub 50-60.")
        if len(words(subject)) > 9:
            add(warnings, "subject_words", "Subiectul are peste 9 cuvinte.")
        if kind == "initial" and re.match(r"^\s*(re|fw|fwd|aw|tr)\s*:", subject, flags=re.I):
            add(warnings, "fake_reply_subject", "Subiect 'Re:/Fwd:' fals pe primul email. Arată înșelător.")
        caps_subj = [w for w in words(subject) if len(w) > 3 and w.isupper()]
        if caps_subj:
            add(warnings, "subject_caps", "Subiect cu majuscule: " + ", ".join(caps_subj))
        if phrase_hits(normalize(subject), SPAM_WORDS):
            add(warnings, "subject_spam", "Subiectul conține cuvinte spam.")

    # deschidere
    core = strip_greeting_and_signature(body)
    first = normalize(core.split("\n")[0].strip()) if core else ""
    for pat in BAD_OPENINGS:
        if re.search(pat, first):
            add(warnings, "self_opening", "Emailul începe cu tine/firma ta. Deschide cu ceva despre ei (o observație concretă).")
            break

    for pat in NOT_JUST_PATTERNS:
        if re.search(pat, norm_body):
            add(warnings, "not_just_but", "Construcție 'nu doar X, ci Y' / 'not just X, it's Y', tipică textelor AI.")
            break

    tokens = [normalize(w) for w in words(core)]
    self_n = sum(1 for t in tokens if t in SELF_WORDS)
    you_n = sum(1 for t in tokens if t in YOU_WORDS)
    if self_n >= 6 and self_n > you_n * 2:
        add(warnings, "self_focused", f"Prea centrat pe expeditor (eu/noi: {self_n}, tu/dvs.: {you_n}). Vorbește despre ei.")

    questions = core.count("?")
    if kind == "initial" and questions > 2:
        add(warnings, "many_questions", f"{questions} întrebări. Un singur call-to-action clar e mai eficient.")
    if kind in ("initial", "follow_up") and questions == 0:
        add(info, "no_question", "Nicio întrebare. Un CTA sub formă de întrebare simplă crește rata de răspuns.")

    # ---- INFO ----
    if kind == "initial" and not phrase_hits(norm_body, OPT_OUT_PHRASES):
        add(info, "no_opt_out", "Nicio formulă de opt-out (ex. 'Dacă nu e relevant, spuneți-mi și nu vă mai scriu.'). Recomandat în UE.")

    triples = re.findall(r"\b\w+, \w+,? (?:si|și|and|und|et|y|e) \w+\b", body)
    if len(triples) >= 2:
        add(info, "rule_of_three", "Mai multe enumerări în trei ('rapid, simplu și sigur'). Tipic AI dacă apar des.")

    if ";" in body:
        add(info, "semicolon", "Punct și virgulă în text. Rar în emailuri scrise de oameni.")
    if "…" in body or "..." in body:
        add(info, "ellipsis", "Puncte de suspensie. Folosește-le cu grijă.")

    score = 100 - 25 * len(errors) - 7 * len(warnings) - 2 * len(info)
    score = max(0, min(100, score))

    return {
        "ok": not errors,
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "stats": {
            "kind": kind,
            "language": language,
            "body_words": wc,
            "subject_chars": len(subject),
            "sentences": len(sentences(body)),
            "questions": questions,
            "links": len(links),
            "self_words": self_n,
            "you_words": you_n,
        },
    }


def has_forbidden_dash(text: str | None) -> bool:
    if not text:
        return False
    return any(ch in text for ch in FORBIDDEN_DASHES) or bool(re.search(r"\w ?-- ?\w", text))


def main(argv=None):
    p = argparse.ArgumentParser(description="Verifică un email înainte de salvare/trimitere.")
    p.add_argument("--subject", default=None)
    p.add_argument("--body", default=None, help="Corpul emailului (text)")
    p.add_argument("--body-file", default=None, help="Fișier cu corpul emailului")
    p.add_argument("--file", default=None, help="Fișier JSON cu {subject, body, kind, language}")
    p.add_argument("--stdin", action="store_true", help="Citește JSON {subject, body, kind, language} de la stdin")
    p.add_argument("--kind", default=None, choices=list(WORD_LIMITS), help="initial | follow_up | reply")
    p.add_argument("--language", default=None)
    a = p.parse_args(argv)

    data = {}
    if a.stdin:
        data = json.loads(sys.stdin.read())
    elif a.file:
        with open(a.file, encoding="utf-8") as f:
            data = json.load(f)
    subject = a.subject if a.subject is not None else data.get("subject")
    body = a.body if a.body is not None else data.get("body")
    if a.body_file:
        with open(a.body_file, encoding="utf-8") as f:
            body = f.read()
    kind = a.kind or data.get("kind") or "initial"
    language = a.language or data.get("language")

    res = lint_email(subject, body, kind, language)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
