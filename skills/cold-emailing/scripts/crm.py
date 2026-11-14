#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crm.py - memoria persistentă a skill-ului cold-emailing (SQLite, doar biblioteca standard Python).

Locația datelor (în ordinea priorității):
  1. --data-dir PATH       (poate apărea oriunde în linia de comandă)
  2. variabila de mediu COLD_EMAIL_HOME
  3. ~/.cold-email
Baza de date: <data-dir>/crm.db

Toate comenzile scriu JSON pe stdout. Erorile au forma {"ok": false, "error": "..."} și cod de ieșire 1.
Datele complexe se transmit ca JSON: --json '{...}', --file cale.json sau --stdin.

Rulează `python3 crm.py --help` sau `python3 crm.py <comandă> --help`.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import statistics
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from email_lint import has_forbidden_dash, lint_email  # noqa: E402

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------------------
# Vocabular
# --------------------------------------------------------------------------------------

COMPANY_STATUSES = [
    "new",             # găsită, încă necontactată
    "drafted",         # are un email în draft
    "contacted",       # cel puțin un email trimis, fără răspuns
    "replied",         # a răspuns (neutru / întrebare / obiecție / referral)
    "interested",      # interes explicit
    "meeting",         # întâlnire programată / avută
    "won",             # client câștigat
    "lost",            # pierdut după discuții
    "not_interested",  # a refuzat
    "paused",          # "nu acum" - reluăm mai târziu
    "bounced",         # emailul nu a ajuns
    "do_not_contact",  # dezabonat / cerere explicită să nu mai fie contactat
]
POSITIVE_LADDER = ["new", "drafted", "contacted", "replied", "interested", "meeting", "won"]

INBOUND_CLASSES = {
    # clasificare: (status firmă, sentiment, necesită răspuns din partea noastră)
    "interested": ("interested", "positive", True),
    "meeting": ("meeting", "positive", True),
    "question": ("replied", "neutral", True),
    "objection": ("replied", "neutral", True),
    "referral": ("replied", "neutral", True),
    "not_now": ("paused", "neutral", True),
    "not_interested": ("not_interested", "negative", False),
    "unsubscribe": ("do_not_contact", "negative", False),
    "ooo": (None, "neutral", False),
    "bounce": ("bounced", "negative", False),
    "other": ("replied", "neutral", True),
}
REAL_REPLY_CLASSES = {k for k in INBOUND_CLASSES if k not in ("ooo", "bounce")}
POSITIVE_CLASSES = {"interested", "meeting"}

MESSAGE_KINDS_OUT = ["initial", "follow_up", "reply"]
MESSAGE_STATUSES = ["draft", "sent", "bounced", "cancelled", "received"]
EMAIL_STATUSES = ["verified", "found", "guessed", "unknown", "invalid", "catch_all"]

DEFAULT_SETTINGS = {
    "followup_days": "4",        # zile de așteptare după fiecare email fără răspuns
    "max_followups": "2",        # câte follow-up-uri după emailul inițial
    "not_now_days": "90",        # după câte zile reluăm un "nu acum"
    "ooo_days": "7",             # după câte zile reluăm un out-of-office fără dată
}

FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.ro", "yahoo.co.uk", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "me.com", "aol.com", "gmx.de", "gmx.net", "web.de", "mail.ru", "yandex.ru",
    "protonmail.com", "proton.me", "zoho.com",
}

LEGAL_SUFFIXES = [
    "srl", "s r l", "sa", "s a", "srl-d", "pfa", "ii", "if", "snc", "scs", "sca", "ong",
    "gmbh", "ag", "kg", "ug", "ohg", "ltd", "limited", "llc", "inc", "corp", "corporation", "plc", "llp",
    "sas", "sarl", "sasu", "eurl", "bv", "nv", "kft", "zrt", "nyrt", "sp z o o", "spzoo", "sro", "s r o",
    "doo", "d o o", "ad", "eood", "ood", "oy", "ab", "as", "aps", "spa", "s p a", "srls", "sl", "s l",
    "co", "company", "group", "grup",
]

TABLE_FIELDS = {
    "senders": ["full_name", "role", "email", "phone", "linkedin", "signature", "tone", "languages",
                "is_default", "active", "notes"],
    "offerings": ["kind", "name", "summary", "description", "benefits", "target_customers", "pain_points",
                  "differentiators", "pricing", "proof", "cta", "keywords", "active", "notes"],
    "searches": ["criteria", "summary", "notes", "result_count"],
    "companies": ["name", "legal_name", "tax_id", "website", "domain", "country", "region", "city", "address",
                  "industry", "subindustry", "employees", "employees_count", "founded_year", "revenue",
                  "description", "linkedin", "phone", "generic_email", "personalization", "fit_score",
                  "fit_reason", "source", "source_urls", "search_id", "status", "tags", "notes",
                  "next_action", "next_action_at"],
    "contacts": ["company_id", "full_name", "first_name", "last_name", "role", "department", "seniority",
                 "email", "email_status", "email_source", "email_confidence", "phone", "linkedin",
                 "is_primary", "do_not_contact", "notes"],
    "messages": ["company_id", "contact_id", "sender_id", "offering_id", "parent_id", "direction", "kind",
                 "step", "subject", "body", "language", "status", "classification", "sentiment", "to_email",
                 "from_email", "sent_at", "received_at", "notes"],
}
JSON_FIELDS = {"benefits", "pain_points", "keywords", "tags", "source_urls", "languages", "differentiators",
               "target_customers", "proof", "criteria", "extra"}

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS company_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL DEFAULT '{}', updated_at TEXT);
CREATE TABLE IF NOT EXISTS senders (
  id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, role TEXT, email TEXT, phone TEXT,
  linkedin TEXT, signature TEXT, tone TEXT, languages TEXT, is_default INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1, notes TEXT, extra TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS offerings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT DEFAULT 'service', name TEXT NOT NULL, summary TEXT,
  description TEXT, benefits TEXT, target_customers TEXT, pain_points TEXT, differentiators TEXT,
  pricing TEXT, proof TEXT, cta TEXT, keywords TEXT, active INTEGER DEFAULT 1, notes TEXT, extra TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS searches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, criteria TEXT NOT NULL DEFAULT '{}', summary TEXT, notes TEXT,
  result_count INTEGER DEFAULT 0, extra TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, legal_name TEXT, tax_id TEXT, website TEXT,
  domain TEXT, country TEXT, region TEXT, city TEXT, address TEXT, industry TEXT, subindustry TEXT,
  employees TEXT, employees_count INTEGER, founded_year INTEGER, revenue TEXT, description TEXT,
  linkedin TEXT, phone TEXT, generic_email TEXT, personalization TEXT, fit_score INTEGER, fit_reason TEXT,
  source TEXT, source_urls TEXT, search_id INTEGER REFERENCES searches(id) ON DELETE SET NULL,
  status TEXT DEFAULT 'new', tags TEXT, notes TEXT, next_action TEXT, next_action_at TEXT, extra TEXT,
  created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  full_name TEXT, first_name TEXT, last_name TEXT, role TEXT, department TEXT, seniority TEXT, email TEXT,
  email_status TEXT DEFAULT 'unknown', email_source TEXT, email_confidence INTEGER, phone TEXT,
  linkedin TEXT, is_primary INTEGER DEFAULT 0, do_not_contact INTEGER DEFAULT 0, notes TEXT, extra TEXT,
  created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
  sender_id INTEGER REFERENCES senders(id) ON DELETE SET NULL,
  offering_id INTEGER REFERENCES offerings(id) ON DELETE SET NULL,
  parent_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
  direction TEXT NOT NULL DEFAULT 'out', kind TEXT DEFAULT 'initial', step INTEGER DEFAULT 0, subject TEXT,
  body TEXT, language TEXT, status TEXT DEFAULT 'draft', classification TEXT, sentiment TEXT, to_email TEXT,
  from_email TEXT, sent_at TEXT, received_at TEXT, notes TEXT, extra TEXT, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_messages_company ON messages(company_id);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
  contact_id INTEGER, message_id INTEGER, type TEXT, detail TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_activity_company ON activity(company_id);
CREATE TABLE IF NOT EXISTS suppression (
  id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT UNIQUE NOT NULL, kind TEXT, reason TEXT, created_at TEXT);
"""


# --------------------------------------------------------------------------------------
# Utilitare generale
# --------------------------------------------------------------------------------------

class CRMError(Exception):
    pass


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def parse_dt(value) -> str | None:
    """Acceptă 'now', 'today', 'yesterday', '-3d', '+7d', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM[:SS]', ISO."""
    if value is None or value == "":
        return None
    v = str(value).strip().lower()
    base = datetime.now().replace(microsecond=0)
    if v == "now":
        return base.isoformat(sep=" ")
    if v == "today":
        return base.replace(hour=0, minute=0, second=0).isoformat(sep=" ")
    if v == "yesterday":
        return (base - timedelta(days=1)).isoformat(sep=" ")
    m = re.fullmatch(r"([+-]?\d+)d", v)
    if m:
        return (base + timedelta(days=int(m.group(1)))).isoformat(sep=" ")
    s = str(value).strip().replace("T", " ").replace("Z", "")
    s = re.sub(r"[+-]\d{2}:?\d{2}$", "", s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.split(".")[0] if fmt.startswith("%Y") else s, fmt).isoformat(sep=" ")
        except ValueError:
            continue
    raise CRMError(f"Dată nerecunoscută: {value!r}. Folosește YYYY-MM-DD sau YYYY-MM-DD HH:MM.")


def to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.fromisoformat(parse_dt(s))
        except Exception:
            return None


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def normalize_domain(v) -> str | None:
    if not v:
        return None
    v = str(v).strip().lower()
    if "@" in v and "://" not in v:
        v = v.split("@", 1)[1]
    v = re.sub(r"^[a-z]+://", "", v)
    v = re.split(r"[/?#:]", v)[0]
    if v.startswith("www."):
        v = v[4:]
    return v.strip(".") or None


def normalize_name(v) -> str:
    if not v:
        return ""
    s = strip_accents(str(v)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    changed = True
    while changed and s:
        changed = False
        for suf in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
            if s.endswith(" " + suf) and len(s) > len(suf) + 1:
                s = s[: -(len(suf) + 1)].strip()
                changed = True
    return s


def normalize_tax_id(v) -> str:
    if not v:
        return ""
    s = re.sub(r"[^A-Z0-9]", "", str(v).upper())
    if re.fullmatch(r"[A-Z]{2}\d+", s):
        s = s[2:]
    return s


def normalize_email(v) -> str | None:
    if not v:
        return None
    v = str(v).strip().lower()
    v = re.sub(r"^mailto:", "", v)
    return v or None


def encode(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k, v in list(d.items()):
        if k in JSON_FIELDS and isinstance(v, str) and v[:1] in "[{":
            try:
                d[k] = json.loads(v)
            except ValueError:
                pass
    if "extra" in d and not d["extra"]:
        d.pop("extra")
    return d


def out(obj, fmt: str = "json"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if fmt == "text" and isinstance(obj, dict) and "_text" in obj:
        print(obj["_text"])
        return
    if isinstance(obj, dict):
        obj.pop("_text", None)
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def table_text(rows: list[dict], cols: list[str], max_width: int = 38) -> str:
    if not rows:
        return "(nimic)"
    def cell(v):
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        s = str(v).replace("\n", " ")
        return s if len(s) <= max_width else s[: max_width - 1] + "…"
    widths = {c: max(len(c), *(len(cell(r.get(c))) for r in rows)) for c in cols}
    line = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = "\n".join(" | ".join(cell(r.get(c)).ljust(widths[c]) for c in cols) for r in rows)
    return f"{line}\n{sep}\n{body}"


def load_payload(args, required: bool = True):
    data = None
    if getattr(args, "json", None):
        data = json.loads(args.json)
    elif getattr(args, "file", None):
        with open(args.file, encoding="utf-8") as f:
            data = json.load(f)
    elif getattr(args, "stdin", False):
        data = json.loads(sys.stdin.read())
    if data is None and required:
        raise CRMError("Lipsește payload-ul: folosește --json '{...}', --file cale.json sau --stdin.")
    return data


# --------------------------------------------------------------------------------------
# Conexiune
# --------------------------------------------------------------------------------------

def extract_option(argv: list[str], name: str) -> tuple[str | None, list[str]]:
    """Scoate `--name VAL` / `--name=VAL` de oriunde din argv (înainte sau după subcomandă)."""
    value = None
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == name and i + 1 < len(argv):
            value = argv[i + 1]
            i += 2
            continue
        if a.startswith(name + "="):
            value = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    return value, rest


def resolve_data_dir(argv: list[str]) -> tuple[Path, list[str]]:
    data_dir, rest = extract_option(argv, "--data-dir")
    if not data_dir:
        data_dir = os.environ.get("COLD_EMAIL_HOME")
    if not data_dir:
        data_dir = str(Path.home() / ".cold-email")
    return Path(data_dir).expanduser().resolve(), rest


def connect(data_dir: Path, readonly: bool = False) -> sqlite3.Connection:
    db = data_dir / "crm.db"
    if readonly:
        if not db.exists():
            raise CRMError(f"Baza de date nu există încă: {db}")
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    else:
        data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not readonly:
        conn.executescript(DDL)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('created_at', ?)", (now(),))
        conn.execute("INSERT OR IGNORE INTO company_profile(id, data, updated_at) VALUES (1, '{}', NULL)")
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)", (k, v, now()))
        conn.commit()
    return conn


def get_setting(conn, key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def get_int_setting(conn, key):
    try:
        return int(get_setting(conn, key, DEFAULT_SETTINGS.get(key, "0")))
    except (TypeError, ValueError):
        return int(DEFAULT_SETTINGS.get(key, "0"))


# --------------------------------------------------------------------------------------
# CRUD generic
# --------------------------------------------------------------------------------------

def split_fields(table: str, data: dict) -> tuple[dict, dict]:
    cols = TABLE_FIELDS[table]
    row, extra = {}, {}
    for k, v in data.items():
        if k in ("id", "created_at", "updated_at"):
            continue
        if k == "extra" and isinstance(v, dict):
            extra.update(v)
        elif k in cols:
            row[k] = encode(v)
        else:
            extra[k] = v
    return row, extra


def get_row(conn, table, rid):
    return conn.execute(f"SELECT * FROM {table} WHERE id = ?", (rid,)).fetchone()


def require_row(conn, table, rid, label=None):
    r = get_row(conn, table, rid)
    if r is None:
        raise CRMError(f"{label or table} cu id={rid} nu există.")
    return r


def insert(conn, table, data: dict) -> int:
    row, extra = split_fields(table, data)
    if extra:
        row["extra"] = json.dumps(extra, ensure_ascii=False)
    row["created_at"] = row["updated_at"] = now()
    cols = ", ".join(row)
    qs = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", list(row.values()))
    return cur.lastrowid


def update_row(conn, table, rid, data: dict) -> dict:
    existing = require_row(conn, table, rid)
    row, extra = split_fields(table, data)
    if extra:
        old = {}
        if existing["extra"]:
            try:
                old = json.loads(existing["extra"])
            except ValueError:
                old = {}
        old.update(extra)
        old = {k: v for k, v in old.items() if v is not None}
        row["extra"] = json.dumps(old, ensure_ascii=False) if old else None
    if not row:
        return row_to_dict(existing)
    row["updated_at"] = now()
    sets = ", ".join(f"{k} = ?" for k in row)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*row.values(), rid])
    return row_to_dict(get_row(conn, table, rid))


def log(conn, company_id, type_, detail, contact_id=None, message_id=None):
    conn.execute(
        "INSERT INTO activity(company_id, contact_id, message_id, type, detail, created_at) VALUES (?,?,?,?,?,?)",
        (company_id, contact_id, message_id, type_, detail, now()),
    )


# --------------------------------------------------------------------------------------
# Profil firmă, setări
# --------------------------------------------------------------------------------------

PROFILE_RECOMMENDED = ["name", "legal_name", "tax_id", "registration_number", "address", "country", "website",
                       "phone", "email", "industry", "description", "value_proposition", "differentiators",
                       "case_studies", "clients", "founded_year", "team_size", "certifications", "languages"]


def profile_get(conn) -> dict:
    r = conn.execute("SELECT data, updated_at FROM company_profile WHERE id = 1").fetchone()
    data = json.loads(r["data"] or "{}")
    missing = [k for k in ("name", "website", "description", "value_proposition") if not data.get(k)]
    return {"profile": data, "updated_at": r["updated_at"], "missing_recommended": missing,
            "recommended_fields": PROFILE_RECOMMENDED}


def profile_set(conn, patch: dict, replace: bool = False) -> dict:
    cur = {} if replace else json.loads(conn.execute("SELECT data FROM company_profile WHERE id = 1").fetchone()["data"] or "{}")
    for k, v in patch.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    conn.execute("UPDATE company_profile SET data = ?, updated_at = ? WHERE id = 1",
                 (json.dumps(cur, ensure_ascii=False), now()))
    conn.commit()
    return profile_get(conn)


# --------------------------------------------------------------------------------------
# Expeditori și oferte
# --------------------------------------------------------------------------------------

def sender_default(conn):
    r = conn.execute("SELECT * FROM senders WHERE active = 1 ORDER BY is_default DESC, id LIMIT 1").fetchone()
    return row_to_dict(r)


def sender_make_default(conn, sid):
    require_row(conn, "senders", sid, "Expeditorul")
    conn.execute("UPDATE senders SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END", (sid,))


def sender_add(conn, data):
    if not data.get("full_name"):
        raise CRMError("Expeditorul are nevoie de 'full_name'.")
    if data.get("email"):
        data["email"] = normalize_email(data["email"])
    sid = insert(conn, "senders", data)
    has_default = conn.execute("SELECT COUNT(*) c FROM senders WHERE is_default = 1 AND id != ?", (sid,)).fetchone()["c"]
    if data.get("is_default") or not has_default:
        sender_make_default(conn, sid)
    conn.commit()
    return row_to_dict(get_row(conn, "senders", sid))


def offering_add(conn, data):
    if not data.get("name"):
        raise CRMError("Oferta are nevoie de 'name'.")
    data.setdefault("kind", "service")
    oid = insert(conn, "offerings", data)
    conn.commit()
    return row_to_dict(get_row(conn, "offerings", oid))


# --------------------------------------------------------------------------------------
# Suprimare (do-not-contact)
# --------------------------------------------------------------------------------------

def suppression_hits(conn, emails=(), domains=()) -> list[dict]:
    vals = set()
    for e in emails:
        e = normalize_email(e)
        if e:
            vals.add(e)
            d = normalize_domain(e)
            if d and d not in FREE_MAIL_DOMAINS:
                vals.add(d)
    for d in domains:
        d = normalize_domain(d)
        if d:
            vals.add(d)
    if not vals:
        return []
    qs = ",".join("?" for _ in vals)
    return [dict(r) for r in conn.execute(f"SELECT * FROM suppression WHERE value IN ({qs})", list(vals))]


def suppress_add(conn, value, reason=None):
    v = normalize_email(value) if "@" in value else normalize_domain(value)
    if not v:
        raise CRMError("Valoare invalidă pentru suprimare.")
    kind = "email" if "@" in v else "domain"
    conn.execute("INSERT OR IGNORE INTO suppression(value, kind, reason, created_at) VALUES (?,?,?,?)",
                 (v, kind, reason, now()))
    # marchează contactele și firmele afectate
    if kind == "email":
        conn.execute("UPDATE contacts SET do_not_contact = 1, updated_at = ? WHERE lower(email) = ?", (now(), v))
    else:
        conn.execute("UPDATE companies SET status = 'do_not_contact', updated_at = ? WHERE domain = ?", (now(), v))
        conn.execute("UPDATE contacts SET do_not_contact = 1, updated_at = ? WHERE lower(email) LIKE ?", (now(), "%@" + v))
    conn.commit()
    return {"value": v, "kind": kind, "reason": reason}


# --------------------------------------------------------------------------------------
# Firme
# --------------------------------------------------------------------------------------

def company_summary(conn, c: dict) -> dict:
    cid = c["id"]
    msgs = conn.execute(
        "SELECT direction, status, kind, sent_at, received_at, classification FROM messages WHERE company_id = ?",
        (cid,)).fetchall()
    sent = [m for m in msgs if m["direction"] == "out" and m["status"] in ("sent", "bounced")]
    inbound = [m for m in msgs if m["direction"] == "in"]
    drafts = [m for m in msgs if m["direction"] == "out" and m["status"] == "draft"]
    last_sent = max((m["sent_at"] for m in sent if m["sent_at"]), default=None)
    last_in = max((m["received_at"] for m in inbound if m["received_at"]), default=None)
    return {
        "id": cid, "name": c.get("name"), "domain": c.get("domain"), "status": c.get("status"),
        "country": c.get("country"), "industry": c.get("industry"),
        "emails_sent": len(sent), "replies": len(inbound), "drafts": len(drafts),
        "last_sent_at": last_sent, "last_reply_at": last_in,
    }


def find_matches(conn, name=None, domain=None, tax_id=None, email=None, exclude_id=None) -> list[dict]:
    n_name = normalize_name(name)
    n_dom = normalize_domain(domain) if domain else None
    n_tax = normalize_tax_id(tax_id)
    n_email = normalize_email(email)
    email_dom = normalize_domain(n_email) if n_email else None
    if email_dom in FREE_MAIL_DOMAINS:
        email_dom = None
    results = {}

    def add(row, reason, strong):
        d = results.setdefault(row["id"], {"company": row_to_dict(row), "reasons": [], "strong": False})
        if reason not in d["reasons"]:
            d["reasons"].append(reason)
        d["strong"] = d["strong"] or strong

    for row in conn.execute("SELECT * FROM companies"):
        if exclude_id and row["id"] == exclude_id:
            continue
        if n_dom and row["domain"] and normalize_domain(row["domain"]) == n_dom:
            add(row, "domain", True)
        if email_dom and row["domain"] and normalize_domain(row["domain"]) == email_dom:
            add(row, "email_domain", True)
        if n_tax and row["tax_id"] and normalize_tax_id(row["tax_id"]) == n_tax:
            add(row, "tax_id", True)
        if n_name:
            rn = normalize_name(row["name"])
            ln = normalize_name(row["legal_name"])
            if n_name in (rn, ln):
                add(row, "name_exact", True)
            elif len(n_name) >= 4 and ((rn and (n_name in rn or rn in n_name)) or (ln and (n_name in ln or ln in n_name))):
                add(row, "name_similar", False)
    if n_email:
        for row in conn.execute("SELECT company_id FROM contacts WHERE lower(email) = ?", (n_email,)):
            if exclude_id and row["company_id"] == exclude_id:
                continue
            add(get_row(conn, "companies", row["company_id"]), "contact_email", True)
    return list(results.values())


def company_check(conn, name=None, domain=None, tax_id=None, email=None) -> dict:
    matches = find_matches(conn, name, domain, tax_id, email)
    supp = suppression_hits(conn, emails=[email] if email else [], domains=[domain] if domain else [])
    items = []
    for m in matches:
        s = company_summary(conn, m["company"])
        s["match_reasons"] = m["reasons"]
        s["strong_match"] = m["strong"]
        items.append(s)
    items.sort(key=lambda x: (not x["strong_match"], x["id"]))
    strong = [i for i in items if i["strong_match"]]
    already = any(i["emails_sent"] > 0 for i in strong)
    blocked = bool(supp) or any(i["status"] in ("do_not_contact",) for i in strong)
    return {
        "exists": bool(strong),
        "already_contacted": already,
        "blocked": blocked,
        "safe_to_add": not strong and not blocked,
        "matches": items,
        "suppression": supp,
    }


def prepare_company(data: dict) -> dict:
    data = dict(data)
    if data.get("website") and not data.get("domain"):
        data["domain"] = normalize_domain(data["website"])
    elif data.get("domain"):
        data["domain"] = normalize_domain(data["domain"])
    if data.get("status") and data["status"] not in COMPANY_STATUSES:
        raise CRMError(f"Status invalid: {data['status']}. Valori: {', '.join(COMPANY_STATUSES)}")
    for k in ("employees_count", "founded_year", "fit_score", "search_id"):
        if data.get(k) not in (None, ""):
            try:
                data[k] = int(data[k])
            except (TypeError, ValueError):
                data.setdefault("extra", {})[k + "_raw"] = data.pop(k)
    if data.get("next_action_at"):
        data["next_action_at"] = parse_dt(data["next_action_at"])
    return data


def company_add(conn, data: dict, allow_duplicate=False, commit=True) -> dict:
    data = prepare_company(data)
    contacts = data.pop("contacts", None) or []
    if not data.get("name"):
        raise CRMError("Firma are nevoie de 'name'.")
    matches = [m for m in find_matches(conn, data.get("name"), data.get("domain"), data.get("tax_id")) if m["strong"]]
    if matches and not allow_duplicate:
        return {"ok": False, "duplicate": True,
                "error": "Firma există deja în baza de date. Folosește 'company update' sau --allow-duplicate.",
                "existing": [dict(company_summary(conn, m["company"]), match_reasons=m["reasons"]) for m in matches]}
    supp = suppression_hits(conn, domains=[data.get("domain")] if data.get("domain") else [])
    if supp:
        data["status"] = "do_not_contact"
    data.setdefault("status", "new")
    cid = insert(conn, "companies", data)
    log(conn, cid, "created", f"Firmă adăugată (sursa: {data.get('source') or 'nespecificată'})")
    created_contacts = []
    for c in contacts:
        c = dict(c)
        c["company_id"] = cid
        res = contact_add(conn, c, commit=False)
        created_contacts.append(res.get("contact") or res)
    if commit:
        conn.commit()
    return {"ok": True, "company": row_to_dict(get_row(conn, "companies", cid)), "contacts": created_contacts,
            "suppressed": bool(supp)}


def company_show(conn, cid: int) -> dict:
    c = row_to_dict(require_row(conn, "companies", cid, "Firma"))
    contacts = [row_to_dict(r) for r in conn.execute("SELECT * FROM contacts WHERE company_id = ? ORDER BY is_primary DESC, id", (cid,))]
    msgs = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM messages WHERE company_id = ? ORDER BY COALESCE(sent_at, received_at, created_at), id", (cid,))]
    acts = [dict(r) for r in conn.execute("SELECT * FROM activity WHERE company_id = ? ORDER BY id", (cid,))]
    return {"company": c, "summary": company_summary(conn, c), "contacts": contacts, "messages": msgs, "activity": acts}


def set_company_status(conn, cid, status, note=None, force=False):
    if status not in COMPANY_STATUSES:
        raise CRMError(f"Status invalid: {status}. Valori: {', '.join(COMPANY_STATUSES)}")
    c = require_row(conn, "companies", cid, "Firma")
    old = c["status"]
    if old == status:
        return
    if not force and old in POSITIVE_LADDER and status in POSITIVE_LADDER:
        if POSITIVE_LADDER.index(status) < POSITIVE_LADDER.index(old):
            return  # nu retrogradăm automat
    conn.execute("UPDATE companies SET status = ?, updated_at = ? WHERE id = ?", (status, now(), cid))
    log(conn, cid, "status", f"{old} -> {status}" + (f" ({note})" if note else ""))


# --------------------------------------------------------------------------------------
# Contacte
# --------------------------------------------------------------------------------------

def contact_add(conn, data: dict, allow_duplicate=False, commit=True) -> dict:
    data = dict(data)
    if not data.get("company_id"):
        raise CRMError("Contactul are nevoie de 'company_id'.")
    require_row(conn, "companies", data["company_id"], "Firma")
    if data.get("email"):
        data["email"] = normalize_email(data["email"])
        if not allow_duplicate:
            dup = conn.execute("SELECT * FROM contacts WHERE lower(email) = ?", (data["email"],)).fetchone()
            if dup:
                return {"ok": False, "duplicate": True, "error": "Emailul există deja la alt contact.",
                        "existing": row_to_dict(dup)}
    if data.get("email_status") and data["email_status"] not in EMAIL_STATUSES:
        raise CRMError(f"email_status invalid. Valori: {', '.join(EMAIL_STATUSES)}")
    if not data.get("full_name") and (data.get("first_name") or data.get("last_name")):
        data["full_name"] = " ".join(x for x in (data.get("first_name"), data.get("last_name")) if x)
    if data.get("full_name") and not data.get("first_name"):
        parts = data["full_name"].split()
        if len(parts) >= 2:
            data["first_name"], data["last_name"] = parts[0], " ".join(parts[1:])
    if data.get("email") and suppression_hits(conn, emails=[data["email"]]):
        data["do_not_contact"] = 1
    if not conn.execute("SELECT COUNT(*) c FROM contacts WHERE company_id = ?", (data["company_id"],)).fetchone()["c"]:
        data.setdefault("is_primary", 1)
    ctid = insert(conn, "contacts", data)
    log(conn, data["company_id"], "contact_added", data.get("full_name") or data.get("email") or "contact", contact_id=ctid)
    if commit:
        conn.commit()
    return {"ok": True, "contact": row_to_dict(get_row(conn, "contacts", ctid))}


# --------------------------------------------------------------------------------------
# Mesaje
# --------------------------------------------------------------------------------------

def sent_sequence(conn, cid):
    return conn.execute(
        "SELECT * FROM messages WHERE company_id = ? AND direction = 'out' AND kind IN ('initial','follow_up') "
        "AND status IN ('sent','bounced') ORDER BY sent_at, id", (cid,)).fetchall()


def apply_sent_effects(conn, msg_id):
    m = get_row(conn, "messages", msg_id)
    cid = m["company_id"]
    set_company_status(conn, cid, "contacted")
    followup_days = get_int_setting(conn, "followup_days")
    max_fu = get_int_setting(conn, "max_followups")
    seq = sent_sequence(conn, cid)
    sent_at = to_dt(m["sent_at"]) or datetime.now()
    if m["kind"] in ("initial", "follow_up"):
        if len(seq) <= max_fu:
            conn.execute("UPDATE companies SET next_action = 'follow_up', next_action_at = ?, updated_at = ? WHERE id = ?",
                         ((sent_at + timedelta(days=followup_days)).isoformat(sep=" "), now(), cid))
        else:
            conn.execute("UPDATE companies SET next_action = 'sequence_finished', next_action_at = NULL, updated_at = ? WHERE id = ?",
                         (now(), cid))
    else:  # răspunsul nostru la un lead
        conn.execute("UPDATE companies SET next_action = 'await_reply', next_action_at = ?, updated_at = ? WHERE id = ?",
                     ((sent_at + timedelta(days=followup_days)).isoformat(sep=" "), now(), cid))
    log(conn, cid, "sent", f"Trimis: {m['subject'] or '(fără subiect)'} [{m['kind']} #{m['step']}]",
        contact_id=m["contact_id"], message_id=msg_id)


def message_add(conn, data: dict, force=False, ignore_lint=False) -> dict:
    data = dict(data)
    data["direction"] = "out"
    cid = data.get("company_id")
    if not cid:
        raise CRMError("Mesajul are nevoie de 'company_id'.")
    company = require_row(conn, "companies", cid, "Firma")
    kind = data.get("kind") or "initial"
    if kind not in MESSAGE_KINDS_OUT:
        raise CRMError(f"kind invalid pentru mesaj trimis: {kind}. Valori: {', '.join(MESSAGE_KINDS_OUT)}")
    data["kind"] = kind
    status = data.get("status") or "draft"
    if status not in ("draft", "sent"):
        raise CRMError("La adăugare, status poate fi 'draft' sau 'sent'.")
    data["status"] = status

    # regula de aur: fără em dash, niciodată
    if has_forbidden_dash(data.get("subject")) or has_forbidden_dash(data.get("body")):
        lint = lint_email(data.get("subject"), data.get("body"), kind, data.get("language"))
        return {"ok": False, "error": "Emailul conține em dash / en dash. Rescrie fără ele (regulă fixă, nu poate fi ignorată).",
                "lint": lint}

    lint = lint_email(data.get("subject"), data.get("body"), kind, data.get("language"))
    if not lint["ok"] and not ignore_lint:
        return {"ok": False, "error": "Emailul nu a trecut verificarea (vezi lint.errors). Corectează sau folosește --ignore-lint.",
                "lint": lint}

    contact = None
    if data.get("contact_id"):
        contact = require_row(conn, "contacts", data["contact_id"], "Contactul")
        if contact["company_id"] != cid:
            raise CRMError("Contactul nu aparține acestei firme.")
    else:
        contact = conn.execute("SELECT * FROM contacts WHERE company_id = ? AND do_not_contact = 0 "
                               "ORDER BY is_primary DESC, id LIMIT 1", (cid,)).fetchone()
        if contact:
            data["contact_id"] = contact["id"]
    if contact and not data.get("to_email"):
        data["to_email"] = contact["email"]

    # blocaje
    blocks = []
    if company["status"] == "do_not_contact":
        blocks.append("Firma este marcată do_not_contact.")
    if contact is not None and contact["do_not_contact"]:
        blocks.append("Contactul este marcat do_not_contact.")
    if contact is not None and contact["email_status"] == "invalid":
        blocks.append("Emailul contactului este marcat invalid (bounce).")
    supp = suppression_hits(conn, emails=[data.get("to_email")] if data.get("to_email") else [],
                            domains=[company["domain"]] if company["domain"] else [])
    if supp:
        blocks.append("Destinatarul/domeniul este pe lista de suprimare.")
    seq = sent_sequence(conn, cid)
    if kind == "initial" and seq:
        blocks.append(f"Firma a primit deja {len(seq)} email(uri) din secvență. Folosește kind=follow_up sau --force.")
    if blocks and not force:
        return {"ok": False, "blocked": True, "error": " ".join(blocks), "lint": lint}

    if not data.get("sender_id"):
        s = sender_default(conn)
        if s:
            data["sender_id"] = s["id"]
    if data.get("sender_id") and not data.get("from_email"):
        s = get_row(conn, "senders", data["sender_id"])
        if s:
            data["from_email"] = s["email"]

    if data.get("step") is None:
        if kind == "initial":
            data["step"] = 0
        elif kind == "follow_up":
            data["step"] = max(1, len(seq))
        else:
            data["step"] = len(seq)
    if kind in ("follow_up", "reply") and not data.get("parent_id"):
        last = conn.execute("SELECT id FROM messages WHERE company_id = ? AND status IN ('sent','received') "
                            "ORDER BY COALESCE(sent_at, received_at) DESC, id DESC LIMIT 1", (cid,)).fetchone()
        if last:
            data["parent_id"] = last["id"]
    if not data.get("offering_id") and kind != "initial":
        prev = conn.execute("SELECT offering_id FROM messages WHERE company_id = ? AND offering_id IS NOT NULL "
                            "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        if prev:
            data["offering_id"] = prev["offering_id"]
    if status == "sent":
        data["sent_at"] = parse_dt(data.get("sent_at")) or now()

    mid = insert(conn, "messages", data)
    if status == "draft":
        set_company_status(conn, cid, "drafted")
        log(conn, cid, "draft", f"Draft creat: {data.get('subject') or '(fără subiect)'} [{kind}]",
            contact_id=data.get("contact_id"), message_id=mid)
    else:
        apply_sent_effects(conn, mid)
    conn.commit()
    return {"ok": True, "message": row_to_dict(get_row(conn, "messages", mid)), "lint": lint}


def message_mark_sent(conn, ids, at=None) -> dict:
    done = []
    for mid in ids:
        m = require_row(conn, "messages", mid, "Mesajul")
        if m["direction"] != "out":
            raise CRMError(f"Mesajul {mid} nu este un mesaj trimis de noi.")
        if m["status"] == "sent":
            done.append({"id": mid, "already_sent": True})
            continue
        if has_forbidden_dash(m["subject"]) or has_forbidden_dash(m["body"]):
            raise CRMError(f"Mesajul {mid} conține em dash. Actualizează textul înainte de a-l marca trimis.")
        sent_at = parse_dt(at) if at else now()
        conn.execute("UPDATE messages SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?", (sent_at, now(), mid))
        apply_sent_effects(conn, mid)
        done.append({"id": mid, "company_id": m["company_id"], "sent_at": sent_at})
    conn.commit()
    return {"ok": True, "marked": done}


def resolve_company_from_email(conn, email):
    email = normalize_email(email)
    if not email:
        return None, None
    ct = conn.execute("SELECT * FROM contacts WHERE lower(email) = ?", (email,)).fetchone()
    if ct:
        return ct["company_id"], ct["id"]
    dom = normalize_domain(email)
    if dom and dom not in FREE_MAIL_DOMAINS:
        c = conn.execute("SELECT id FROM companies WHERE domain = ?", (dom,)).fetchone()
        if c:
            return c["id"], None
    return None, None


def inbound_add(conn, data: dict) -> dict:
    data = dict(data)
    cls = data.get("classification")
    if cls not in INBOUND_CLASSES:
        raise CRMError(f"'classification' obligatoriu. Valori: {', '.join(INBOUND_CLASSES)}")
    if not data.get("company_id"):
        cid, ctid = resolve_company_from_email(conn, data.get("from_email"))
        if not cid:
            raise CRMError("Nu am putut identifica firma. Dă 'company_id' sau un 'from_email' cunoscut.")
        data["company_id"] = cid
        if ctid and not data.get("contact_id"):
            data["contact_id"] = ctid
    cid = data["company_id"]
    require_row(conn, "companies", cid, "Firma")
    if not data.get("contact_id") and data.get("from_email"):
        _, ctid = resolve_company_from_email(conn, data["from_email"])
        if ctid:
            data["contact_id"] = ctid
    new_status, sentiment, _needs = INBOUND_CLASSES[cls]
    data.setdefault("sentiment", sentiment)
    data["direction"] = "in"
    data["kind"] = "inbound"
    data["status"] = "received"
    data["received_at"] = parse_dt(data.get("received_at")) or now()
    follow_up_at = parse_dt(data.pop("follow_up_at", None)) if data.get("follow_up_at") else None
    if not data.get("parent_id"):
        last = conn.execute("SELECT id, step FROM messages WHERE company_id = ? AND direction = 'out' AND status IN ('sent','bounced') "
                            "ORDER BY sent_at DESC, id DESC LIMIT 1", (cid,)).fetchone()
        if last:
            data["parent_id"] = last["id"]
            data.setdefault("step", last["step"])
    mid = insert(conn, "messages", data)

    effects = []
    if new_status:
        set_company_status(conn, cid, new_status, note=f"răspuns: {cls}",
                           force=new_status in ("not_interested", "do_not_contact", "bounced", "paused"))
        effects.append(f"status -> {new_status}")
    if cls == "unsubscribe":
        target = data.get("from_email")
        if not target and data.get("contact_id"):
            target = get_row(conn, "contacts", data["contact_id"])["email"]
        if target:
            suppress_add(conn, target, reason="a cerut dezabonare")
            effects.append(f"suprimat: {target}")
        if data.get("contact_id"):
            conn.execute("UPDATE contacts SET do_not_contact = 1 WHERE id = ?", (data["contact_id"],))
        conn.execute("UPDATE companies SET next_action = NULL, next_action_at = NULL WHERE id = ?", (cid,))
    elif cls == "bounce":
        if data.get("contact_id"):
            conn.execute("UPDATE contacts SET email_status = 'invalid', updated_at = ? WHERE id = ?", (now(), data["contact_id"]))
            effects.append("email contact -> invalid")
        if data.get("parent_id"):
            conn.execute("UPDATE messages SET status = 'bounced', updated_at = ? WHERE id = ?", (now(), data["parent_id"]))
        conn.execute("UPDATE companies SET next_action = 'find_new_contact', next_action_at = NULL WHERE id = ?", (cid,))
    elif cls == "ooo":
        when = follow_up_at or (datetime.now() + timedelta(days=get_int_setting(conn, "ooo_days"))).replace(microsecond=0).isoformat(sep=" ")
        conn.execute("UPDATE companies SET next_action = 'follow_up', next_action_at = ? WHERE id = ?", (when, cid))
        effects.append(f"follow-up reprogramat la {when}")
    elif cls == "not_now":
        when = follow_up_at or (datetime.now() + timedelta(days=get_int_setting(conn, "not_now_days"))).replace(microsecond=0).isoformat(sep=" ")
        conn.execute("UPDATE companies SET next_action = 'reconnect', next_action_at = ? WHERE id = ?", (when, cid))
        effects.append(f"reluare programată la {when}")
    elif cls == "not_interested":
        conn.execute("UPDATE companies SET next_action = NULL, next_action_at = NULL WHERE id = ?", (cid,))
    else:
        conn.execute("UPDATE companies SET next_action = 'reply', next_action_at = ? WHERE id = ?", (now(), cid))
        effects.append("necesită răspuns")
    log(conn, cid, "inbound", f"Răspuns primit [{cls}]: {data.get('subject') or ''}".strip(),
        contact_id=data.get("contact_id"), message_id=mid)
    conn.commit()
    return {"ok": True, "message": row_to_dict(get_row(conn, "messages", mid)), "effects": effects,
            "company": company_summary(conn, row_to_dict(get_row(conn, "companies", cid)))}


# --------------------------------------------------------------------------------------
# Follow-up-uri
# --------------------------------------------------------------------------------------

def followups(conn, lookahead_days=0) -> dict:
    nowdt = datetime.now()
    horizon = nowdt + timedelta(days=lookahead_days)
    followup_days = get_int_setting(conn, "followup_days")
    max_fu = get_int_setting(conn, "max_followups")
    needs_reply, due, scheduled, drafts_pending = [], [], [], []

    for c in conn.execute("SELECT * FROM companies WHERE status NOT IN ('do_not_contact','won','lost','not_interested','bounced')"):
        c = row_to_dict(c)
        cid = c["id"]
        msgs = [row_to_dict(m) for m in conn.execute(
            "SELECT * FROM messages WHERE company_id = ? ORDER BY COALESCE(sent_at, received_at, created_at), id", (cid,))]
        if not msgs:
            continue
        drafts = [m for m in msgs if m["direction"] == "out" and m["status"] == "draft"]
        done = [m for m in msgs if m["status"] in ("sent", "received", "bounced")]
        last = done[-1] if done else None
        primary = conn.execute("SELECT id, full_name, email FROM contacts WHERE company_id = ? ORDER BY is_primary DESC, id LIMIT 1",
                               (cid,)).fetchone()
        base = {"company_id": cid, "company": c["name"], "status": c["status"],
                "contact": dict(primary) if primary else None,
                "last_subject": last["subject"] if last else None,
                "language": next((m["language"] for m in reversed(msgs) if m.get("language")), None),
                "offering_id": next((m["offering_id"] for m in reversed(msgs) if m.get("offering_id")), None)}
        if drafts:
            drafts_pending.append(dict(base, draft_ids=[d["id"] for d in drafts]))
            continue
        if not last:
            continue
        if last["direction"] == "in":
            cls = last.get("classification")
            if cls in INBOUND_CLASSES and INBOUND_CLASSES[cls][2] and cls != "not_now":
                age = (nowdt - (to_dt(last["received_at"]) or nowdt)).days
                needs_reply.append(dict(base, inbound_message_id=last["id"], classification=cls, days_waiting=age))
                continue
        nat = to_dt(c.get("next_action_at"))
        seq = [m for m in msgs if m["direction"] == "out" and m["kind"] in ("initial", "follow_up") and m["status"] in ("sent", "bounced")]
        real_replies = [m for m in msgs if m["direction"] == "in" and m.get("classification") in REAL_REPLY_CLASSES]
        if c.get("next_action") in ("follow_up",) and not real_replies and seq:
            last_out = seq[-1]
            days_since = (nowdt - (to_dt(last_out["sent_at"]) or nowdt)).days
            when = nat or ((to_dt(last_out["sent_at"]) or nowdt) + timedelta(days=followup_days))
            item = dict(base, next_step=len(seq), max_followups=max_fu, days_since_last=days_since,
                        due_at=when.isoformat(sep=" "), last_sent_message_id=last_out["id"])
            if len(seq) > max_fu:
                continue
            if when <= nowdt:
                due.append(item)
            elif when <= horizon:
                scheduled.append(dict(item, reason="follow_up"))
            continue
        if nat and c.get("next_action") in ("reconnect", "await_reply", "follow_up"):
            item = dict(base, next_action=c["next_action"], due_at=c["next_action_at"])
            if nat <= nowdt:
                due.append(dict(item, next_step=len(seq), reason=c["next_action"]))
            elif nat <= horizon:
                scheduled.append(dict(item, reason=c["next_action"]))

    due.sort(key=lambda x: x.get("due_at") or "")
    scheduled.sort(key=lambda x: x.get("due_at") or "")
    needs_reply.sort(key=lambda x: -x["days_waiting"])
    return {"needs_reply": needs_reply, "follow_ups_due": due, "upcoming": scheduled,
            "drafts_pending": drafts_pending,
            "settings": {"followup_days": followup_days, "max_followups": max_fu}}


# --------------------------------------------------------------------------------------
# Statistici
# --------------------------------------------------------------------------------------

def size_band(c: dict) -> str:
    n = c.get("employees_count")
    if isinstance(n, int):
        if n < 10:
            return "micro (<10)"
        if n < 50:
            return "mica (10-49)"
        if n < 250:
            return "medie (50-249)"
        return "mare (250+)"
    return c.get("employees") or "necunoscut"


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def compute_stats(conn, since=None, until=None, by=None) -> dict:
    since_dt = to_dt(parse_dt(since)) if since else None
    until_dt = to_dt(parse_dt(until)) if until else None

    def in_range(s):
        d = to_dt(s)
        if d is None:
            return False
        if since_dt and d < since_dt:
            return False
        if until_dt and d > until_dt:
            return False
        return True

    companies = {r["id"]: row_to_dict(r) for r in conn.execute("SELECT * FROM companies")}
    senders = {r["id"]: r["full_name"] for r in conn.execute("SELECT id, full_name FROM senders")}
    offerings = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM offerings")}
    contacts = {r["id"]: row_to_dict(r) for r in conn.execute("SELECT * FROM contacts")}
    searches = {r["id"]: (r["summary"] or f"căutarea #{r['id']}") for r in conn.execute("SELECT id, summary FROM searches")}
    msgs = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM messages ORDER BY COALESCE(sent_at, received_at, created_at), id")]

    by_company: dict[int, list] = {}
    for m in msgs:
        by_company.setdefault(m["company_id"], []).append(m)

    # volum de emailuri în interval
    sent_in_range = [m for m in msgs if m["direction"] == "out" and m["status"] in ("sent", "bounced") and in_range(m["sent_at"])]
    inbound_in_range = [m for m in msgs if m["direction"] == "in" and in_range(m["received_at"])]

    threads = []
    for cid, ms in by_company.items():
        outs = [m for m in ms if m["direction"] == "out" and m["kind"] in ("initial", "follow_up") and m["status"] in ("sent", "bounced")]
        if not outs:
            continue
        first = outs[0]
        if not in_range(first["sent_at"]):
            continue
        c = companies.get(cid, {})
        first_dt = to_dt(first["sent_at"])
        ins = [m for m in ms if m["direction"] == "in"]
        real = [m for m in ins if m.get("classification") in REAL_REPLY_CLASSES]
        first_reply = real[0] if real else None
        reply_step = None
        days_to_reply = None
        if first_reply:
            rdt = to_dt(first_reply["received_at"])
            before = [o for o in outs if (to_dt(o["sent_at"]) or first_dt) <= (rdt or first_dt)]
            reply_step = (len(before) - 1) if before else 0
            if rdt and first_dt:
                days_to_reply = round((rdt - first_dt).total_seconds() / 86400, 1)
        classes = {m.get("classification") for m in ins}
        ct = contacts.get(first.get("contact_id")) or {}
        threads.append({
            "company_id": cid,
            "replied": bool(real),
            "positive": bool(classes & POSITIVE_CLASSES) or c.get("status") in ("interested", "meeting", "won"),
            "meeting": "meeting" in classes or c.get("status") in ("meeting", "won"),
            "won": c.get("status") == "won",
            "bounced": "bounce" in classes or c.get("status") == "bounced" or any(o["status"] == "bounced" for o in outs),
            "unsubscribed": "unsubscribe" in classes,
            "not_interested": "not_interested" in classes or c.get("status") == "not_interested",
            "ooo": "ooo" in classes,
            "reply_step": reply_step,
            "days_to_reply": days_to_reply,
            "emails_in_sequence": len(outs),
            "groups": {
                "offering": offerings.get(first.get("offering_id"), "nespecificat"),
                "sender": senders.get(first.get("sender_id"), "nespecificat"),
                "language": first.get("language") or "nespecificat",
                "industry": c.get("industry") or "nespecificat",
                "country": c.get("country") or "nespecificat",
                "size": size_band(c),
                "month": (first.get("sent_at") or "")[:7] or "nespecificat",
                "week": first_dt.strftime("%G-W%V") if first_dt else "nespecificat",
                "seniority": ct.get("seniority") or "nespecificat",
                "search": searches.get(c.get("search_id"), "fără căutare"),
                "status": c.get("status") or "nespecificat",
            },
        })

    def aggregate(ts):
        n = len(ts)
        replied = sum(t["replied"] for t in ts)
        positive = sum(t["positive"] for t in ts)
        days = [t["days_to_reply"] for t in ts if t["days_to_reply"] is not None]
        return {
            "companies_contacted": n,
            "replied": replied, "reply_rate_pct": pct(replied, n),
            "positive": positive, "positive_rate_pct": pct(positive, n),
            "positive_of_replies_pct": pct(positive, replied),
            "meetings": sum(t["meeting"] for t in ts), "meeting_rate_pct": pct(sum(t["meeting"] for t in ts), n),
            "won": sum(t["won"] for t in ts),
            "bounced": sum(t["bounced"] for t in ts), "bounce_rate_pct": pct(sum(t["bounced"] for t in ts), n),
            "unsubscribed": sum(t["unsubscribed"] for t in ts),
            "not_interested": sum(t["not_interested"] for t in ts),
            "avg_days_to_reply": round(statistics.mean(days), 1) if days else None,
            "median_days_to_reply": round(statistics.median(days), 1) if days else None,
        }

    overall = aggregate(threads)
    reply_by_step = {}
    for t in threads:
        if t["reply_step"] is not None:
            key = "initial" if t["reply_step"] == 0 else f"follow_up_{t['reply_step']}"
            reply_by_step[key] = reply_by_step.get(key, 0) + 1

    pipeline = {}
    for c in companies.values():
        pipeline[c["status"]] = pipeline.get(c["status"], 0) + 1

    result = {
        "period": {"since": since, "until": until},
        "volume": {
            "emails_sent": len(sent_in_range),
            "initial_sent": sum(1 for m in sent_in_range if m["kind"] == "initial"),
            "follow_ups_sent": sum(1 for m in sent_in_range if m["kind"] == "follow_up"),
            "replies_sent": sum(1 for m in sent_in_range if m["kind"] == "reply"),
            "inbound_received": len(inbound_in_range),
            "inbound_by_classification": {},
            "drafts_pending": conn.execute("SELECT COUNT(*) c FROM messages WHERE status = 'draft'").fetchone()["c"],
        },
        "funnel": overall,
        "reply_by_step": reply_by_step,
        "pipeline_all_time": dict(sorted(pipeline.items(), key=lambda x: -x[1])),
        "database": {
            "companies": len(companies),
            "contacts": len(contacts),
            "contacts_with_email": sum(1 for c in contacts.values() if c.get("email")),
            "emails_verified": sum(1 for c in contacts.values() if c.get("email_status") == "verified"),
            "suppressed": conn.execute("SELECT COUNT(*) c FROM suppression").fetchone()["c"],
        },
    }
    for m in inbound_in_range:
        k = m.get("classification") or "neclasificat"
        result["volume"]["inbound_by_classification"][k] = result["volume"]["inbound_by_classification"].get(k, 0) + 1

    dims = by or []
    breakdowns = {}
    for d in dims:
        groups: dict[str, list] = {}
        for t in threads:
            groups.setdefault(str(t["groups"].get(d, "nespecificat")), []).append(t)
        rows = []
        for g, ts in groups.items():
            a = aggregate(ts)
            rows.append({d: g, **a})
        rows.sort(key=lambda r: (-r["companies_contacted"], r[d]))
        breakdowns[d] = rows
    if breakdowns:
        result["breakdowns"] = breakdowns

    # varianta text
    lines = []
    lines.append(f"STATISTICI COLD EMAILING  (interval: {since or 'început'} -> {until or 'azi'})")
    v = result["volume"]
    lines.append(f"Emailuri trimise: {v['emails_sent']} (inițiale {v['initial_sent']}, follow-up {v['follow_ups_sent']}, răspunsuri {v['replies_sent']})")
    lines.append(f"Răspunsuri primite: {v['inbound_received']}  {v['inbound_by_classification']}")
    lines.append(f"Drafturi netrimise: {v['drafts_pending']}")
    f = overall
    lines.append("")
    lines.append(f"Firme contactate: {f['companies_contacted']}")
    lines.append(f"Au răspuns: {f['replied']} ({f['reply_rate_pct']}%)   Pozitiv: {f['positive']} ({f['positive_rate_pct']}%)")
    lines.append(f"Întâlniri: {f['meetings']} ({f['meeting_rate_pct']}%)   Câștigate: {f['won']}")
    lines.append(f"Bounce: {f['bounced']} ({f['bounce_rate_pct']}%)   Dezabonări: {f['unsubscribed']}   Refuzuri: {f['not_interested']}")
    lines.append(f"Timp până la răspuns: medie {f['avg_days_to_reply']} zile, mediană {f['median_days_to_reply']} zile")
    lines.append(f"Răspunsuri după pasul secvenței: {reply_by_step}")
    lines.append(f"Pipeline (toate firmele): {result['pipeline_all_time']}")
    for d, rows in breakdowns.items():
        lines.append("")
        lines.append(f"PE {d.upper()}:")
        lines.append(table_text(rows, [d, "companies_contacted", "replied", "reply_rate_pct", "positive",
                                       "positive_rate_pct", "meetings", "bounced"]))
    result["_text"] = "\n".join(lines)
    return result


# --------------------------------------------------------------------------------------
# Overview / export / backup
# --------------------------------------------------------------------------------------

def overview(conn, data_dir: Path) -> dict:
    prof = profile_get(conn)
    senders = [row_to_dict(r) for r in conn.execute("SELECT id, full_name, role, email, is_default FROM senders WHERE active = 1")]
    offerings = [row_to_dict(r) for r in conn.execute("SELECT id, kind, name, summary FROM offerings WHERE active = 1")]
    pipeline = {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM companies GROUP BY status")}
    fu = followups(conn)
    hints = []
    if prof["missing_recommended"]:
        hints.append("Profilul firmei e incomplet: " + ", ".join(prof["missing_recommended"]))
    if not senders:
        hints.append("Nu există niciun expeditor salvat.")
    if not offerings:
        hints.append("Nu există niciun serviciu/produs salvat.")
    if fu["needs_reply"]:
        hints.append(f"{len(fu['needs_reply'])} lead(uri) așteaptă răspunsul nostru.")
    if fu["follow_ups_due"]:
        hints.append(f"{len(fu['follow_ups_due'])} follow-up(uri) scadente.")
    if fu["drafts_pending"]:
        hints.append(f"{len(fu['drafts_pending'])} firme au drafturi netrimise (marchează-le trimise după expediere).")
    last_backup = None
    bdir = data_dir / "backups"
    if bdir.exists():
        files = sorted(bdir.glob("*.db"))
        if files:
            last_backup = files[-1].name
    return {
        "data_dir": str(data_dir), "db": str(data_dir / "crm.db"),
        "company_profile": {"name": prof["profile"].get("name"), "missing_recommended": prof["missing_recommended"]},
        "senders": senders, "offerings": offerings,
        "companies_total": sum(pipeline.values()), "pipeline": pipeline,
        "needs_reply": len(fu["needs_reply"]), "follow_ups_due": len(fu["follow_ups_due"]),
        "drafts_pending": len(fu["drafts_pending"]),
        "settings": {r["key"]: mask(r["key"], r["value"]) for r in conn.execute("SELECT key, value FROM settings")},
        "last_backup": last_backup,
        "hints": hints,
    }


def mask(key, value):
    if value and any(t in key.lower() for t in ("key", "token", "secret", "password")):
        return value[:4] + "…" + value[-2:] if len(value) > 8 else "***"
    return value


def export_csv(conn, data_dir: Path, what: str, out_dir: str | None) -> dict:
    target = Path(out_dir).expanduser() if out_dir else data_dir / "exports" / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    files = []
    queries = {
        "companies": "SELECT c.*, (SELECT email FROM contacts WHERE company_id = c.id ORDER BY is_primary DESC, id LIMIT 1) AS primary_email, "
                     "(SELECT full_name FROM contacts WHERE company_id = c.id ORDER BY is_primary DESC, id LIMIT 1) AS primary_contact "
                     "FROM companies c ORDER BY c.id",
        "contacts": "SELECT ct.*, c.name AS company_name FROM contacts ct JOIN companies c ON c.id = ct.company_id ORDER BY ct.id",
        "messages": "SELECT m.*, c.name AS company_name FROM messages m JOIN companies c ON c.id = m.company_id ORDER BY m.id",
        "offerings": "SELECT * FROM offerings ORDER BY id",
        "senders": "SELECT * FROM senders ORDER BY id",
        "suppression": "SELECT * FROM suppression ORDER BY id",
    }
    names = list(queries) if what == "all" else [what]
    for n in names:
        if n not in queries:
            raise CRMError(f"Nu pot exporta '{n}'. Valori: all, {', '.join(queries)}")
        cur = conn.execute(queries[n])
        cols = [d[0] for d in cur.description]
        path = target / f"{n}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in cur:
                w.writerow(list(r))
        files.append(str(path))
    return {"ok": True, "files": files}


def backup(conn, data_dir: Path, out_path: str | None) -> dict:
    path = Path(out_path).expanduser() if out_path else data_dir / "backups" / f"crm-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(str(path))
    with dst:
        conn.backup(dst)
    dst.close()
    return {"ok": True, "backup": str(path), "bytes": path.stat().st_size}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def add_payload_args(p, required=True):
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--json", help="Payload JSON ca text")
    g.add_argument("--file", help="Cale către un fișier JSON")
    g.add_argument("--stdin", action="store_true", help="Citește JSON de la stdin")


def build_parser():
    p = argparse.ArgumentParser(prog="crm.py", description="Memoria persistentă a skill-ului cold-emailing. "
                                "Opțiuni globale (oriunde în comandă): --data-dir PATH, --format json|text.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Creează baza de date (idempotent)")
    sub.add_parser("where", help="Arată unde sunt datele")
    sub.add_parser("overview", help="Rezumat: profil, expeditori, oferte, pipeline, ce e de făcut")
    sub.add_parser("schema", help="Câmpurile acceptate pentru fiecare entitate și valorile permise")

    # profil
    pr = sub.add_parser("profile", help="Profilul firmei din partea căreia se scrie")
    prs = pr.add_subparsers(dest="action", required=True)
    prs.add_parser("show")
    x = prs.add_parser("set", help="Actualizează câmpuri (merge). Valoarea null șterge câmpul.")
    add_payload_args(x)
    x = prs.add_parser("replace", help="Înlocuiește complet profilul")
    add_payload_args(x)

    # expeditori
    se = sub.add_parser("sender", help="Persoanele care semnează emailurile")
    ses = se.add_subparsers(dest="action", required=True)
    x = ses.add_parser("list"); x.add_argument("--all", action="store_true", help="Include și inactivi")
    x = ses.add_parser("show"); x.add_argument("id", type=int)
    x = ses.add_parser("add"); add_payload_args(x)
    x = ses.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)
    x = ses.add_parser("default"); x.add_argument("id", type=int)
    x = ses.add_parser("remove", help="Dezactivează"); x.add_argument("id", type=int)

    # oferte
    of = sub.add_parser("offering", help="Serviciile și produsele firmei")
    ofs = of.add_subparsers(dest="action", required=True)
    x = ofs.add_parser("list"); x.add_argument("--all", action="store_true")
    x = ofs.add_parser("show"); x.add_argument("id", type=int)
    x = ofs.add_parser("add"); add_payload_args(x)
    x = ofs.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)
    x = ofs.add_parser("remove", help="Dezactivează"); x.add_argument("id", type=int)

    # căutări
    sr = sub.add_parser("search", help="Criteriile căutărilor de firme")
    srs = sr.add_subparsers(dest="action", required=True)
    x = srs.add_parser("add"); add_payload_args(x)
    x = srs.add_parser("list"); x.add_argument("--limit", type=int, default=20)
    x = srs.add_parser("show"); x.add_argument("id", type=int)
    x = srs.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)

    # firme
    co = sub.add_parser("company", help="Firmele țintă (lead-uri)")
    cos = co.add_subparsers(dest="action", required=True)
    x = cos.add_parser("add"); add_payload_args(x); x.add_argument("--allow-duplicate", action="store_true")
    x = cos.add_parser("import", help="Adaugă o listă de firme (JSON array), sare peste duplicate")
    add_payload_args(x); x.add_argument("--search-id", type=int); x.add_argument("--allow-duplicate", action="store_true")
    x = cos.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)
    x = cos.add_parser("show"); x.add_argument("id", type=int)
    for name in ("check", "find"):
        x = cos.add_parser(name, help="Verifică dacă o firmă/email există deja sau e blocat")
        x.add_argument("--name"); x.add_argument("--domain"); x.add_argument("--tax-id"); x.add_argument("--email")
        x.add_argument("--q", help="Text liber (nume parțial)")
    x = cos.add_parser("list")
    x.add_argument("--status"); x.add_argument("--country"); x.add_argument("--industry")
    x.add_argument("--search-id", type=int); x.add_argument("--q"); x.add_argument("--limit", type=int, default=50)
    x.add_argument("--uncontacted", action="store_true", help="Doar firme fără emailuri trimise")
    x = cos.add_parser("status"); x.add_argument("id", type=int); x.add_argument("status", choices=COMPANY_STATUSES)
    x.add_argument("--note"); x.add_argument("--next-action"); x.add_argument("--next-action-at")
    x = cos.add_parser("delete"); x.add_argument("id", type=int); x.add_argument("--yes", action="store_true")

    # contacte
    ct = sub.add_parser("contact", help="Persoane de contact")
    cts = ct.add_subparsers(dest="action", required=True)
    x = cts.add_parser("add"); add_payload_args(x); x.add_argument("--allow-duplicate", action="store_true")
    x = cts.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)
    x = cts.add_parser("list"); x.add_argument("--company", type=int); x.add_argument("--q"); x.add_argument("--limit", type=int, default=100)
    x = cts.add_parser("show"); x.add_argument("id", type=int)
    x = cts.add_parser("remove"); x.add_argument("id", type=int)

    # mesaje
    me = sub.add_parser("message", help="Emailurile trimise de noi (drafturi și trimise)")
    mes = me.add_subparsers(dest="action", required=True)
    x = mes.add_parser("add", help="Salvează un email (draft implicit)"); add_payload_args(x)
    x.add_argument("--force", action="store_true", help="Ignoră blocajele (deja contactat etc.)")
    x.add_argument("--ignore-lint", action="store_true", help="Ignoră erorile de lint (nu și em dash)")
    x = mes.add_parser("update"); x.add_argument("id", type=int); add_payload_args(x)
    x = mes.add_parser("sent", help="Marchează drafturi ca trimise")
    x.add_argument("ids", type=int, nargs="*"); x.add_argument("--all-drafts", action="store_true"); x.add_argument("--at")
    x = mes.add_parser("cancel", help="Anulează un draft"); x.add_argument("id", type=int)
    x = mes.add_parser("show"); x.add_argument("id", type=int)
    x = mes.add_parser("list")
    x.add_argument("--company", type=int); x.add_argument("--status"); x.add_argument("--direction", choices=["out", "in"])
    x.add_argument("--limit", type=int, default=50)
    x = mes.add_parser("thread", help="Conversația completă cu o firmă"); x.add_argument("company_id", type=int)

    x = sub.add_parser("inbound", help="Înregistrează un răspuns primit de la un lead"); add_payload_args(x)

    x = sub.add_parser("followups", help="Ce trebuie făcut: răspunsuri, follow-up-uri scadente, drafturi")
    x.add_argument("--days", type=int, default=0, help="Arată și ce urmează în următoarele N zile")

    x = sub.add_parser("stats", help="Statistici")
    x.add_argument("--since"); x.add_argument("--until")
    x.add_argument("--by", help="Listă separată prin virgulă: offering,sender,language,industry,country,size,month,week,seniority,search,status")

    su = sub.add_parser("suppress", help="Lista do-not-contact (emailuri / domenii)")
    sus = su.add_subparsers(dest="action", required=True)
    x = sus.add_parser("add"); x.add_argument("value"); x.add_argument("--reason")
    sus.add_parser("list")
    x = sus.add_parser("remove"); x.add_argument("value")

    cf = sub.add_parser("config", help="Setări (zile follow-up, chei API etc.)")
    cfs = cf.add_subparsers(dest="action", required=True)
    cfs.add_parser("list")
    x = cfs.add_parser("get"); x.add_argument("key")
    x = cfs.add_parser("set"); x.add_argument("key"); x.add_argument("value")
    x = cfs.add_parser("unset"); x.add_argument("key")

    x = sub.add_parser("export", help="Export CSV")
    x.add_argument("--what", default="all"); x.add_argument("--out-dir")
    x = sub.add_parser("backup", help="Copie de siguranță a bazei de date"); x.add_argument("--out")
    x = sub.add_parser("sql", help="Interogare SQL doar-citire (SELECT)"); x.add_argument("query")
    x = sub.add_parser("lint", help="Verifică un email (vezi email_lint.py)")
    add_payload_args(x); x.add_argument("--kind", default=None)
    return p


def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir, argv = resolve_data_dir(argv)
    _fmt, argv = extract_option(argv, "--format")
    args = build_parser().parse_args(argv)
    cmd = args.cmd
    action = getattr(args, "action", None)

    if cmd == "where":
        db = data_dir / "crm.db"
        return {"data_dir": str(data_dir), "db": str(db), "exists": db.exists(),
                "source": "--data-dir" if "--data-dir" in " ".join(sys.argv) else
                          ("COLD_EMAIL_HOME" if os.environ.get("COLD_EMAIL_HOME") else "default (~/.cold-email)")}
    if cmd == "schema":
        return {"fields": TABLE_FIELDS, "company_statuses": COMPANY_STATUSES,
                "inbound_classifications": {k: {"company_status": v[0], "sentiment": v[1], "needs_our_reply": v[2]}
                                            for k, v in INBOUND_CLASSES.items()},
                "message_kinds_out": MESSAGE_KINDS_OUT, "email_statuses": EMAIL_STATUSES,
                "profile_recommended_fields": PROFILE_RECOMMENDED,
                "note": "Câmpurile necunoscute sunt păstrate în 'extra' (JSON)."}
    if cmd == "sql":
        q = args.query.strip()
        if not re.match(r"^(select|with)\b", q, flags=re.I):
            raise CRMError("Doar interogări SELECT/WITH.")
        conn = connect(data_dir, readonly=True)
        cur = conn.execute(q)
        rows = [dict(r) for r in cur.fetchall()]
        res = {"rows": rows, "count": len(rows)}
        if rows:
            res["_text"] = table_text(rows, list(rows[0].keys()))
        return res
    if cmd == "lint":
        data = load_payload(args)
        return lint_email(data.get("subject"), data.get("body"), args.kind or data.get("kind") or "initial", data.get("language"))

    conn = connect(data_dir)

    if cmd == "init":
        return {"ok": True, "data_dir": str(data_dir), "db": str(data_dir / "crm.db")}
    if cmd == "overview":
        return overview(conn, data_dir)

    if cmd == "profile":
        if action == "show":
            return profile_get(conn)
        return profile_set(conn, load_payload(args), replace=(action == "replace"))

    if cmd == "sender":
        if action == "list":
            q = "SELECT * FROM senders" + ("" if args.all else " WHERE active = 1") + " ORDER BY is_default DESC, id"
            return {"senders": [row_to_dict(r) for r in conn.execute(q)]}
        if action == "show":
            return row_to_dict(require_row(conn, "senders", args.id, "Expeditorul"))
        if action == "add":
            return {"ok": True, "sender": sender_add(conn, load_payload(args))}
        if action == "update":
            data = load_payload(args)
            if data.get("email"):
                data["email"] = normalize_email(data["email"])
            r = update_row(conn, "senders", args.id, data)
            if data.get("is_default"):
                sender_make_default(conn, args.id)
            conn.commit()
            return {"ok": True, "sender": r}
        if action == "default":
            sender_make_default(conn, args.id); conn.commit()
            return {"ok": True, "default_sender": row_to_dict(get_row(conn, "senders", args.id))}
        if action == "remove":
            update_row(conn, "senders", args.id, {"active": 0, "is_default": 0}); conn.commit()
            return {"ok": True, "deactivated": args.id}

    if cmd == "offering":
        if action == "list":
            q = "SELECT * FROM offerings" + ("" if args.all else " WHERE active = 1") + " ORDER BY id"
            rows = [row_to_dict(r) for r in conn.execute(q)]
            return {"offerings": rows, "_text": table_text(rows, ["id", "kind", "name", "summary", "pricing"])}
        if action == "show":
            return row_to_dict(require_row(conn, "offerings", args.id, "Oferta"))
        if action == "add":
            return {"ok": True, "offering": offering_add(conn, load_payload(args))}
        if action == "update":
            r = update_row(conn, "offerings", args.id, load_payload(args)); conn.commit()
            return {"ok": True, "offering": r}
        if action == "remove":
            update_row(conn, "offerings", args.id, {"active": 0}); conn.commit()
            return {"ok": True, "deactivated": args.id}

    if cmd == "search":
        if action == "add":
            data = load_payload(args)
            if "criteria" not in data:
                data = {"criteria": data}
            sid = insert(conn, "searches", data); conn.commit()
            return {"ok": True, "search": row_to_dict(get_row(conn, "searches", sid))}
        if action == "list":
            rows = []
            for r in conn.execute("SELECT * FROM searches ORDER BY id DESC LIMIT ?", (args.limit,)):
                d = row_to_dict(r)
                d["companies"] = conn.execute("SELECT COUNT(*) c FROM companies WHERE search_id = ?", (r["id"],)).fetchone()["c"]
                rows.append(d)
            return {"searches": rows}
        if action == "show":
            d = row_to_dict(require_row(conn, "searches", args.id, "Căutarea"))
            d["companies"] = [company_summary(conn, row_to_dict(r)) for r in
                              conn.execute("SELECT * FROM companies WHERE search_id = ? ORDER BY id", (args.id,))]
            return d
        if action == "update":
            r = update_row(conn, "searches", args.id, load_payload(args)); conn.commit()
            return {"ok": True, "search": r}

    if cmd == "company":
        if action == "add":
            return company_add(conn, load_payload(args), allow_duplicate=args.allow_duplicate)
        if action == "import":
            items = load_payload(args)
            if isinstance(items, dict):
                items = items.get("companies", [])
            created, skipped, errors = [], [], []
            for it in items:
                try:
                    if args.search_id:
                        it.setdefault("search_id", args.search_id)
                    res = company_add(conn, it, allow_duplicate=args.allow_duplicate, commit=False)
                    if res.get("ok"):
                        created.append({"id": res["company"]["id"], "name": res["company"]["name"],
                                        "contacts": len(res["contacts"]), "suppressed": res["suppressed"]})
                    else:
                        skipped.append({"name": it.get("name"), "reason": res.get("error"), "existing": res.get("existing")})
                except CRMError as e:
                    errors.append({"name": it.get("name"), "error": str(e)})
            if args.search_id:
                n = conn.execute("SELECT COUNT(*) c FROM companies WHERE search_id = ?", (args.search_id,)).fetchone()["c"]
                conn.execute("UPDATE searches SET result_count = ?, updated_at = ? WHERE id = ?", (n, now(), args.search_id))
            conn.commit()
            return {"ok": not errors, "created": created, "skipped_duplicates": skipped, "errors": errors}
        if action == "update":
            data = prepare_company(load_payload(args))
            contacts = data.pop("contacts", None)
            if data.get("domain") or data.get("tax_id"):
                dups = [m for m in find_matches(conn, None, data.get("domain"), data.get("tax_id"), exclude_id=args.id) if m["strong"]]
                if dups:
                    return {"ok": False, "error": "Domeniul/CUI-ul aparține altei firme din baza de date.",
                            "existing": [company_summary(conn, m["company"]) for m in dups]}
            status = data.pop("status", None)
            r = update_row(conn, "companies", args.id, data)
            if status:
                set_company_status(conn, args.id, status, force=True)
            for c in contacts or []:
                c = dict(c); c["company_id"] = args.id
                contact_add(conn, c, commit=False)
            conn.commit()
            return {"ok": True, "company": row_to_dict(get_row(conn, "companies", args.id)) if status else r}
        if action == "show":
            return company_show(conn, args.id)
        if action in ("check", "find"):
            res = company_check(conn, args.name or args.q, args.domain, args.tax_id, args.email)
            if args.q and not res["matches"]:
                like = f"%{args.q}%"
                rows = conn.execute("SELECT * FROM companies WHERE name LIKE ? OR legal_name LIKE ? OR domain LIKE ? LIMIT 20",
                                    (like, like, like)).fetchall()
                res["matches"] = [dict(company_summary(conn, row_to_dict(r)), match_reasons=["text"], strong_match=False) for r in rows]
            return res
        if action == "list":
            q = "SELECT * FROM companies WHERE 1=1"
            params = []
            if args.status:
                q += " AND status = ?"; params.append(args.status)
            if args.country:
                q += " AND lower(country) = lower(?)"; params.append(args.country)
            if args.industry:
                q += " AND lower(industry) LIKE lower(?)"; params.append(f"%{args.industry}%")
            if args.search_id:
                q += " AND search_id = ?"; params.append(args.search_id)
            if args.q:
                q += " AND (name LIKE ? OR legal_name LIKE ? OR domain LIKE ? OR notes LIKE ?)"; params += [f"%{args.q}%"] * 4
            if args.uncontacted:
                q += " AND id NOT IN (SELECT company_id FROM messages WHERE direction = 'out' AND status IN ('sent','bounced'))"
            q += " ORDER BY id DESC LIMIT ?"; params.append(args.limit)
            rows = [company_summary(conn, row_to_dict(r)) for r in conn.execute(q, params)]
            return {"companies": rows, "count": len(rows),
                    "_text": table_text(rows, ["id", "name", "domain", "status", "country", "industry", "emails_sent", "replies", "last_sent_at"])}
        if action == "status":
            set_company_status(conn, args.id, args.status, note=args.note, force=True)
            if args.next_action is not None or args.next_action_at is not None:
                conn.execute("UPDATE companies SET next_action = ?, next_action_at = ? WHERE id = ?",
                             (args.next_action, parse_dt(args.next_action_at), args.id))
            conn.commit()
            return {"ok": True, "company": company_summary(conn, row_to_dict(get_row(conn, "companies", args.id)))}
        if action == "delete":
            c = require_row(conn, "companies", args.id, "Firma")
            if not args.yes:
                return {"ok": False, "error": "Confirmă cu --yes. Ștergerea elimină și contactele și mesajele firmei.",
                        "company": company_summary(conn, row_to_dict(c))}
            conn.execute("DELETE FROM companies WHERE id = ?", (args.id,)); conn.commit()
            return {"ok": True, "deleted": args.id}

    if cmd == "contact":
        if action == "add":
            return contact_add(conn, load_payload(args), allow_duplicate=args.allow_duplicate)
        if action == "update":
            data = load_payload(args)
            if data.get("email"):
                data["email"] = normalize_email(data["email"])
            if data.get("email_status") and data["email_status"] not in EMAIL_STATUSES:
                raise CRMError(f"email_status invalid. Valori: {', '.join(EMAIL_STATUSES)}")
            r = update_row(conn, "contacts", args.id, data); conn.commit()
            return {"ok": True, "contact": r}
        if action == "list":
            q = "SELECT ct.*, c.name AS company_name FROM contacts ct JOIN companies c ON c.id = ct.company_id WHERE 1=1"
            params = []
            if args.company:
                q += " AND ct.company_id = ?"; params.append(args.company)
            if args.q:
                q += " AND (ct.full_name LIKE ? OR ct.email LIKE ? OR ct.role LIKE ?)"; params += [f"%{args.q}%"] * 3
            q += " ORDER BY ct.id DESC LIMIT ?"; params.append(args.limit)
            rows = [row_to_dict(r) for r in conn.execute(q, params)]
            return {"contacts": rows, "_text": table_text(rows, ["id", "company_name", "full_name", "role", "email", "email_status"])}
        if action == "show":
            return row_to_dict(require_row(conn, "contacts", args.id, "Contactul"))
        if action == "remove":
            c = require_row(conn, "contacts", args.id, "Contactul")
            conn.execute("DELETE FROM contacts WHERE id = ?", (args.id,))
            log(conn, c["company_id"], "contact_removed", c["full_name"] or c["email"] or str(args.id))
            conn.commit()
            return {"ok": True, "removed": args.id}

    if cmd == "message":
        if action == "add":
            return message_add(conn, load_payload(args), force=args.force, ignore_lint=args.ignore_lint)
        if action == "update":
            data = load_payload(args)
            m = require_row(conn, "messages", args.id, "Mesajul")
            subj = data.get("subject", m["subject"])
            body = data.get("body", m["body"])
            if m["direction"] == "out" and (has_forbidden_dash(subj) or has_forbidden_dash(body)):
                return {"ok": False, "error": "Textul conține em dash / en dash. Rescrie fără ele."}
            if data.get("sent_at"):
                data["sent_at"] = parse_dt(data["sent_at"])
            r = update_row(conn, "messages", args.id, data); conn.commit()
            lint = lint_email(subj, body, m["kind"] if m["kind"] in ("initial", "follow_up", "reply") else "reply") if m["direction"] == "out" else None
            return {"ok": True, "message": r, "lint": lint}
        if action == "sent":
            ids = list(args.ids)
            if args.all_drafts:
                ids += [r["id"] for r in conn.execute("SELECT id FROM messages WHERE direction = 'out' AND status = 'draft' ORDER BY id")]
            if not ids:
                raise CRMError("Dă cel puțin un id sau --all-drafts.")
            return message_mark_sent(conn, ids, args.at)
        if action == "cancel":
            m = require_row(conn, "messages", args.id, "Mesajul")
            conn.execute("UPDATE messages SET status = 'cancelled', updated_at = ? WHERE id = ?", (now(), args.id))
            log(conn, m["company_id"], "draft_cancelled", m["subject"] or "", message_id=args.id)
            c = get_row(conn, "companies", m["company_id"])
            if c["status"] == "drafted" and not sent_sequence(conn, c["id"]):
                conn.execute("UPDATE companies SET status = 'new' WHERE id = ?", (c["id"],))
            conn.commit()
            return {"ok": True, "cancelled": args.id}
        if action == "show":
            return row_to_dict(require_row(conn, "messages", args.id, "Mesajul"))
        if action == "list":
            q = ("SELECT m.id, m.company_id, c.name AS company, m.direction, m.kind, m.step, m.status, m.subject, "
                 "m.language, m.classification, m.to_email, m.sent_at, m.received_at, m.created_at "
                 "FROM messages m JOIN companies c ON c.id = m.company_id WHERE 1=1")
            params = []
            if args.company:
                q += " AND m.company_id = ?"; params.append(args.company)
            if args.status:
                q += " AND m.status = ?"; params.append(args.status)
            if args.direction:
                q += " AND m.direction = ?"; params.append(args.direction)
            q += " ORDER BY m.id DESC LIMIT ?"; params.append(args.limit)
            rows = [dict(r) for r in conn.execute(q, params)]
            return {"messages": rows, "_text": table_text(rows, ["id", "company", "direction", "kind", "step", "status", "subject", "sent_at"])}
        if action == "thread":
            d = company_show(conn, args.company_id)
            return {"company": d["company"], "contacts": d["contacts"], "messages": d["messages"]}

    if cmd == "inbound":
        return inbound_add(conn, load_payload(args))

    if cmd == "followups":
        res = followups(conn, args.days)
        lines = []
        for title, key, cols in (("AȘTEAPTĂ RĂSPUNSUL NOSTRU", "needs_reply", ["company_id", "company", "classification", "days_waiting", "last_subject"]),
                                 ("FOLLOW-UP SCADENT", "follow_ups_due", ["company_id", "company", "next_step", "days_since_last", "due_at", "last_subject"]),
                                 ("URMEAZĂ", "upcoming", ["company_id", "company", "reason", "due_at"]),
                                 ("DRAFTURI NETRIMISE", "drafts_pending", ["company_id", "company", "draft_ids"])):
            lines.append(f"{title} ({len(res[key])})")
            lines.append(table_text(res[key], cols))
            lines.append("")
        res["_text"] = "\n".join(lines)
        return res

    if cmd == "stats":
        by = [b.strip() for b in args.by.split(",")] if args.by else []
        return compute_stats(conn, args.since, args.until, by)

    if cmd == "suppress":
        if action == "add":
            return {"ok": True, "suppressed": suppress_add(conn, args.value, args.reason)}
        if action == "list":
            return {"suppression": [dict(r) for r in conn.execute("SELECT * FROM suppression ORDER BY id DESC")]}
        if action == "remove":
            v = normalize_email(args.value) if "@" in args.value else normalize_domain(args.value)
            conn.execute("DELETE FROM suppression WHERE value = ?", (v,)); conn.commit()
            return {"ok": True, "removed": v, "note": "Contactele/firmele marcate do_not_contact rămân marcate; schimbă-le manual dacă e cazul."}

    if cmd == "config":
        if action == "list":
            return {"settings": {r["key"]: mask(r["key"], r["value"]) for r in conn.execute("SELECT key, value FROM settings ORDER BY key")}}
        if action == "get":
            return {"key": args.key, "value": mask(args.key, get_setting(conn, args.key))}
        if action == "set":
            conn.execute("INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                         (args.key, args.value, now()))
            conn.commit()
            return {"ok": True, "key": args.key, "value": mask(args.key, args.value)}
        if action == "unset":
            conn.execute("DELETE FROM settings WHERE key = ?", (args.key,)); conn.commit()
            return {"ok": True, "removed": args.key}

    if cmd == "export":
        return export_csv(conn, data_dir, args.what, args.out_dir)
    if cmd == "backup":
        return backup(conn, data_dir, args.out)

    raise CRMError(f"Comandă necunoscută: {cmd} {action or ''}")


def main():
    fmt, _ = extract_option(sys.argv[1:], "--format")
    fmt = fmt if fmt in ("json", "text") else "json"
    try:
        res = run()
        out(res, fmt)
        if isinstance(res, dict) and res.get("ok") is False:
            sys.exit(1)
    except CRMError as e:
        out({"ok": False, "error": str(e)})
        sys.exit(1)
    except (json.JSONDecodeError, ValueError) as e:
        out({"ok": False, "error": f"Date invalide: {e}"})
        sys.exit(1)
    except sqlite3.Error as e:
        out({"ok": False, "error": f"Eroare SQLite: {e}"})
        sys.exit(1)


if __name__ == "__main__":
    main()
