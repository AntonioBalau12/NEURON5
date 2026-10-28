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
| Fundație Python deterministă (ingestie CSV, lexicon, valori tipizate, validare output) existentă pe `origin/codex/p0-contract-foundation` | `foundation.py` (branch) | copiată inițial în `backend/app/engine/foundation.py`; auditul cleanup-ului a confirmat că modulul nu este folosit de orchestrator |
| Backend / API | **nu exista** | creat în `backend/` (FastAPI), conform cerinței utilizatorului |
| Clasificator | adaptorul local fitted din `backend/scripts/adapter.joblib` | prototip local LightGBM pentru etichetele `true`/`false`/`unsure`; nu generează claims |

Constrângeri explicite de la utilizator: modificări doar în `frontend/` și `backend/` nou;
fără commit-uri (doar branch-ul `feature/backend`); frontend deja pornit pe `localhost:3000`.

## D1 — Etichete: `true`, `false`, `unsure`

`contracts/README.md` este contractul juraților: etichetele sunt exact `true`, `false`,
`unsure`, iar `confidence` e obligatoriu pentru `true`/`false` (0.5–1) și gol pentru
`unsure`. Planul mai pomenește `unsafe`; **`unsafe` nu există în contract și nu se emite
niciodată**. Rezolvare: pentru rândurile care nu pot fi clasificate (eroare tehnică, text gol,
lipsă de dovezi) se folosește `unsure` + eroare structurată, exact cum permite contractul.
Nu se mapează `unsure` la `false`. În API-ul CSV curent confidence este folosit intern
de model, dar nu se expune în răspunsuri sau în CSV; coloanele contractuale rămân
neschimbate.

## D2 — Coloane de intrare și ieșire

Contractul juraților fixează schema de input (`id,text,date,label`) și output
`id,type,text,form,label,confidence`. Aplicația din plan e însă generică. Rezolvare pentru app:

- mapping obligatoriu înainte de job: coloana text (obligatorie), coloana dată (opțională
  în UI, dar necesară modelului; lipsa ei produce `unsure` + eroare),
  coloana id (opțională, altfel rândurile primesc `r-<index>` stabil), coloana rezultat.
- dacă coloana rezultat există, valorile ei sunt suprascrise în output; dacă nu există, se
  **adaugă** o coloană la final (permisiune explicită D2). CSV-ul original nu e modificat.
- ordinea coloanelor existente și ordinea rândurilor se păstrează.

## D2b — Schema de input primită: `id,text,date,label,form`

Echipa primește fișiere cu exact aceste cinci coloane, în această ordine (ex.
`data/practice.csv`). Backend-ul le tratează ca format de prim rang:

- header exact → `format: "practice"`, mapping fix (`text/date/id/label`) deja confirmat
  (nu mai e nevoie de pasul de mapping înainte de job);
- fiecare rând e validat: `id`/`text` ne-goale, `date` ISO `yyyy-mm-dd`, `label`
  gol sau `true|false|unsure`, `form` gol sau JSON array de `{subject, attribute,
  value}`; rândurile problematice nu blochează upload-ul, adaugă warning-ul
  `PRACTICE_ROW_ERRORS`;
- coloana `form` este păstrată neatinsă atât în snapshot, cât și în output-ul final;
  clasificatorul folosește textul și data mapate;
- CSV-urile generice rămân acceptate (`format: "generic"`, mapping confirmat manual).

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

## D6 — Strategie de inferență: adaptorul local fitted

Backend-ul folosește `backend/scripts/adapter.joblib`, prototipul local fitted
(SHA-256 `9200b1536c6df28609e4e8b36a3aaefc16a08cecf1278392d878f847d609fd2a`). Calea
implicită este `backend/scripts/adapter.joblib`; `NEURON_MODEL_PATH` o poate înlocui.
Modelul este încărcat și memorat în cache per proces și cale; după înlocuirea artefactului
la aceeași cale se repornește backend-ul. Artefactul lipsă sau imposibil de încărcat
înseamnă eșecul jobului cu `CLASSIFIER_UNAVAILABLE`; nu există fallback mock/demo și nu
se inventează etichete. Prototipul clasifică rândurile existente și nu generează claims.

Modelul cere text ne-gol și o dată ISO `yyyy-mm-dd`. Textul gol ori data lipsă/nevalidă
produce `unsure` și eroare structurată, fără completarea datei. Pentru o intrare validă,
eticheta este argmax între `true` și `false`; probabilitatea sub `0.5` produce `unsure`.
Confidence rămâne internă: API-ul și CSV-ul păstrează contractul actual, fără câmp nou.

Integrarea folosește procesarea locală pe rând și păstrează protocolul `Engine`,
`RowDecision`, evenimentele de job și deadline-ul existent. Toate coloanele și rândurile
CSV de intrare rămân în aceeași ordine; coloana rezultat mapată este suprascrisă sau
adăugată la final, iar celelalte câmpuri (inclusiv `form`) se păstrează.

## Decizia de cleanup a orchestratorului

Backend-ul rămâne orchestrator CSV în jurul modelului local: rutele orientate către
frontend, sesiunile, rezultatele și contractele externe rămân neschimbate. `Engine`
își păstrează dataclass-urile și protocolul `prepare/classify/close`, iar procesorul
păstrează semantica de streaming, progres, erori pe rând și deadline. Fabrica de engine
folosește setările aplicației; `NEURON_MODEL_PATH` selectează artefactul. Nu există
setări de URL, mod, token sau retry pentru un serviciu classifier.

Un singur job global per contract rămâne regula; nu există o setare de concurență
configurabilă. Dataset snapshots și rezultatele joburilor continuă să folosească
fișiere temporare, curățate la expirare.

## Abateri și lucruri neimplementate (conștient, în afara scopului acestui build)

1. **Claims (exact 1.000 propoziții noi)** — cerute de jurați pentru rularea Docker, dar în
   afara scope-ului aplicației CSV și neexpuse de API-ul din acest build. Prototipul local
   clasifică rândurile furnizate și nu generează claims.
2. **Dockerfile la rădăcină și scripts/check.sh** — interzise de constrângerea „doar
   `frontend/` și `backend/`”; nu se creează. Când se decide ambalarea, `backend/` are
   `requirements.txt` și instrucțiuni de rulare gata de copiat într-un Dockerfile.
3. **Editor de coloane / redimensionare / duplicare coloane în Manual** — planul le cere;
   build-ul livrează CRUD de rânduri + undo/redo + paste TSV. Coloanele sunt fixe
   `id,text,date`. Se adaugă dacă rămâne timp / la cerere.
4. **Search în loguri, pause/resume/cancel, upload reluabil, istoric permanent** — explicit
   excluse de plan (§1), nu se implementează.
5. **Persistență** — niciuna, conform planului §1/§11; starea trăiește în RAM + fișiere
   temporare curățate la expirare.
6. **Autentificare** — doar sesiune anonimă izolată, conform planului §10.
7. **Frontend dev server** — deja pornit pe 3000 de utilizator; nu se pornește altul. CORS
   permite exact originile de dezvoltare.

## Livrabile separate

- Claims și Docker rămân livrabile separate înainte de freeze. Acest migration note nu
  pretinde că root Dockerfile-ul sau runner-ul de claims au fost implementați.
