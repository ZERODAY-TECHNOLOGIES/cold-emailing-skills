# Căutarea firmelor, a persoanelor de contact și a emailurilor

## 1. Interviul de criterii

Pune toate întrebările într-un singur mesaj, cu valori implicite propuse, ca utilizatorul să poată răspunde scurt („da, dar doar Cluj”):

| Criteriu | Exemple / implicit |
|---|---|
| Domeniu de activitate | „magazine online de fashion”, „clinici stomatologice”, „firme de construcții”; în România poți filtra și după cod CAEN |
| Țară, regiune, oraș | implicit țara firmei utilizatorului |
| Mărime | nr. angajați (1-9 / 10-49 / 50-249 / 250+) sau cifră de afaceri |
| Vechime | ex. „înființate înainte de 2020” sau „startup-uri sub 3 ani” |
| Tip clienți | B2B / B2C / ambele |
| Semnale | angajează pe un anumit rol, a primit finanțare, a lansat ceva recent, folosește o anumită tehnologie, are site vechi etc. |
| Excluderi | concurenți, clienți existenți, firme de stat, anumite orașe |
| Roluri căutate | CEO/fondator, CTO, director marketing, HR, achiziții etc. Implicit: decidentul cel mai probabil pentru oferta aleasă |
| Câte firme | implicit 10 pe lot |
| Oferta vizată | din `offering list`; ajută la scorul de potrivire și la alegerea rolului |

Mărimi standard UE: micro sub 10 angajați, mică 10-49, medie 50-249, mare 250+. Salvează `employees_count` ca număr când îl știi (statisticile pe mărime îl folosesc), altfel `employees` ca text (ex. „11-50” de pe LinkedIn).

Salvează criteriile:

```bash
python3 "$SKILL_DIR/scripts/crm.py" search add --json '{"criteria": {"industry": "e-commerce fashion", "country": "Romania", "city": "Cluj-Napoca", "employees": "10-49", "founded_before": 2021, "roles": ["fondator", "CEO", "marketing"], "offering_id": 1, "count": 10}, "summary": "Fashion online Cluj, 10-49 ang."}'
```

## 2. Surse de firme

Folosește căutarea web și citirea paginilor. Notează mereu URL-urile surselor în `source_urls`.

**Pornește de la liste filtrate, nu de la căutări generale.** Căutările de tipul „distribuitor Cluj B2B” dau rezultate amestecate și consumă mult timp. Mai eficient: identifică 2-5 coduri CAEN (sau codurile NACE echivalente în alte țări) potrivite domeniului. Deschide apoi listele de firme dintr-un registru filtrate după județ/regiune și cod, sortate după numărul de angajați (ex. pe topfirme.com: `/judet/<judet>/caen/<cod>/numar-angajati/`). Din ele alegi candidații care se încadrează la mărime și vechime și abia apoi le verifici site-ul. Țintește cam 2-3 candidați verificați pentru fiecare firmă cerută și oprește-te când ai numărul cerut. Unele registre blochează accesul automat; dacă unul refuză, treci la altul în loc să insiști.

### România
- **listafirme.ro, termene.ro, risco.ro, topfirme.com**: cifră de afaceri, nr. angajați, an înființare, CAEN, administratori/asociați (unele date doar cu cont).
- **mfinante.gov.ro** (informații fiscale și bilanțuri după CUI) și **API-ul public ANAF** pentru CUI: denumire, adresă, data înregistrării, stare.
- **data.gov.ro**: seturi de date ONRC cu firmele înregistrate (pentru filtrare masivă după CAEN și județ).
- Asociații de profil (ex. ARMO pentru magazine online, ANIS pentru software), camere de comerț, liste de expozanți de la târguri.

### Alte țări
- **Registre:** North Data (DE, AT, CH, NL, PL și altele), OpenCorporates, Companies House (UK), Pappers / Societe.com (FR), KVK (NL), Unternehmensregister (DE), registrele naționale în general.
- **Directoare:** Europages, Kompass, Clutch / GoodFirms (agenții, IT), G2 / Capterra (SaaS), Crunchbase / Dealroom (startup-uri, finanțări).

### Oriunde
- **LinkedIn** prin căutare web, ex. `site:linkedin.com/company "fashion" "Cluj"`. Pagina de companie dă mărimea aproximativă și anul.
- **Google Maps** pentru afaceri locale (clinici, restaurante, service-uri).
- **Semnale:** anunțuri de angajare (LinkedIn Jobs, eJobs, BestJobs, site-ul firmei), știri, comunicate, finanțări, lansări.
- **Tehnologii:** codul sursă al site-ului (ex. Shopify, WooCommerce, Magento), BuiltWith / Wappalyzer.
- **Apollo** (dacă există cheie): `enrich.py apollo-orgs --keywords "fashion,apparel" --locations "Romania" --employees "11,50"`.

### Pentru fiecare candidat
1. `crm.py company check --domain firma.ro --name "Firma"`. Dacă `exists` sau `blocked` e `true`, sari peste el și notează-l în raport.
2. Verifică criteriile în cel puțin o sursă (mărime, an, țară, domeniu). Dacă o valoare e estimată, scrie asta în `notes`.
3. Notează 1-3 observații de personalizare concrete și recente în `personalization` (ex. „au deschis al doilea showroom în octombrie 2026”, „angajează 2 developeri PHP”, „checkout-ul încă cere cont obligatoriu”). Fără observații generice de tipul „firmă dinamică”.
4. Dă un `fit_score` 1-5 și un `fit_reason` scurt față de oferta vizată.

## 3. Persoane de contact

Ordinea surselor, de la cea mai bună:

1. **Site-ul firmei:** „Echipa”, „Despre noi”, „Contact”, „Impressum” (în DE, AT, CH Impressum-ul îl numește obligatoriu pe directorul general), blog (autori), comunicate.
2. **LinkedIn** prin căutare web: `site:linkedin.com/in "Firma" (CEO OR fondator OR "director general")`. Verifică să lucreze încă acolo (rolul curent).
3. **Registre:** administratorii și asociații (pentru firme mici, de obicei decidentul).
4. **Presă, podcasturi, conferințe:** interviuri, liste de vorbitori.
5. **Apollo** (cu cheie): `enrich.py apollo-people --domains firma.ro --titles "CEO,Founder,CTO"`. Nu dă emailuri; pentru email folosește pasul următor.

Alege 1-2 persoane per firmă: decidentul pentru oferta respectivă (firmă mică: fondatorul/administratorul; firmă medie: șeful departamentului vizat). Salvează `role`, `seniority` (`owner`, `founder`, `c_suite`, `director`, `manager`, `senior`, `other`), `linkedin` și sursa.

## 4. Emailuri

Ordinea de preferință:

1. **Adresă publicată** pe site, în comunicate, pe LinkedIn: `email_status: "found"`, `email_source`: URL-ul.
2. **Pattern dedus:** dacă găsești adresa reală a unui coleg (ex. `maria.popa@firma.ro`), aplică același pattern: `enrich.py guess --domain firma.ro --first Ion --last Ionescu --pattern "{first}.{last}"`; `email_status: "guessed"`, cu nota pattern-ului.
3. **Hunter** (cu cheie): `enrich.py hunter-domain --domain firma.ro` (pattern + persoane), `enrich.py hunter-find --domain firma.ro --first Ion --last Ionescu`.
4. **Apollo** (cu cheie, consumă credite): `enrich.py apollo-match --first Ion --last Ionescu --domain firma.ro`.
5. **Ghicire simplă:** `enrich.py guess --domain firma.ro --first Ion --last Ionescu`. Primul candidat e cel mai comun pattern; restul sunt alternative. `email_status: "guessed"`.
6. **Adresă generică** (office@, contact@): ultima variantă. Pune-o în `generic_email` la firmă, nu ca persoană.

Verificare:
- `enrich.py mx --domain firma.ro`: domeniul primește email? Dacă nu, nu scrie la el.
- `enrich.py hunter-verify --email x@firma.ro` (cu cheie): `valid` devine `verified`, `accept_all` devine `catch_all`, `invalid` devine `invalid`.
- Spune-i utilizatorului clar câte emailuri sunt verificate și câte ghicite. Un bounce peste 5% afectează reputația domeniului expeditorului.

Valori `email_status`: `verified`, `found`, `guessed`, `catch_all`, `unknown`, `invalid`.

## 5. Format pentru import

Scrie lotul într-un fișier JSON (ex. în folderul de date sau într-un folder temporar) și importă-l:

```json
[
  {
    "name": "Moda Exemplu",
    "legal_name": "Moda Exemplu SRL",
    "tax_id": "RO40000000",
    "website": "https://modaexemplu.ro",
    "country": "Romania",
    "city": "Cluj-Napoca",
    "industry": "e-commerce fashion",
    "employees_count": 18,
    "founded_year": 2017,
    "revenue": "1,2 mil. EUR (2025)",
    "linkedin": "https://www.linkedin.com/company/...",
    "description": "Magazin online de îmbrăcăminte pentru femei, cu showroom în Cluj.",
    "personalization": "Au lansat în octombrie 2026 plata în rate; angajează un developer WooCommerce.",
    "fit_score": 4,
    "fit_reason": "Magazin WooCommerce cu flux de plată nou, mărime potrivită.",
    "source": "web",
    "source_urls": ["https://www.listafirme.ro/...", "https://modaexemplu.ro/despre"],
    "contacts": [
      {
        "full_name": "Ioana Exemplu",
        "first_name": "Ioana",
        "last_name": "Exemplu",
        "role": "Fondatoare",
        "seniority": "founder",
        "email": "ioana@modaexemplu.ro",
        "email_status": "found",
        "email_source": "https://modaexemplu.ro/contact",
        "linkedin": "https://www.linkedin.com/in/..."
      }
    ]
  }
]
```

```bash
python3 "$SKILL_DIR/scripts/crm.py" company import --file /cale/lot.json --search-id 3
```

Rezultatul arată ce s-a creat, ce s-a sărit ca duplicat și eventualele erori. Pentru o singură firmă poți folosi `company add`.

## 6. Prezentarea rezultatului

Tabel scurt: firmă, oraș, angajați, an, contact + rol, email + status, scor. Sub tabel: câte au fost sărite (duplicate sau blocate), ce criterii n-au putut fi verificate, și propunerea de pas următor („Scriu emailurile pentru cele cu scor 4-5?”).

## 7. Conformitate (GDPR și reguli locale)

- Folosește doar date de business (email de serviciu, rol), relevante pentru oferta trimisă. Nu colecta date personale inutile.
- Notează sursa fiecărui contact (`email_source`, `source_urls`). Persoana are dreptul să afle de unde ai datele.
- Include în fiecare email inițial o formulă simplă de opt-out și respect-o imediat (clasificare `unsubscribe`, care suprimă adresa).
- Regulile pentru emailul comercial nesolicitat diferă între țări; în unele (de exemplu Germania) chiar și B2B se cere de regulă consimțământ prealabil. Dacă utilizatorul țintește o țară nouă, amintește-i pe scurt să verifice regulile locale. Decizia îi aparține.
