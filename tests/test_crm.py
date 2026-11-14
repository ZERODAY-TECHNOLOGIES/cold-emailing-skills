"""Teste end-to-end pentru crm.py, email_lint.py și enrich.py (offline). Rulare: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "cold-emailing" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from email_lint import lint_email  # noqa: E402

GOOD_BODY = ("Bună ziua, domnule Ionescu,\n\nAm văzut că ați lansat plata în rate pe alfa.ro. "
             "Fluxurile noi de plată sunt de obicei locul unde apar probleme de securitate.\n\n"
             "Facem teste de penetrare pentru magazine de mărimea dumneavoastră.\n\n"
             "Vă trimit un exemplu de raport?\n\nDacă nu e relevant, spuneți-mi și nu vă mai scriu.\n\nAndrei")


class CRMTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, COLD_EMAIL_HOME=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def crm(self, *args, payload=None, ok=True):
        cmd = [sys.executable, str(SCRIPTS / "crm.py"), *args]
        if payload is not None:
            cmd += ["--stdin"]
        p = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                           capture_output=True, text=True, env=self.env)
        res = json.loads(p.stdout)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return res

    def seed(self):
        self.crm("profile", "set", payload={"name": "Test SRL", "website": "test.ro"})
        self.crm("sender", "add", payload={"full_name": "Andrei Pop", "email": "andrei@test.ro"})
        self.crm("offering", "add", payload={"name": "Pentest"})
        r = self.crm("company", "add", payload={"name": "Alfa SRL", "website": "https://www.alfa.ro/x", "tax_id": "RO123",
                                                 "contacts": [{"full_name": "Ion Ionescu", "email": "Ion@Alfa.ro"}]})
        return r["company"]["id"]

    def test_persistence_and_dedup(self):
        cid = self.seed()
        self.assertEqual(self.crm("overview")["companies_total"], 1)
        dup = self.crm("company", "add", payload={"name": "Alfa", "domain": "alfa.ro"}, ok=False)
        self.assertTrue(dup["duplicate"])
        chk = self.crm("company", "check", "--tax-id", "123")
        self.assertTrue(chk["exists"])
        self.assertEqual(chk["matches"][0]["id"], cid)

    def test_em_dash_always_rejected(self):
        cid = self.seed()
        r = self.crm("message", "add", "--ignore-lint", "--force",
                     payload={"company_id": cid, "subject": "x", "body": "Salut — test"}, ok=False)
        self.assertFalse(r["ok"])
        r = self.crm("message", "add", payload={"company_id": cid, "subject": "x", "body": "Salut – test"}, ok=False)
        self.assertFalse(r["ok"])

    def test_full_cycle(self):
        cid = self.seed()
        r = self.crm("message", "add", payload={"company_id": cid, "offering_id": 1, "language": "ro",
                                                "subject": "plata în rate pe alfa.ro", "body": GOOD_BODY})
        mid = r["message"]["id"]
        self.assertEqual(r["message"]["to_email"], "ion@alfa.ro")
        self.crm("message", "sent", str(mid), "--at", "2026-01-01 10:00")
        fu = self.crm("followups")
        self.assertEqual(len(fu["follow_ups_due"]), 1)
        blocked = self.crm("message", "add", payload={"company_id": cid, "subject": "a", "body": GOOD_BODY}, ok=False)
        self.assertTrue(blocked.get("blocked"))
        inc = self.crm("inbound", payload={"from_email": "ion@alfa.ro", "classification": "interested",
                                            "body": "Da", "received_at": "2026-01-03 10:00"})
        self.assertEqual(inc["company"]["status"], "interested")
        fu = self.crm("followups")
        self.assertEqual(len(fu["needs_reply"]), 1)
        st = self.crm("stats", "--by", "offering")
        self.assertEqual(st["funnel"]["companies_contacted"], 1)
        self.assertEqual(st["funnel"]["reply_rate_pct"], 100.0)
        self.assertEqual(st["funnel"]["avg_days_to_reply"], 2.0)
        self.assertEqual(st["breakdowns"]["offering"][0]["offering"], "Pentest")

    def test_unsubscribe_suppresses(self):
        cid = self.seed()
        self.crm("message", "add", payload={"company_id": cid, "subject": "s", "body": GOOD_BODY, "status": "sent"})
        self.crm("inbound", payload={"company_id": cid, "from_email": "ion@alfa.ro", "classification": "unsubscribe", "body": "stop"})
        self.assertTrue(self.crm("company", "check", "--email", "ion@alfa.ro")["blocked"])
        r = self.crm("message", "add", payload={"company_id": cid, "kind": "follow_up", "subject": "s", "body": GOOD_BODY}, ok=False)
        self.assertTrue(r.get("blocked"))

    def test_data_dir_flag_anywhere(self):
        other = Path(self.tmp.name) / "other"
        self.crm("init", "--data-dir", str(other))
        self.assertTrue((other / "crm.db").exists())


class LintTest(unittest.TestCase):
    def test_good_email(self):
        r = lint_email("plata în rate pe alfa.ro", GOOD_BODY, "initial")
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["score"], 85)

    def test_bad_email(self):
        r = lint_email("OFERTĂ GRATUITĂ!!", "Mă numesc Andrei. Sper că acest email vă găsește bine. [Nume], soluții inovatoare — 100% garantat!!", "initial")
        codes = {e["code"] for e in r["errors"]} | {w["code"] for w in r["warnings"]}
        self.assertFalse(r["ok"])
        for c in ("forbidden_dash", "placeholder", "cliche", "spam_words", "self_opening"):
            self.assertIn(c, codes)


class EnrichTest(unittest.TestCase):
    def test_guess_patterns_strip_diacritics(self):
        from enrich import guess_emails, mx_lookup  # noqa: F401
        import enrich
        enrich.mx_lookup = lambda d: {"domain": d, "accepts_mail": True, "mx": []}
        r = enrich.guess_emails("https://www.Firma.ro/", "Ștefan", "Țurcanu")
        self.assertIn("stefan.turcanu@firma.ro", r["candidates"])
        self.assertEqual(r["email_status"], "guessed")


if __name__ == "__main__":
    unittest.main()
