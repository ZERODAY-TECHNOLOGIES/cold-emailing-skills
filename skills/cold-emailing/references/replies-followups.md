# Răspunsuri primite și follow-up

## Fluxul la un răspuns primit

1. **Identifică firma:** `company check --email adresa@firma.ro`. Dacă adresa e nouă (alt angajat, un forward), caută după domeniu sau nume; dacă tot nu e clar, întreabă utilizatorul. Dacă scrie o persoană nouă din firmă, adaug-o cu `contact add`.
2. **Citește firul:** `message thread COMPANY_ID`, ca să știi exact ce s-a trimis, în ce limbă și ce ofertă.
3. **Clasifică** (tabelul de mai jos) și spune-i utilizatorului clasificarea într-o propoziție.
4. **Înregistrează** cu `inbound`.
5. **Propune pasul următor**, de obicei un răspuns redactat, salvat ca draft cu `kind: "reply"`.

```bash
python3 "$SKILL_DIR/scripts/crm.py" inbound --stdin <<'EOF'
{"company_id": 12, "contact_id": 30, "classification": "question",
 "subject": "Re: plata în rate pe modaexemplu.ro",
 "body": "Bună ziua, cât durează un test și ce costă?",
 "received_at": "2026-11-14 09:12", "language": "ro"}
EOF
```

Dacă `company_id` lipsește, scriptul încearcă să găsească firma după `from_email`.

## Clasificări și efecte automate

| Clasificare | Când | Status firmă | Ce faci |
|---|---|---|---|
| `interested` | Vrea să afle mai mult, cere materiale, preț, detalii | `interested` | Răspunzi rapid cu ce a cerut + propui un pas concret |
| `meeting` | Acceptă sau propune o discuție | `meeting` | Confirmi ziua/ora, trimiți invitația (utilizatorul), eventual agendă scurtă |
| `question` | Pune o întrebare, fără interes clar încă | `replied` | Răspunzi exact la întrebare, apoi un CTA mic |
| `objection` | „Avem deja furnizor”, „e scump”, „nu avem buget” | `replied` | Recunoști, un fapt relevant, o întrebare deschisă; nu insiști |
| `referral` | „Vorbiți cu colegul X” | `replied` | Adaugi contactul, scrii persoanei recomandate menționând recomandarea, mulțumești celui care a recomandat |
| `not_now` | „Reveniți în martie”, „acum nu e momentul” | `paused` | Mulțumești scurt; pune `follow_up_at` cu data menționată (implicit +90 zile) |
| `not_interested` | Refuz clar | `not_interested` | Opțional, un răspuns scurt de mulțumire. Fără argumente |
| `unsubscribe` | Cere să nu mai fie contactat, sau răspuns ostil | `do_not_contact` | Nu mai răspunzi. Adresa e suprimată automat |
| `ooo` | Răspuns automat de concediu | neschimbat | Pune `follow_up_at` la data revenirii + 1-2 zile |
| `bounce` | Emailul nu a ajuns | `bounced` | Contactul devine `invalid`; cauți altă adresă/persoană, apoi readuci statusul cu `company status` |
| `other` | Nimic din cele de mai sus | `replied` | Judecă de la caz la caz |

Statusurile pozitive nu se retrogradează automat (o întrebare după o întâlnire nu mută firma înapoi la `replied`). Un `unsubscribe` marchează toată firma `do_not_contact`; dacă utilizatorul vrea totuși să contacteze altă persoană de acolo, schimbă statusul manual și confirmă cu el.

## Cum scrii răspunsul

Reguli generale (pe lângă cele din `email-writing.md`):
- Prima propoziție răspunde la ce a spus el.
- Scurt: 40-120 de cuvinte. Dacă a cerut detalii tehnice, poate fi mai lung, dar structurat în paragrafe scurte.
- Limba: cea în care a scris lead-ul. Confirmă cu utilizatorul înainte de a redacta.
- Serviciul: cel din conversație. Dacă răspunsul sugerează nevoia altei oferte salvate, propune-o utilizatorului, nu o schimba singur.
- Nu inventa prețuri, termene sau disponibilitate. Folosește `pricing` din ofertă doar dacă utilizatorul e de acord, altfel întreabă-l.
- Pentru întâlniri, cere-i utilizatorului 2 intervale disponibile sau linkul de programare.
- Fără em dash, ca peste tot.

Exemple scurte:

**question** („Cât durează și cât costă?”)
```
Bună ziua, doamna Exemplu,

Pentru un magazin de mărimea dumneavoastră testul durează 4-5 zile lucrătoare, iar raportul îl primiți în 2 zile după. Prețul pornește de la 2.500 EUR și depinde de câte integrări aveți (plăți, ERP, curierat).

Dacă îmi spuneți ce integrări folosiți, vă trimit o estimare exactă. Sau putem vorbi 15 minute joi sau vineri, cum vă e mai simplu.

Cu stimă,
Andrei Pop
```

**objection** („Avem deja pe cineva care se ocupă de securitate.”)
```
Bună ziua,

Perfect, e un lucru bun că aveți pe cineva dedicat.

Mulți dintre clienții noștri au și ei echipă internă. Ne cheamă o dată pe an pentru o privire din afară, pentru că e greu să testezi obiectiv ce ai construit tu.

Dacă la un moment dat vă ajută o a doua opinie, îmi scrieți. Până atunci, nu vă mai deranjez.

Andrei
```

**referral** (către persoana recomandată)
```
Subiect: recomandare de la Ioana Exemplu

Bună ziua, domnule Marin,

Ioana mi-a spus că dumneavoastră vă ocupați de partea tehnică a magazinului, așa că vă scriu direct.

Pe scurt: facem teste de securitate pentru magazine online, iar fluxul nou de plată în rate e exact genul de zonă unde găsim probleme.

Vă trimit un exemplu de raport, ca să vedeți dacă merită o discuție?

Dacă nu e cazul, spuneți-mi și nu vă mai scriu.

Andrei Pop
```

## Follow-up pentru cine nu a răspuns

```bash
python3 "$SKILL_DIR/scripts/crm.py" followups --format text
python3 "$SKILL_DIR/scripts/crm.py" followups --days 14 --format text
```

Secțiuni:
- **Așteaptă răspunsul nostru:** lead-uri care au scris ultimele și încă nu le-am răspuns. Prioritate maximă, mai ales `interested` și `meeting`.
- **Follow-up scadent:** emailuri fără răspuns, trecute de `followup_days`, cu pași rămași din secvență. Include `next_step` (1 = primul follow-up).
- **Urmează:** programate în următoarele N zile (follow-up, reluări după `not_now`, revenire după `ooo`).
- **Drafturi netrimise:** întreabă utilizatorul dacă le-a trimis între timp (`message sent`) sau dacă trebuie anulate (`message cancel ID`).

Pentru un lot de follow-up-uri: confirmă o dată limba (implicit cea a emailului inițial al fiecărei firme), apoi scrie fiecare follow-up separat, cu unghi nou, folosind `message thread` pentru context. Salvează cu `kind: "follow_up"`.

După ultimul follow-up din secvență, firma rămâne `contacted` fără acțiune programată. Utilizatorul poate decide mai târziu o reluare cu altă ofertă (atunci folosește `message add --force` cu `kind: "initial"` și spune-i că firma a mai fost contactată, când și despre ce).
