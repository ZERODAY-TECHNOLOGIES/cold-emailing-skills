---
name: cold-emailing
description: Aplicație completă de cold emailing B2B cu memorie persistentă locală (SQLite). Folosește-o când utilizatorul vrea să caute firme noi sau lead-uri după criterii (domeniu, mărime, vechime, țară), să găsească persoane de contact și emailuri, să scrie un cold email personalizat sau un follow-up, să înregistreze un răspuns primit de la un lead, să vadă ce firme a contactat și ce le-a scris, să vadă statistici de campanie (rată de răspuns etc.), sau să salveze/actualizeze datele firmei proprii, serviciile/produsele și expeditorul. Triggers - cold email, prospectare, outreach, lead generation, find companies, follow up, a răspuns un client, statistici emailuri, campanie email, CRM.
---

# Cold Emailing

Skill-ul funcționează ca o aplicație de cold emailing: ține minte firma ta, serviciile tale, expeditorii, firmele țintă, persoanele de contact și fiecare email trimis sau primit. Totul stă într-o bază SQLite locală, gestionată exclusiv prin scripturile din `scripts/`.

Vorbește cu utilizatorul în limba în care îți scrie (implicit română). Limba emailurilor se alege separat, de fiecare dată.

## Reguli fixe

1. **Memoria = baza de date.** Orice informație nouă (profil, ofertă, expeditor, firmă, contact, email, răspuns, schimbare de status) se scrie imediat cu `crm.py`. Nu te baza pe memoria conversației.
2. **Nu inventa date.** Nume, roluri, emailuri, cifre despre firme vin doar din surse verificabile sau de la utilizator. Un email ghicit se salvează cu `email_status: "guessed"` și se spune asta clar.
3. **Fără em dash (—) și fără en dash (–) în emailuri.** `crm.py message add` le respinge automat. Nu folosi nici " - " sau "--" ca înlocuitor; reformulează cu virgulă, punct sau propoziții separate.
4. **Întreabă înainte de a scrie un email:** (a) limba, (b) serviciul/produsul prezentat (din lista salvată), (c) expeditorul, dacă există mai mulți. Nu presupune.
5. **Skill-ul nu trimite emailuri.** Le redactează și le salvează ca draft. Utilizatorul le trimite manual, apoi tu le marchezi trimise (`message sent`). Întreabă-l explicit dacă le-a trimis.
6. **Verifică înainte de a contacta.** Rulează `company check` înainte să adaugi o firmă sau să scrii cuiva. Nu contacta firme `do_not_contact`, emailuri suprimate sau firme deja în secvență, decât dacă utilizatorul cere explicit.
7. **Respectă opt-out-ul.** Când cineva cere să nu mai fie contactat, clasifică răspunsul `unsubscribe` (îl suprimă automat).

## Pornire: unde sunt scripturile și datele

`SKILL_DIR` este folderul care conține acest `SKILL.md`. Comenzile se rulează cu cale completă, de exemplu:

```bash
python3 "$SKILL_DIR/scripts/crm.py" overview
```

(Pe Windows, dacă `python3` nu există, folosește `python`.) Starea shell-ului nu se păstrează între apeluri, deci scrie calea completă de fiecare dată.

**Locația datelor** (prima care se aplică): `--data-dir CALE` (oriunde în comandă) > variabila `COLD_EMAIL_HOME` > `~/.cold-email/`.

La **prima utilizare din fiecare conversație**:

1. Stabilește locația datelor în funcție de mediu:
   - **Claude Code** (rulează pe calculatorul utilizatorului): implicitul `~/.cold-email/` e persistent. Nu e nevoie de `--data-dir`.
   - **Claude Desktop, mod Cowork, cu un folder selectat**: home-ul mașinii virtuale nu e garantat persistent. Folosește `--data-dir "<folderul selectat>/cold-email-data"` la **fiecare** comandă. Dacă există deja un `cold-email-data/crm.db` în folderul de lucru, folosește-l pe acela.
   - **Chat fără acces la fișiere locale** (claude.ai sau Desktop fără folder): avertizează utilizatorul că datele se pierd la finalul conversației. Oferă-i varianta: la final rulezi `backup` și îi dai fișierul `.db`; data viitoare îl încarcă și îl copiezi în data-dir înainte de orice comandă.
2. Rulează `crm.py overview`. Dacă baza de date e nouă sau goală, confirmă cu utilizatorul locația înainte să scrii date importante (să nu ajungă într-un loc greșit).
3. Citește `hints` din overview și spune-i utilizatorului pe scurt ce lipsește sau ce e de făcut (răspunsuri în așteptare, follow-up-uri scadente, drafturi netrimise).

Toate comenzile întorc JSON. Pentru a afișa tabele lizibile adaugă `--format text` (la `company list`, `followups`, `stats`, `message list`, `offering list`, `contact list`, `sql`). Pentru payload-uri cu text lung (emailuri), folosește `--stdin` cu heredoc ca să eviți problemele de ghilimele:

```bash
python3 "$SKILL_DIR/scripts/crm.py" message add --stdin <<'EOF'
{"company_id": 12, "offering_id": 2, "language": "ro", "subject": "...", "body": "..."}
EOF
```

`python3 "$SKILL_DIR/scripts/crm.py" schema` arată toate câmpurile acceptate și valorile permise. Câmpurile necunoscute se păstrează automat în `extra`.

## Fluxuri

### 1. Configurare inițială (profil firmă, expeditor, oferte)

Când profilul, expeditorul sau ofertele lipsesc, sau utilizatorul vrea să le modifice. Detalii și câmpuri complete: `references/onboarding.md`.

- **Profilul firmei** (`profile set`): nume, date de identificare (CUI, Reg. Com., adresă), site, ce face firma, propunere de valoare, diferențiatori, clienți/studii de caz, certificări. Dacă utilizatorul dă site-ul, citește-l (WebFetch / căutare web) și propune profilul și ofertele extrase, apoi cere confirmare înainte de salvare.
- **Expeditorul** (`sender add`): nume, funcție, email, telefon, LinkedIn, semnătura exactă, tonul preferat. Primul expeditor devine implicit.
- **Serviciile și produsele** (`offering add`): câte unul pe rând, cu beneficii concrete, clientul ideal, problemele pe care le rezolvă, dovezi (cifre, clienți), preț orientativ, CTA preferat.
- **Preferințe de stil** (`config set`): de ex. `formality_ro` (`dumneavoastra` sau `tu`), `followup_days`, `max_followups`. Întreabă o singură dată și salvează.

### 2. Căutare de firme noi și persoane de contact

Ghid complet cu surse pe țări, metode de găsire a emailurilor și verificare: `references/lead-search.md`. Citește-l înainte de prima căutare.

1. **Interviu scurt** (într-un singur mesaj, cu valori implicite propuse): domeniu de activitate / industrie, țară și eventual oraș/regiune, mărime (angajați sau cifră de afaceri), vechime (an înființare minim/maxim), B2B/B2C, alte filtre (tehnologii folosite, semnale precum angajări sau finanțări), excluderi, rolurile persoanelor de contact căutate (CEO, CTO, marketing etc.), câte firme vrea (implicit 10), pentru ce serviciu caută (ajută la scorul de potrivire).
2. **Salvează criteriile:** `search add --json '{"criteria": {...}, "summary": "e-commerce RO 10-50 ang."}'` și reține `search_id`.
3. **Caută firme** pe web (registre, directoare, LinkedIn, Google Maps etc.) și, dacă există chei, cu `enrich.py apollo-orgs`. Pentru fiecare candidat:
   - `company check --domain X --name "Y"` și sari peste ce există deja sau e blocat;
   - verifică criteriile (mărime, vechime, țară) din surse și notează sursa;
   - completează `fit_score` (1-5), `fit_reason` și `personalization` (1-3 observații concrete și recente despre firmă, utile în email).
4. **Găsește persoane de contact și emailuri:** site (echipă, despre noi, contact, impressum), LinkedIn (prin căutare), registre (administratori), presă. Pentru emailuri: adrese publice, `enrich.py hunter-domain / hunter-find / apollo-match` dacă există chei, altfel `enrich.py guess` cu pattern dedus. Marchează onest `email_status`: `verified`, `found`, `guessed`, `unknown`.
5. **Salvează lotul** într-un fișier JSON și importă: `company import --file leads.json --search-id N` (contactele merg în câmpul `contacts` al fiecărei firme). Duplicatele sunt sărite automat.
6. **Prezintă rezultatul** ca tabel: firmă, oraș, mărime, an, contact, rol, email + status, scor, motiv. Spune câte au fost sărite ca duplicate și de ce.

### 3. Redactarea unui cold email

Reguli de scriere, structură, exemple și listă de expresii interzise: `references/email-writing.md`. Citește-l înainte de a scrie primul email din conversație.

1. Identifică firma (`company check` / `company list`) și citește tot: `company show ID` (profil, contacte, istoric, `personalization`).
2. **Întreabă** (într-un singur mesaj): limba emailului; ce serviciu/produs prezinți (listează ofertele active cu id); expeditorul, dacă sunt mai mulți; destinatarul, dacă firma are mai multe contacte. Propune o variantă recomandată pentru fiecare, dar așteaptă confirmarea.
3. Dacă `personalization` lipsește sau e veche, documentează-te rapid despre firmă (site, știri, LinkedIn) și salvează observațiile cu `company update`.
4. Scrie emailul conform ghidului: subiect scurt, deschidere despre ei, legătura concretă dintre problema lor probabilă și oferta aleasă, o dovadă, un singur CTA ușor, opt-out politicos, semnătura expeditorului din baza de date. Text simplu, ton uman, fără em dash.
5. Salvează-l ca draft: `message add --stdin` (cu `company_id`, `contact_id`, `sender_id`, `offering_id`, `language`, `subject`, `body`, `kind: "initial"`). Scriptul rulează automat verificarea (`lint`). Dacă întoarce erori sau avertizări relevante, rescrie și salvează din nou (`message update ID`).
6. Arată emailul final utilizatorului (subiect + corp, gata de copiat) și spune-i că e salvat ca draft. Întreabă-l să-ți confirme când l-a trimis.
7. La confirmare: `message sent ID` (sau `message sent --all-drafts`, ori `--at "YYYY-MM-DD HH:MM"` dacă a fost trimis altă dată). Asta setează statusul `contacted` și programează follow-up-ul.

**Mai multe emailuri deodată:** întreabă limba, oferta și expeditorul o singură dată pentru tot lotul, apoi scrie câte un email cu adevărat personalizat pentru fiecare firmă. Nu folosi același text cu numele schimbat.

### 4. Răspunsuri primite și follow-up pentru lead-uri care au răspuns

Ghid detaliat pe fiecare tip de răspuns: `references/replies-followups.md`.

Când utilizatorul lipește un răspuns de la un lead:

1. Identifică firma și contactul: `company check --email adresa@firma.ro` (sau după nume/domeniu). Dacă nu e clar, întreabă.
2. Citește conversația: `message thread COMPANY_ID`.
3. Clasifică răspunsul: `interested`, `meeting`, `question`, `objection`, `referral`, `not_now`, `not_interested`, `unsubscribe`, `ooo`, `bounce`, `other`. Spune-i utilizatorului clasificarea.
4. Înregistrează-l: `inbound --stdin` cu `company_id`, `contact_id`, `classification`, `subject`, `body`, `received_at`, `language` și, pentru `not_now`/`ooo`, `follow_up_at` dacă reiese o dată. Statusul firmei, suprimarea și programările se actualizează automat.
5. Dacă e cazul (interested, meeting, question, objection, referral, other), propune un răspuns. Limba: propune limba în care a scris lead-ul și confirmă cu utilizatorul. Serviciul: același din conversație, dacă utilizatorul nu vrea altul. Salvează-l ca draft cu `kind: "reply"`, arată-l, apoi `message sent` după confirmare.
6. La `referral`: adaugă persoana recomandată cu `contact add` și propune un email nou către ea care menționează recomandarea.
7. La `bounce`: caută alt contact sau altă adresă, actualizează contactul și readu firma la statusul potrivit cu `company status`.

### 5. Follow-up pentru lead-uri care nu au răspuns

1. `followups --format text` arată: lead-uri care așteaptă răspunsul nostru, follow-up-uri scadente, ce urmează (`--days 14`) și drafturile netrimise.
2. Pentru fiecare follow-up scadent: `message thread ID`, apoi scrie un follow-up scurt, cu un unghi nou (o informație utilă, o întrebare diferită, un caz concret), nu „revin la emailul anterior”. Limba: aceeași ca emailul inițial (confirmă). Salvează cu `kind: "follow_up"`.
3. După `max_followups` (implicit 2) secvența se oprește automat. Nu insista peste limită fără acordul utilizatorului.

### 6. Statistici

```bash
python3 "$SKILL_DIR/scripts/crm.py" stats --format text
python3 "$SKILL_DIR/scripts/crm.py" stats --since 2026-10-01 --by offering,language,industry --format text
```

Dimensiuni pentru `--by`: `offering, sender, language, industry, country, size, month, week, seniority, search, status`. Indicatori: emailuri trimise (inițiale, follow-up, răspunsuri), firme contactate, rată de răspuns, rată pozitivă, întâlniri, câștigate, bounce, dezabonări, timp mediu până la răspuns, la ce pas din secvență vin răspunsurile, pipeline pe statusuri.

Prezintă cifrele, apoi 2-4 concluzii practice (ce ofertă/limbă/industrie merge mai bine, dacă follow-up-urile aduc răspunsuri, dacă bounce-ul e peste 5% și emailurile trebuie verificate mai bine). Atenționează când eșantionul e prea mic pentru concluzii (sub ~20 de firme pe grup). Pentru întrebări neprevăzute folosește `crm.py sql "SELECT ..."` (doar citire). Dacă utilizatorul vrea un grafic, construiește-l din aceste date.

### 7. Administrare

- Istoric firmă: `company show ID`; listă: `company list [--status contacted] [--uncontacted] [--q text] --format text`.
- Schimbare status manual: `company status ID meeting --note "call joi"`; statusuri: `new, drafted, contacted, replied, interested, meeting, won, lost, not_interested, paused, bounced, do_not_contact`.
- Do-not-contact: `suppress add email@firma.ro` sau `suppress add firma.ro --reason "..."`.
- Export CSV: `export --what all` (sau `companies`, `contacts`, `messages`). Copie de siguranță: `backup`. Oferă un backup după sesiuni cu multe modificări.
- Ștergere firmă: `company delete ID --yes`, doar la cererea explicită a utilizatorului.

## Referință rapidă comenzi

```
crm.py overview | where | schema | init
crm.py profile show | set --json '{...}' | replace --json '{...}'
crm.py sender list | add | update ID | default ID | remove ID
crm.py offering list | show ID | add | update ID | remove ID
crm.py search add | list | show ID | update ID
crm.py company check|find [--name --domain --tax-id --email --q] | add | import [--search-id] | update ID | show ID
                    | list [--status --country --industry --q --uncontacted] | status ID STATUS | delete ID --yes
crm.py contact add | update ID | list [--company ID] | show ID | remove ID
crm.py message add [--force] [--ignore-lint] | update ID | sent ID... [--all-drafts] [--at] | cancel ID
                    | show ID | list [--company --status --direction] | thread COMPANY_ID
crm.py inbound --stdin            (răspuns primit, cu classification)
crm.py followups [--days N]
crm.py stats [--since --until --by dims]
crm.py suppress add|list|remove ;  crm.py config list|get|set|unset
crm.py export [--what] ; crm.py backup ; crm.py sql "SELECT ..." ; crm.py lint --stdin
enrich.py keys | mx | guess | hunter-domain | hunter-find | hunter-verify | apollo-people | apollo-match | apollo-orgs
email_lint.py --stdin             (verificare independentă a unui text)
```

Payload-urile se dau cu `--json '...'`, `--file cale.json` sau `--stdin`. Opțiunile globale `--data-dir` și `--format` pot apărea oriunde în comandă.

## Fișiere de referință

- `references/onboarding.md`: câmpurile profilului, expeditorului și ofertelor, cum le extragi dintr-un site.
- `references/lead-search.md`: surse de firme pe țări, găsirea persoanelor de contact și a emailurilor, verificare, GDPR.
- `references/email-writing.md`: structura emailului, stil umanizat, expresii interzise, subiecte, exemple RO/EN, secvența de follow-up.
- `references/replies-followups.md`: cum clasifici și cum răspunzi la fiecare tip de răspuns.
