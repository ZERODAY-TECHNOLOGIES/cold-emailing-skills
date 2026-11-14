# Scrierea emailurilor: cold email, follow-up, răspuns

Ținta: un email pe care un om ocupat îl citește în 20 de secunde și care sună scris de un om pentru el, nu de un tool pentru o listă.

## Înainte de scriere

Ai nevoie de:
- **Limba** (întrebată de fiecare dată) și forma de adresare (`config get formality_ro` etc.; dacă lipsește, întreabă și salvează).
- **Oferta** aleasă: `offering show ID` (beneficii, probleme rezolvate, dovezi, CTA).
- **Expeditorul**: `sender show ID` (semnătură, ton).
- **Firma și contactul**: `company show ID` (descriere, `personalization`, rol, istoric).
- **Profilul firmei proprii**: `profile show` (dovezi, clienți).

Dacă nu ai nicio observație concretă despre firmă, documentează-te întâi (site, știri, LinkedIn, anunțuri de angajare). Fără ea, emailul devine generic.

## Structura emailului inițial (50-125 de cuvinte)

1. **Subiect:** 2-6 cuvinte, litere mici în mare parte, specific lor. Fără „!”, fără majuscule, fără „Re:” fals, fără clickbait.
   Bune: `checkout-ul modaexemplu.ro`, `întrebare despre showroom-ul din Cluj`, `noii developeri WooCommerce`, `idee pentru plata în rate`.
   Slabe: `Colaborare`, `Ofertă specială pentru dumneavoastră`, `Creșteți vânzările cu 300%!`
2. **Salut:** cu prenumele, sau „Bună ziua, doamna/domnule X” dacă forma e formală. Fără „Stimate client”.
3. **Deschidere despre ei (1-2 propoziții):** observația concretă din `personalization`. Arată că ai văzut ceva real la ei.
4. **Legătura cu problema (1-2 propoziții):** ce implică de obicei situația lor, legat de una din `pain_points`. Formulat ca observație, nu ca acuzație („de obicei apare X”, nu „aveți problema X”).
5. **Oferta, pe scurt (1-2 propoziții):** ce faceți și o dovadă concretă (`proof`, `case_studies`). Rezultatul, nu lista de servicii.
6. **CTA (o singură întrebare, ușor de acceptat):** interes, nu angajament. „Vă trimit un exemplu de raport?” e mai bun decât „Când aveți 30 de minute pentru o întâlnire?”
7. **Opt-out (o propoziție):** „Dacă nu e relevant acum, spuneți-mi și nu vă mai scriu.”
8. **Semnătura** expeditorului exact cum e salvată.

## Stil umanizat

Fă:
- Propoziții scurte, de lungimi diferite. Unele de 4 cuvinte. Altele mai lungi, dar sub 25.
- Cuvinte simple, cum ai vorbi la telefon cu un om de business pe care îl respecți.
- Persoana I singular („am văzut”, „lucrez cu”), nu „compania noastră”.
- Mai mult despre ei decât despre tine. Numără „noi/eu” vs. „dvs./tu”: ei trebuie să câștige.
- O singură idee centrală. Un singur CTA.
- Cifre concrete în loc de adjective („3 vulnerabilități critice” în loc de „rezultate excelente”).
- Text simplu: fără bold, fără liste cu buline, fără emoji, fără imagini, maxim un link (ideal zero în primul email).
- În engleză: contracții naturale (I'm, you're, it's). În română: diacritice corecte (ș, ț cu virgulă).

Nu face:
- **Em dash (—) sau en dash (–), în nicio limbă.** Nici „ - ” sau „--” ca înlocuitor. Folosește virgulă, punct, două puncte sau o propoziție nouă. Regula e verificată automat.
- Nu deschide cu tine: „Mă numesc...”, „Sunt X de la Y”, „Vă scriu pentru a vă prezenta...”, „Sper că acest email vă găsește bine”.
- Nu folosi construcții tipice AI: „nu doar X, ci și Y”, enumerări în trei („rapid, eficient și sigur”), întrebări retorice în cascadă, „în era digitală”, „în peisajul actual”, „soluții inovatoare”, „la următorul nivel”, „partener de încredere”, „valoare adăugată”, „sinergie”, „experiență vastă”.
- În engleză evită: leverage, seamless, game-changer, cutting-edge, unlock, elevate, delve, streamline, empower, robust, holistic, „I hope this email finds you well”, „I'm reaching out”, „just following up”, „just checking in”, „touch base”, „circle back”, „don't hesitate to”.
- Fără laude goale („am fost impresionat de compania dvs.”), fără urgență falsă, fără „ofertă limitată”.
- Fără cuvinte care declanșează filtrele de spam: gratuit, garantat, 100%, urgent, click aici, free, guaranteed, act now.
- Fără punct și virgulă și fără puncte de suspensie decât dacă chiar își au locul.

Verificarea automată (`message add` sau `crm.py lint --stdin`) prinde o parte din acestea. Scorul ideal: 85+. Avertizările nu blochează salvarea, dar citește-le și corectează ce are sens.

## Exemple

### Română, formal (dumneavoastră)

```
Subiect: plata în rate pe modaexemplu.ro

Bună ziua, doamna Exemplu,

Am văzut că ați introdus luna trecută plata în rate pe modaexemplu.ro. E o mișcare bună pentru coșul mediu.

Fluxurile noi de plată sunt însă locul unde găsim cele mai multe probleme de securitate la magazinele online. La ultimele 20 de teste pe WooCommerce, 14 aveau cel puțin o vulnerabilitate critică exact acolo.

Facem teste de penetrare pentru magazine de mărimea dumneavoastră, cu raport în 5 zile.

Vă trimit un exemplu de raport anonimizat, ca să vedeți ce verificăm?

Dacă nu e relevant acum, spuneți-mi și nu vă mai scriu.

Cu stimă,
Andrei Pop
Fondator, Exemplu Tech
```

### Română, informal (tu)

```
Subiect: noii developeri WooCommerce

Bună, Ioana,

Am văzut că angajați doi developeri WooCommerce. Pare că urmează ceva mare pe magazin.

Când echipa crește și se lansează funcții noi repede, securitatea rămâne de obicei pe ultimul loc până apare prima problemă.

Noi testăm magazinul ca un atacator real, iar echipa primește lista exactă cu ce e de reparat. La un client din Iași am găsit acces la comenzile tuturor clienților printr-un singur parametru din URL.

Are sens să-ți trimit un exemplu de raport?

Dacă nu e momentul, zi-mi și nu te mai deranjez.

Andrei
```

### English

```
Subject: your new instalment checkout

Hi Ioana,

Saw you added instalment payments to modaexemplu.ro last month. Nice move for basket size.

New payment flows are where we find most of the serious security holes in online stores. In our last 20 WooCommerce tests, 14 had at least one critical issue right there.

We run penetration tests for stores your size and deliver the report in five days.

Want me to send over an anonymised sample report?

If this isn't relevant, just say so and I won't email again.

Andrei Pop
Founder, Exemplu Tech
```

## Follow-up pentru cine nu a răspuns

Implicit 2 follow-up-uri, la ~4 zile distanță (setări `followup_days`, `max_followups`). Fiecare:

- **Scurt:** 25-80 de cuvinte.
- **Același fir:** subiect „Re: <subiectul inițial>” (aici e firesc, chiar e același fir) și răspuns la emailul anterior, ca destinatarul să vadă contextul.
- **Unghi nou, nu reminder.** Nu „revin la emailul anterior” sau „doar verificam dacă ați văzut”. Adu ceva util:
  - Follow-up 1: o informație sau un exemplu concret legat de situația lor („o verificare de 5 minute pe care o poate face echipa dvs.”, un caz similar, o cifră).
  - Follow-up 2 (ultimul): o întrebare simplă care ușurează răspunsul („Sunteți persoana potrivită pentru asta sau e mai degrabă colegul X?”) sau închidere politicoasă („Presupun că nu e o prioritate acum, nu vă mai scriu pe tema asta.”).
- Aceeași limbă ca emailul inițial, dacă utilizatorul nu cere altfel.

Exemplu (follow-up 1, română):

```
Subiect: Re: plata în rate pe modaexemplu.ro

Bună ziua, doamna Exemplu,

Un lucru pe care echipa dvs. îl poate verifica în 5 minute: dacă la pasul de plată se poate modifica suma din browser înainte de trimitere. Am găsit asta la două magazine din ultimele luni.

Dacă vreți, vă trimit lista completă de verificări rapide pe care o folosim.

Andrei
```

## Răspuns la un lead care a răspuns

- Răspunde exact la ce a întrebat sau a spus, în primele 1-2 propoziții.
- Ton cald, dar la obiect. Fără să reiei prezentarea de la zero.
- Dacă e interesat: propune un pas concret cu 2 variante de timp („joi la 11 sau vineri la 14?”) sau trimite ce a cerut.
- Dacă are o obiecție: recunoaște-o, răspunde cu un fapt, nu insista.
- Limba: de regulă cea în care a scris lead-ul (confirmă cu utilizatorul).
- Detalii pe fiecare tip de răspuns: `replies-followups.md`.

## Salvarea

```bash
python3 "$SKILL_DIR/scripts/crm.py" message add --stdin <<'EOF'
{"company_id": 12, "contact_id": 30, "sender_id": 1, "offering_id": 2, "kind": "initial", "language": "ro",
 "subject": "plata în rate pe modaexemplu.ro",
 "body": "Bună ziua, doamna Exemplu,\n\nAm văzut că ...\n\nCu stimă,\nAndrei Pop\nFondator, Exemplu Tech"}
EOF
```

`kind`: `initial`, `follow_up` sau `reply`. `step` și `parent_id` se completează automat. Răspunsul conține `lint` cu scorul și observațiile. Dacă rescrii: `message update ID --stdin` cu `subject`/`body` noi.

Arată utilizatorului emailul final într-un format ușor de copiat (subiectul pe un rând, corpul dedesubt), spune că e salvat ca draft cu id-ul lui și cere confirmarea trimiterii.
