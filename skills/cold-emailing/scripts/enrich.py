#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py - găsire și verificare de emailuri / persoane de contact (opțional, prin API-uri).

Chei API (oricare variantă):
  - variabile de mediu: HUNTER_API_KEY, APOLLO_API_KEY
  - setări persistente: python3 crm.py config set hunter_api_key XXX
                        python3 crm.py config set apollo_api_key XXX

Comenzi:
  keys                                   ce chei sunt configurate
  mx --domain firma.ro                   verifică dacă domeniul primește email (MX prin DNS-over-HTTPS)
  guess --domain firma.ro --first Ion --last Popescu [--pattern "{first}.{last}"]
                                         generează adrese probabile (fără API); marcate "guessed"
  hunter-domain --domain firma.ro [--limit 10] [--type personal] [--seniority senior,executive] [--department executive,it]
  hunter-find --domain firma.ro --first Ion --last Popescu
  hunter-verify --email ion@firma.ro
  apollo-people --domains a.ro,b.ro [--titles "CEO,Founder"] [--seniorities owner,founder,c_suite] [--per-page 10]
  apollo-match --first Ion --last Popescu --domain firma.ro       (consumă credite Apollo)
  apollo-orgs [--keywords "software"] [--locations "Romania"] [--employees "11,50"] [--per-page 25]

Toate comenzile afișează JSON. Rezultatele trebuie salvate apoi cu crm.py (company add / contact add).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from crm import extract_option, resolve_data_dir  # noqa: E402

TIMEOUT = 25
UA = "cold-emailing-skill/1.0"


class EnrichError(Exception):
    pass


# --------------------------------------------------------------------------------------

def get_key(data_dir: Path, name: str) -> str | None:
    env = os.environ.get(name.upper())
    if env:
        return env
    db = data_dir / "crm.db"
    if db.exists():
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            r = conn.execute("SELECT value FROM settings WHERE key = ?", (name.lower(),)).fetchone()
            conn.close()
            if r and r[0]:
                return r[0]
        except sqlite3.Error:
            pass
    return None


def http(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"User-Agent": UA, "Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        raise EnrichError(f"HTTP {e.code} de la {urllib.parse.urlsplit(url).netloc}: {detail}")
    except urllib.error.URLError as e:
        raise EnrichError(f"Nu am putut contacta {urllib.parse.urlsplit(url).netloc}: {e.reason}")


def ascii_slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z]", "", s)


def norm_domain(v: str) -> str:
    v = (v or "").strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = re.split(r"[/?#:]", v)[0]
    return v[4:] if v.startswith("www.") else v


# --------------------------------------------------------------------------------------
# Fără API
# --------------------------------------------------------------------------------------

def mx_lookup(domain: str) -> dict:
    domain = norm_domain(domain)
    url = "https://dns.google/resolve?" + urllib.parse.urlencode({"name": domain, "type": "MX"})
    try:
        res = http("GET", url)
    except EnrichError:
        url = "https://cloudflare-dns.com/dns-query?" + urllib.parse.urlencode({"name": domain, "type": "MX"})
        res = http("GET", url, headers={"Accept": "application/dns-json"})
    answers = [a.get("data") for a in res.get("Answer", []) if a.get("type") == 15]
    mx = sorted(answers, key=lambda x: int(x.split()[0]) if x and x.split()[0].isdigit() else 99)
    provider = None
    joined = " ".join(mx).lower()
    for key, name in (("google", "Google Workspace"), ("outlook", "Microsoft 365"), ("protection.outlook", "Microsoft 365"),
                      ("zoho", "Zoho"), ("mailgun", "Mailgun"), ("secureserver", "GoDaddy"), ("ovh", "OVH"),
                      ("hostinger", "Hostinger"), ("mimecast", "Mimecast"), ("pphosted", "Proofpoint")):
        if key in joined:
            provider = name
            break
    return {"domain": domain, "accepts_mail": bool(mx), "mx": mx, "provider_guess": provider}


PATTERNS = [
    "{first}", "{first}.{last}", "{f}{last}", "{first}{last}", "{f}.{last}", "{last}", "{first}_{last}",
    "{last}.{first}", "{first}-{last}", "{first}{l}", "{last}{f}", "{f}{l}",
]


def guess_emails(domain: str, first: str, last: str, pattern: str | None = None) -> dict:
    domain = norm_domain(domain)
    f_parts = [ascii_slug(p) for p in re.split(r"[\s\-]+", first or "") if ascii_slug(p)]
    l_parts = [ascii_slug(p) for p in re.split(r"[\s\-]+", last or "") if ascii_slug(p)]
    if not f_parts:
        raise EnrichError("Lipsește prenumele.")
    first_s = f_parts[0]
    last_s = l_parts[0] if l_parts else ""
    vals = {"first": first_s, "last": last_s, "f": first_s[:1], "l": last_s[:1]}
    pats = [pattern] if pattern else PATTERNS
    out = []
    for p in pats:
        if not last_s and ("{last}" in p or "{l}" in p):
            continue
        local = p.format(**vals)
        e = f"{local}@{domain}"
        if e not in out:
            out.append(e)
    # variante pentru nume compuse (ex. "Ana-Maria", "Popescu Ionescu")
    if len(f_parts) > 1 and last_s:
        out.append(f"{''.join(f_parts)}.{last_s}@{domain}")
    if len(l_parts) > 1:
        out.append(f"{first_s}.{l_parts[-1]}@{domain}")
    mx = None
    try:
        mx = mx_lookup(domain)
    except EnrichError as e:
        mx = {"error": str(e)}
    return {
        "domain": domain, "candidates": out, "email_status": "guessed", "mx": mx,
        "note": "Adrese ghicite, NEVERIFICATE. Primul candidat folosește pattern-ul dat sau cel mai comun. "
                "Dacă ai găsit pe site o adresă reală a altei persoane din firmă, deduce pattern-ul din ea și "
                "rulează din nou cu --pattern. Salvează contactul cu email_status='guessed'.",
    }


# --------------------------------------------------------------------------------------
# Hunter.io
# --------------------------------------------------------------------------------------

HUNTER = "https://api.hunter.io/v2"


def hunter_domain(key, domain, limit=10, type_=None, seniority=None, department=None) -> dict:
    params = {"domain": norm_domain(domain), "limit": limit, "api_key": key}
    if type_:
        params["type"] = type_
    if seniority:
        params["seniority"] = seniority
    if department:
        params["department"] = department
    res = http("GET", f"{HUNTER}/domain-search?" + urllib.parse.urlencode(params)).get("data", {})
    people = []
    for e in res.get("emails", []):
        people.append({
            "full_name": " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x) or None,
            "first_name": e.get("first_name"), "last_name": e.get("last_name"),
            "role": e.get("position"), "department": e.get("department"), "seniority": e.get("seniority"),
            "email": e.get("value"), "email_type": e.get("type"), "email_confidence": e.get("confidence"),
            "email_status": "verified" if (e.get("verification") or {}).get("status") == "valid" else "found",
            "email_source": "hunter", "linkedin": e.get("linkedin"), "phone": e.get("phone_number"),
            "sources": [s.get("uri") for s in (e.get("sources") or [])][:3],
        })
    return {
        "domain": res.get("domain"), "organization": res.get("organization"), "pattern": res.get("pattern"),
        "accept_all": res.get("accept_all"), "country": res.get("country"), "industry": res.get("industry"),
        "headcount": res.get("headcount"), "linkedin": res.get("linkedin"), "people": people,
    }


def hunter_find(key, domain, first, last) -> dict:
    params = {"domain": norm_domain(domain), "first_name": first, "last_name": last, "api_key": key}
    d = http("GET", f"{HUNTER}/email-finder?" + urllib.parse.urlencode(params)).get("data", {})
    status = (d.get("verification") or {}).get("status")
    return {
        "email": d.get("email"), "email_confidence": d.get("score"),
        "email_status": "verified" if status == "valid" else ("found" if d.get("email") else "unknown"),
        "verification": status, "role": d.get("position"), "linkedin": d.get("linkedin_url"),
        "email_source": "hunter", "sources": [s.get("uri") for s in (d.get("sources") or [])][:3],
    }


def hunter_verify(key, email) -> dict:
    params = {"email": email, "api_key": key}
    d = http("GET", f"{HUNTER}/email-verifier?" + urllib.parse.urlencode(params)).get("data", {})
    status = d.get("status")  # valid | invalid | accept_all | webmail | disposable | unknown
    mapped = {"valid": "verified", "invalid": "invalid", "accept_all": "catch_all"}.get(status, "unknown")
    return {"email": d.get("email"), "hunter_status": status, "result": d.get("result"), "score": d.get("score"),
            "email_status": mapped, "mx_records": d.get("mx_records"), "smtp_check": d.get("smtp_check")}


# --------------------------------------------------------------------------------------
# Apollo.io
# --------------------------------------------------------------------------------------

APOLLO = "https://api.apollo.io/api/v1"


def apollo_headers(key):
    return {"x-api-key": key, "Cache-Control": "no-cache"}


def csv_list(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def apollo_people(key, domains=None, titles=None, seniorities=None, locations=None, per_page=10, page=1) -> dict:
    body = {"per_page": per_page, "page": page}
    if domains:
        body["q_organization_domains_list"] = [norm_domain(d) for d in domains]
    if titles:
        body["person_titles"] = titles
    if seniorities:
        body["person_seniorities"] = seniorities
    if locations:
        body["person_locations"] = locations
    res = http("POST", f"{APOLLO}/mixed_people/api_search", headers=apollo_headers(key), body=body)
    people = []
    for p in res.get("people", []) or []:
        org = p.get("organization") or {}
        people.append({
            "apollo_id": p.get("id"), "first_name": p.get("first_name"),
            "last_name": p.get("last_name") or p.get("last_name_obfuscated"),
            "full_name": p.get("name"), "role": p.get("title"), "seniority": p.get("seniority"),
            "linkedin": p.get("linkedin_url"), "has_email": p.get("has_email"),
            "company": org.get("name"), "company_domain": org.get("primary_domain") or org.get("website_url"),
        })
    return {"total": (res.get("pagination") or {}).get("total_entries") or res.get("total_entries"),
            "people": people,
            "note": "Căutarea Apollo nu returnează emailuri. Folosește apollo-match (consumă credite) sau hunter-find / guess."}


def apollo_match(key, first=None, last=None, domain=None, apollo_id=None, linkedin=None) -> dict:
    body = {"reveal_personal_emails": False}
    if apollo_id:
        body["id"] = apollo_id
    if first:
        body["first_name"] = first
    if last:
        body["last_name"] = last
    if domain:
        body["domain"] = norm_domain(domain)
    if linkedin:
        body["linkedin_url"] = linkedin
    res = http("POST", f"{APOLLO}/people/match", headers=apollo_headers(key), body=body)
    p = res.get("person") or {}
    st = p.get("email_status")
    return {
        "full_name": p.get("name"), "first_name": p.get("first_name"), "last_name": p.get("last_name"),
        "role": p.get("title"), "seniority": p.get("seniority"), "linkedin": p.get("linkedin_url"),
        "email": p.get("email"), "apollo_email_status": st,
        "email_status": "verified" if st == "verified" else ("found" if p.get("email") else "unknown"),
        "email_source": "apollo", "company": (p.get("organization") or {}).get("name"),
    }


def apollo_orgs(key, keywords=None, locations=None, employees=None, per_page=25, page=1) -> dict:
    body = {"per_page": per_page, "page": page}
    if keywords:
        body["q_organization_keyword_tags"] = keywords
    if locations:
        body["organization_locations"] = locations
    if employees:
        body["organization_num_employees_ranges"] = employees
    res = http("POST", f"{APOLLO}/mixed_companies/search", headers=apollo_headers(key), body=body)
    orgs = []
    for o in (res.get("organizations") or []) + (res.get("accounts") or []):
        orgs.append({
            "name": o.get("name"), "website": o.get("website_url"), "domain": o.get("primary_domain"),
            "linkedin": o.get("linkedin_url"), "founded_year": o.get("founded_year"),
            "employees_count": o.get("estimated_num_employees"), "industry": o.get("industry"),
            "city": o.get("city"), "country": o.get("country"), "phone": (o.get("primary_phone") or {}).get("number"),
            "source": "apollo",
        })
    return {"total": (res.get("pagination") or {}).get("total_entries"), "organizations": orgs}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir, argv = resolve_data_dir(argv)
    _, argv = extract_option(argv, "--format")
    p = argparse.ArgumentParser(prog="enrich.py", description="Găsire/verificare emailuri și persoane de contact.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keys")
    x = sub.add_parser("mx"); x.add_argument("--domain", required=True)
    x = sub.add_parser("guess"); x.add_argument("--domain", required=True); x.add_argument("--first", required=True)
    x.add_argument("--last", default=""); x.add_argument("--pattern", help='ex. "{first}.{last}", "{f}{last}"')
    x = sub.add_parser("hunter-domain"); x.add_argument("--domain", required=True); x.add_argument("--limit", type=int, default=10)
    x.add_argument("--type", choices=["personal", "generic"]); x.add_argument("--seniority"); x.add_argument("--department")
    x = sub.add_parser("hunter-find"); x.add_argument("--domain", required=True); x.add_argument("--first", required=True); x.add_argument("--last", required=True)
    x = sub.add_parser("hunter-verify"); x.add_argument("--email", required=True)
    x = sub.add_parser("apollo-people"); x.add_argument("--domains"); x.add_argument("--titles"); x.add_argument("--seniorities")
    x.add_argument("--locations"); x.add_argument("--per-page", type=int, default=10); x.add_argument("--page", type=int, default=1)
    x = sub.add_parser("apollo-match"); x.add_argument("--first"); x.add_argument("--last"); x.add_argument("--domain")
    x.add_argument("--apollo-id"); x.add_argument("--linkedin")
    x = sub.add_parser("apollo-orgs"); x.add_argument("--keywords"); x.add_argument("--locations")
    x.add_argument("--employees", help='intervale separate prin ";" ex. "11,50;51,200"')
    x.add_argument("--per-page", type=int, default=25); x.add_argument("--page", type=int, default=1)
    a = p.parse_args(argv)

    def need(name):
        k = get_key(data_dir, name)
        if not k:
            raise EnrichError(f"Lipsește cheia {name.upper()}. Setează variabila de mediu sau "
                              f"`python3 crm.py config set {name.lower()} CHEIA`. Fără cheie, folosește căutarea web + `guess`.")
        return k

    if a.cmd == "keys":
        res = {"hunter_api_key": bool(get_key(data_dir, "hunter_api_key")),
               "apollo_api_key": bool(get_key(data_dir, "apollo_api_key"))}
    elif a.cmd == "mx":
        res = mx_lookup(a.domain)
    elif a.cmd == "guess":
        res = guess_emails(a.domain, a.first, a.last, a.pattern)
    elif a.cmd == "hunter-domain":
        res = hunter_domain(need("hunter_api_key"), a.domain, a.limit, a.type, a.seniority, a.department)
    elif a.cmd == "hunter-find":
        res = hunter_find(need("hunter_api_key"), a.domain, a.first, a.last)
    elif a.cmd == "hunter-verify":
        res = hunter_verify(need("hunter_api_key"), a.email)
    elif a.cmd == "apollo-people":
        res = apollo_people(need("apollo_api_key"), csv_list(a.domains), csv_list(a.titles), csv_list(a.seniorities),
                            csv_list(a.locations), a.per_page, a.page)
    elif a.cmd == "apollo-match":
        res = apollo_match(need("apollo_api_key"), a.first, a.last, a.domain, a.apollo_id, a.linkedin)
    elif a.cmd == "apollo-orgs":
        ranges = [r.strip() for r in (a.employees or "").split(";") if r.strip()]
        res = apollo_orgs(need("apollo_api_key"), csv_list(a.keywords), csv_list(a.locations), ranges, a.per_page, a.page)
    else:
        raise EnrichError("Comandă necunoscută")
    return res


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2))
    except EnrichError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)
