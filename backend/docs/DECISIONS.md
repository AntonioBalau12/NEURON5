# Etapa A — audit și decizii (D1–D6)

Scop: consemnarea diferențelor dintre plan (`frontend/public/PLAN_ARHITECTURA_API_CSV_OFFLINE.md`)
și repository, înainte de implementare. Plan §0 cere explicit documentarea contradicțiilor.

## Audit scurt al repository-ului (2026-10-28)

| Ce există | Unde | Stare |
| --- | --- | --- |
| Contractele juraților (input `/universe`, output `/output/output.csv`, imagine Docker, offline 2 CPU / 6 GiB / 30 min) | `contracts/`, `README.md`, `scripts/` | sursă de adevăr pentru limbajul de etichete și pentru ce înseamnă „sistemul rulează” |
| Date de practică: 1.897 rânduri (`true` 1.581, `false` 277, `unsure` 39), coloane `id,text,date,label,form`; lexicon cu 62 subiecte + 13 evenimente | `data/` | suficiente pentru evaluare offline și pentru un KB determinist |
| Frontend Next.js 15 App Router (TS, Tailwind), landing + mascotă Rive + `Studio.tsx` cu 3 pași **mock** (setTimeout, date hardcodate) | `frontend/` | se păstrează landing-ul; `Studio` se leagă la API-ul real |
| Site static vechi (index.html, previewN.html, DESIGN.md) | rădăcină repo | nu se atinge |
| Fundație Python deterministă (ingestie CSV, lexicon, valori tipizate, validare output) existentă pe `origin/codex/p0-contract-foundation` | `foundation.py` (branch) | copiată în `backend/app/engine/foundation.py` și refolosită |
| Backend / API | **nu exista** | creat în `backend/` (FastAPI), conform cerinței utilizatorului |
| Clasificator | **nu exista** pe `main` și **nu se construiește aici** | clasificarea este a colegilor: backend-ul trimite HTTP payload-ul datasetului către serverul lor și stochează răspunsul (date sau CSV). Claims = în afara scopului acestui build |

Constrângeri explicite de la utilizator: modificări doar în `frontend/` și `backend/` nou;
fără commit-uri (doar branch-ul `feature/backend`); frontend deja pornit pe `localhost:3000`.

## D1 — Etichete: `true`, `false`, `unsure`

`contracts/README.md` este contractul juraților: etichetele sunt exact `true`, `false`,
`unsure`, iar `confidence` e obligatoriu pentru `true`/`false` (0.5–1) și gol pentru
`unsure`. Planul mai pomenește `unsafe`; **`unsafe` nu există în contract și nu se emite
niciodată**. Rezolvare: pentru rândurile care nu pot fi clasificate (eroare tehnică, text gol,
lipsă de dovezi) se folosește `unsure` + eroare structurată, exact cum permite contractul.
Nu se mapează `unsure` la `false`.

## D2 — Coloane de intrare și ieșire

Contractul juraților fixează schema de input (`id,text,date,label`) și output
`id,type,text,form,label,confidence`. Aplicația din plan e însă generică. Rezolvare pentru app:

- mapping obligatoriu înainte de job: coloana text (obligatorie), coloana dată (opțională),
  coloana id (opțională, altfel rândurile primesc `r-<index>` stabil), coloana rezultat.
- dacă coloana rezultat există, valorile ei sunt suprascrise în output; dacă nu există, se
  **adaugă** o coloană la final (permisiune explicită D2). CSV-ul original nu e modificat.
- ordinea coloanelor existente și ordinea rândurilor se păstrează.

## D3 — Semantica `unsafe`

Fără echivalent în contractul juraților. Nu există categorie „conținut periculos” în date.
Rezolvare: `unsure` = sistemul nu are dovezi suficiente / rândul nu poate fi procesat;
conținutul periculos nu se evaluează. Erorile tehnice sunt separate de etichetă: `row.failed`
+ listă `errors` (`rowId`, `lineNumber`, `column`, `code`, `message`), conform planului §9.

## D4 — Delimitator și encoding

Autodetectare dintre `,` `;` tab după prima linie ne-goală; tie → `,` + warning
`AMBIGUOUS_DELIMITER`. UTF-8 cu BOM acceptat (`utf-8-sig`); alt encoding → eroare
`UNSUPPORTED_ENCODING`. Planul cerea confirmare UI la ambiguitate; deviație asumată minimă:
warning-ul e vizibil în UI, iar câmpul `delimiter` poate fi trimis explicit la upload bulk.

## D5 — „Păstrarea formatului”

Se păstrează schema logică și ordinea, nu identitatea byte-cu-byte: output-ul e rescris cu
`csv.writer` (quoting corect), aceleași coloane + eventuala coloană rezultat, aceleași
valori logice, `\n` ca line terminator. Nu se normalizează conținutul celulelor.

## D6 — Strategie de inferență: serviciul HTTP al colegilor

**Backend-ul nu clasifică nimic.** Colegii dețin motorul de clasificare; backend-ul este
orchestrator + proxy: trimite datasetul (snapshot CSV prin multipart sau JSON `rows`) către
unul sau mai multe endpoint-uri HTTP configurate prin `NEURON_CLASSIFIER_URLS` și așteaptă
răspunsul, care poate fi CSV direct sau date (JSON) — vezi `docs/API_CONTRACT.md` §7.
Răspunsul serviciului este tabelul autoritativ al jobului; când serviciul întoarce doar
etichete înguste (`id` + `label`), backend-ul le îmbină cu snapshot-ul păstrând coloanele,
ordinea și rândurile.

Consecințe:
- nu există model, lexicon sau inferență locală în acest build; `app/engine/remote_engine.py`
  este clientul HTTP, `app/engine/processor.py` doar stochează și validează răspunsul.
- indisponibilitatea serviciului **nu** produce etichete inventate: jobul eșuează cu
  `CLASSIFIER_UNAVAILABLE` (sau `TIMEOUT`), iar UI arată motivul.
- pentru dezvoltare locală există `app/mock_classifier.py`, un stand-in care răspunde cu
  etichete DEMO; se folosește doar până e pornit serviciul real și este marcat ca atare.


## Abateri și lucruri neimplementate (conștient, în afara scopului acestui build)

1. **Claims (exact 1.000 propoziții noi)** — cerute de jurați pentru rularea Docker, dar nu fac
   obiectul planului / aplicației CSV și nu sunt expuse de API-ul din acest build. Rămâne pe
   `backend/runner.py`-ul echipei din branch-ul p0 (candidate verificate extern).
2. **Dockerfile la rădăcină și scripts/check.sh** — interzise de constrângerea „doar
   `frontend/` și `backend/`”; nu se creează. Când se decide ambalarea, `backend/` are
   `requirements.txt` și instrucțiuni de rulare gata de copiat într-un Dockerfile.
3. **Motor local de clasificare** — nu se implementează: aparține colegilor. Seam-ul
   `app.engine.api.Engine` + `remote_engine.py` permit schimbarea endpoint-ului/payload-ului
   fără atingerea API-ului sau a UI-ului.
4. **Editor de coloane / redimensionare / duplicare coloane în Manual** — planul le cere;
   build-ul livrează CRUD de rânduri + undo/redo + paste TSV. Coloanele sunt fixe
   `id,text,date`. Se adaugă dacă rămâne timp / la cerere.
5. **Search în loguri, pause/resume/cancel, upload reluabil, istoric permanent** — explicit
   excluse de plan (§1), nu se implementează.
6. **Persistență** — niciuna, conform planului §1/§11; starea trăiește în RAM + fișiere
   temporare curățate la expirare.
7. **Autentificare** — doar sesiune anonimă izolată, conform planului §10.
8. **Frontend dev server** — deja pornit pe 3000 de utilizator; nu se pornește altul. CORS
   permite exact originile de dezvoltare.

## Întrebări deschise pentru echipă

- **Contractul serviciului HTTP al colegilor**: URL-ul exact, metoda (multipart CSV vs JSON
  `rows`), schema răspunsului și dacă răspunsul e CSV complet sau doar etichete. Se
  configurează din env, fără cod: `NEURON_CLASSIFIER_URLS`, `NEURON_CLASSIFIER_MODE`,
  `NEURON_CLASSIFIER_FIELD_NAME`, `NEURON_CLASSIFIER_TIMEOUT_SECONDS`,
  `NEURON_CLASSIFIER_TOKEN`. Dacă payload-ul cerut diferă, se adaptează doar
  `remote_engine.py`.
- Eticheta de fallback pentru rândurile fără rezultat în răspunsul îngust: `unsure`
  (conform contractului). Un rând lipsă nu oprește jobul, dar e raportat în `errors`.
- Claims + Docker rămân livrabile separate înainte de freeze.