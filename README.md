# Cold Emailing: skill pentru Claude

O aplicație completă de cold emailing B2B, sub formă de skill pentru **Claude Code** și **Claude Desktop**. Claude devine asistentul tău de prospectare: caută firme după criteriile tale, găsește persoanele de contact și emailurile lor, scrie emailuri personalizate cu text natural (fără em dash), urmărește răspunsurile, propune follow-up-uri și îți arată statistici. Totul e memorat local, de la o sesiune la alta.

## Ce face

| Funcție | Detalii |
|---|---|
| **Memorie persistentă** | Bază SQLite locală (`~/.cold-email/crm.db`): profilul firmei tale, servicii/produse, expeditori, firme țintă, contacte, toate emailurile trimise și primite, istoric de activitate |
| **Profilul firmei** | Date de identificare (CUI, Reg. Com., adresă), descriere, propunere de valoare, diferențiatori, studii de caz. Le poate extrage din site-ul tău |
| **Servicii și produse** | Fiecare cu beneficii, client ideal, probleme rezolvate, dovezi, preț, CTA |
| **Expeditori** | Nume, funcție, email, telefon, semnătură, ton |
| **Căutare de firme** | Te întreabă domeniul, țara, mărimea, vechimea, semnalele, rolurile căutate; caută pe web (registre, directoare, LinkedIn, Google Maps) și, opțional, prin Apollo |
| **Persoane de contact și emailuri** | Din site, LinkedIn, registre; emailuri publice, deduse din pattern, sau prin Hunter.io / Apollo (opțional). Fiecare email are status onest: verificat, găsit, ghicit |
| **Deduplicare** | După domeniu, CUI, nume normalizat și email. Nu contactezi aceeași firmă de două ori din greșeală |
| **Emailuri personalizate** | Întreabă limba și serviciul prezentat înainte de fiecare email. Verificare automată: em dash/en dash blocate, clișee AI, cuvinte spam, lungime, CTA-uri multiple, opt-out |
| **Răspunsuri și follow-up** | Lipești răspunsul primit, Claude îl clasifică (interesat, întrebare, obiecție, recomandare, „nu acum”, refuz, dezabonare, out-of-office, bounce), actualizează statusul și redactează răspunsul potrivit |
| **Secvențe** | Follow-up automat programat (implicit 2, la 4 zile), cu listă de ce e scadent |
| **Statistici** | Rată de răspuns, rată pozitivă, întâlniri, bounce, dezabonări, timp până la răspuns, la ce pas vin răspunsurile, defalcat pe ofertă, limbă, industrie, țară, mărime, lună, expeditor |
| **Do-not-contact** | Listă de suprimare pentru emailuri și domenii; dezabonările se aplică automat |
| **Export și backup** | CSV pentru Excel / Google Sheets și copii ale bazei de date |

Skill-ul **nu trimite** emailuri. Le redactează, tu le trimiți din clientul tău de email, apoi îi spui lui Claude că le-ai trimis.

## Instalare

Cerință: Python 3.9+ (doar biblioteca standard, fără pachete de instalat).

### Claude Code (recomandat: memoria e persistentă automat)

Varianta 1, ca plugin din acest repository:

```
/plugin marketplace add zeroday-technologies/cold-emailing-skills
```

```
/plugin install cold-emailing@zeroday-cold-emailing
```

Varianta 2, manual, ca skill personal:

```bash
git clone https://github.com/zeroday-technologies/cold-emailing-skills.git
```

```bash
mkdir -p ~/.claude/skills && cp -r cold-emailing-skills/skills/cold-emailing ~/.claude/skills/
```

Datele stau în `~/.cold-email/`. Pentru altă locație, setează variabila de mediu `COLD_EMAIL_HOME`.

### Claude Desktop

1. Construiește arhiva (sau descarc-o, dacă e publicată la Releases):

   ```bash
   python3 tools/build_zip.py
   ```

   Rezultat: `dist/cold-emailing.zip`.
2. În Claude Desktop: **Settings**, secțiunea **Skills** (sub Capabilities), încarcă `cold-emailing.zip`. Code execution trebuie să fie activat.
3. **Pentru memorie persistentă folosește modul Cowork cu un folder selectat** de pe calculatorul tău (de exemplu `Documente/ColdEmail`). Claude va păstra baza de date în `cold-email-data/` din acel folder.

> Important: în chat-ul obișnuit (fără folder local), mediul de execuție se șterge la finalul conversației, deci memoria nu rezistă. Skill-ul te avertizează și îți poate da baza de date ca fișier de descărcat (`backup`), pe care o reîncarci data viitoare.

## Chei API opționale

Fără chei, skill-ul caută pe web și deduce emailurile din pattern-uri (marcate ca „ghicite”). Cu chei, găsește și verifică emailurile mai precis:

| Serviciu | Ce aduce | Configurare |
|---|---|---|
| [Hunter.io](https://hunter.io) | Emailuri pe domeniu, găsire după nume, verificare | `HUNTER_API_KEY` sau spune-i lui Claude „setează cheia Hunter” |
| [Apollo.io](https://apollo.io) | Căutare de firme și persoane, îmbogățire | `APOLLO_API_KEY` sau „setează cheia Apollo” |

Cheile se salvează local, în baza de date (`crm.py config set hunter_api_key ...`), și apar mascate.

## Cum îl folosești

Exemple de cereri către Claude:

- „Configurează-mi skill-ul de cold emailing. Site-ul nostru e exemplu.ro.”
- „Adaugă un serviciu nou: audit SEO pentru magazine online, de la 800 EUR.”
- „Găsește-mi 15 firme de logistică din Timișoara, 20-100 de angajați, înființate înainte de 2018. Caut directorul de operațiuni.”
- „Scrie emailuri pentru firmele din ultima căutare cu scor 4 sau 5.”
- „Le-am trimis pe toate.”
- „Mi-a răspuns cineva de la Moda Exemplu: [textul răspunsului]”
- „Ce follow-up-uri am de trimis azi?”
- „Arată-mi statisticile pe ultima lună, pe ofertă și pe limbă.”
- „Pe cine am contactat din industria auto și ce le-am scris?”
- „Fă-mi un export Excel cu toate lead-urile.”

## Structura

```
.claude-plugin/              manifest plugin + marketplace (Claude Code)
skills/cold-emailing/
  SKILL.md                   instrucțiunile principale ale skill-ului
  references/
    onboarding.md            profil firmă, expeditori, oferte, preferințe
    lead-search.md           surse de firme, contacte, emailuri, GDPR
    email-writing.md         reguli de scriere, stil umanizat, exemple RO/EN
    replies-followups.md     clasificarea răspunsurilor și follow-up
  scripts/
    crm.py                   baza de date: CRUD, deduplicare, follow-up, statistici, export
    email_lint.py            verificarea emailurilor (em dash, clișee, spam, lungime)
    enrich.py                Hunter, Apollo, pattern-uri de email, verificare MX
tools/build_zip.py           construiește arhiva pentru Claude Desktop
tests/test_crm.py            teste end-to-end
```

## Datele tale

- Baza de date e doar pe calculatorul tău (sau în folderul ales în Cowork). Nimic nu e trimis în altă parte, cu excepția interogărilor către Hunter/Apollo/DNS când le folosești.
- Poți deschide `crm.db` cu orice client SQLite (ex. DB Browser for SQLite) sau poți exporta în CSV.
- Backup: „fă un backup” sau `python3 skills/cold-emailing/scripts/crm.py backup`. Copiile ajung în `~/.cold-email/backups/`.
- Pentru a muta datele pe alt calculator, copiezi folderul `~/.cold-email/`.

## Conformitate

Cold emailingul B2B în UE trebuie să respecte GDPR și regulile locale privind comunicările comerciale (care diferă de la o țară la alta). Skill-ul ajută: păstrează sursa fiecărui contact, include o formulă de opt-out în emailuri și suprimă automat pe cei care cer să nu mai fie contactați. Responsabilitatea pentru campanie rămâne a ta.

## Dezvoltare

```bash
python3 -m unittest discover tests -v
```

```bash
python3 skills/cold-emailing/scripts/crm.py --help
```
