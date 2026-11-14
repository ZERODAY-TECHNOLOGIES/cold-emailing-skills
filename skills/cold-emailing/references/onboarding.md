# Configurare: profilul firmei, expeditori, servicii și produse

Scopul: emailurile să fie scrise din date reale despre firma ta, nu din formulări generice. Cu cât profilul și ofertele sunt mai concrete (cifre, clienți, rezultate), cu atât emailurile sunt mai bune.

## Ordinea recomandată

1. Profilul firmei
2. Cel puțin un expeditor
3. Cel puțin un serviciu sau produs
4. Preferințe de stil (o singură dată)

Nu cere totul într-un singur mesaj lung. Cere esențialul, propune restul din ce găsești pe site, apoi confirmă.

## Varianta rapidă: pornind de la site

Dacă utilizatorul dă site-ul firmei:

1. Citește pagina principală, „Despre noi”, „Servicii”/„Produse”, „Clienți”/„Portofoliu”/„Studii de caz”, „Contact”.
2. Pentru firme din România poți completa datele de identificare din surse publice (listafirme.ro, termene.ro, mfinante.gov.ro) pe baza CUI-ului sau a denumirii.
3. Propune un profil și o listă de oferte într-un format scurt, ușor de corectat.
4. Salvează doar după confirmare.

## Profilul firmei (`profile set`)

Profilul e un document JSON flexibil. Câmpuri recomandate:

| Câmp | Ce conține |
|---|---|
| `name` | Numele comercial |
| `legal_name` | Denumirea juridică (ex. „Exemplu Tech SRL”) |
| `tax_id` | CUI / VAT ID |
| `registration_number` | Nr. Registrul Comerțului |
| `address`, `country` | Sediul |
| `website`, `phone`, `email` | Date de contact generale |
| `industry` | Domeniul de activitate |
| `description` | 2-3 propoziții: ce face firma, pentru cine |
| `value_proposition` | O propoziție: ce rezultat obține clientul |
| `differentiators` | De ce voi și nu alții (listă) |
| `case_studies` | Rezultate concrete: client (sau tip de client), problemă, rezultat cu cifră |
| `clients` | Clienți care pot fi menționați public |
| `founded_year`, `team_size` | Credibilitate |
| `certifications` | ISO, parteneriate, acreditări |
| `languages` | Limbile în care puteți lucra cu clienții |

Exemplu:

```bash
python3 "$SKILL_DIR/scripts/crm.py" profile set --stdin <<'EOF'
{
  "name": "Exemplu Tech",
  "legal_name": "Exemplu Tech SRL",
  "tax_id": "RO12345678",
  "registration_number": "J40/1234/2019",
  "address": "Str. Exemplu 1, București",
  "country": "Romania",
  "website": "https://exemplu.ro",
  "industry": "Securitate cibernetică",
  "description": "Facem teste de penetrare și audit de securitate pentru IMM-uri și magazine online.",
  "value_proposition": "Găsim breșele înaintea atacatorilor, cu raport clar și pași de remediere.",
  "differentiators": ["raport în 5 zile lucrătoare", "retestare gratuită după remediere", "echipă certificată OSCP"],
  "case_studies": ["Magazin online cu 40 de angajați: 3 vulnerabilități critice găsite în checkout, remediate în 2 săptămâni"],
  "founded_year": 2019,
  "team_size": "8"
}
EOF
```

Un câmp setat la `null` se șterge. `profile replace` înlocuiește tot profilul.

## Expeditori (`sender add`)

Persoana care semnează emailul. Câmpuri:

| Câmp | Note |
|---|---|
| `full_name` | Obligatoriu |
| `role` | Funcția (ex. „Fondator”, „Business Development”) |
| `email`, `phone`, `linkedin` | Apar în semnătură dacă utilizatorul vrea |
| `signature` | Semnătura exactă, cu `\n` între rânduri. Folosește-o identic în emailuri |
| `tone` | ex. „direct, prietenos, fără formalisme” |
| `languages` | Limbile în care scrie expeditorul, ex. `["ro", "en"]` |
| `is_default` | Expeditorul implicit (primul adăugat devine automat implicit) |

```bash
python3 "$SKILL_DIR/scripts/crm.py" sender add --json '{"full_name": "Andrei Pop", "role": "Fondator", "email": "andrei@exemplu.ro", "phone": "+40 700 000 000", "signature": "Andrei Pop\nFondator, Exemplu Tech\n+40 700 000 000", "tone": "direct, colegial", "languages": ["ro", "en"]}'
```

Semnătura e bine să fie scurtă: nume, funcție, firmă, eventual telefon. Fără logo, fără bannere, fără citate.

## Servicii și produse (`offering add`)

Fiecare ofertă e o intrare separată. Câmpuri:

| Câmp | Ce conține |
|---|---|
| `name` | Obligatoriu |
| `kind` | `service` sau `product` |
| `summary` | O propoziție |
| `description` | Detalii: ce include, cum se livrează |
| `benefits` | Rezultate pentru client, nu caracteristici (listă) |
| `target_customers` | Clientul ideal: industrie, mărime, situație (listă) |
| `pain_points` | Problemele pe care le rezolvă, formulate cum le-ar spune clientul (listă) |
| `differentiators` | Ce o face diferită (listă) |
| `pricing` | Preț orientativ sau model de preț (folosit doar dacă utilizatorul vrea să apară) |
| `proof` | Dovezi: cifre, clienți, rezultate (listă) |
| `cta` | CTA preferat, ex. „exemplu de raport”, „demo de 15 minute”, „audit gratuit” |
| `keywords` | Cuvinte cheie utile la căutarea de firme potrivite |

```bash
python3 "$SKILL_DIR/scripts/crm.py" offering add --stdin <<'EOF'
{
  "kind": "service",
  "name": "Test de penetrare pentru magazine online",
  "summary": "Testăm site-ul, checkout-ul și panoul de administrare ca un atacator real.",
  "benefits": ["afli ce poate fi exploatat înainte să fie", "raport pe înțelesul echipei tehnice și al managementului", "dovadă de conformitate pentru procesatorii de plăți"],
  "target_customers": ["magazine online cu 10-200 de angajați", "firme care au schimbat recent platforma sau procesatorul de plăți"],
  "pain_points": ["nu știm cât de sigur e checkout-ul", "procesatorul de plăți ne cere un test", "am avut un incident și vrem să nu se repete"],
  "proof": ["peste 60 de teste făcute în 2025", "media: 2,4 vulnerabilități critice pe test"],
  "pricing": "de la 2.500 EUR",
  "cta": "un exemplu de raport anonimizat",
  "keywords": ["e-commerce", "magento", "woocommerce", "shopify", "plăți online"]
}
EOF
```

Dacă utilizatorul nu are dovezi sau cifre, nu le inventa. Notează că lipsesc și scrie emailurile fără ele.

## Preferințe de stil (`config set`)

Întreabă o singură dată, la configurare sau la primul email, și salvează:

| Cheie | Valori | Rol |
|---|---|---|
| `formality_ro` | `dumneavoastra` / `tu` | Forma de adresare în română |
| `formality_de` | `Sie` / `du` | Forma de adresare în germană |
| `formality_fr` | `vous` / `tu` | Forma de adresare în franceză |
| `default_language_suggestion` | ex. `ro` | Doar ca propunere; limba se întreabă tot de fiecare dată |
| `followup_days` | implicit `4` | Zile de așteptare după fiecare email fără răspuns |
| `max_followups` | implicit `2` | Câte follow-up-uri după emailul inițial |
| `not_now_days` | implicit `90` | După cât timp reluăm un „nu acum” fără dată |
| `ooo_days` | implicit `7` | După cât timp reluăm un out-of-office fără dată |
| `hunter_api_key`, `apollo_api_key` | cheile API | Opțional, pentru găsirea și verificarea emailurilor |

```bash
python3 "$SKILL_DIR/scripts/crm.py" config set formality_ro dumneavoastra
```

Cheile API pot fi date și ca variabile de mediu (`HUNTER_API_KEY`, `APOLLO_API_KEY`). În `config list` ele apar mascate.
