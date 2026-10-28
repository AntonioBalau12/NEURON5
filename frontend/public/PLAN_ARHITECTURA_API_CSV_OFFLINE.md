# Plan de implementare — Aplicație offline de clasificare a propozițiilor din CSV

**Statut:** document de predare pentru agenți de dezvoltare. **Nu este cod și nu impune un framework.**

## 0. Cum trebuie folosit acest document

Agentul care preia implementarea trebuie mai întâi să inspecteze repository-ul, stack-ul, modulele, algoritmii, instrucțiunile de evaluare și comportamentul efectiv al procesorului. Acest plan descrie **contracte, responsabilități, invariabile și teste**, nu presupune că anumite biblioteci sau fișiere există. Dacă proiectul contrazice o presupunere, agentul documentează diferența înainte de a modifica arhitectura. Nu se implementează totul într-un singur pas: fiecare etapă trebuie validată independent.

## 1. Obiectiv și constrângeri ferme

- Aplicația primește un CSV și clasifică propoziții ca `true`, `false` sau `unsafe`. Utilizatorul a cerut și `unsure` ca rezultat de rezervă pentru rândurile care nu pot fi procesate. **Compatibilitatea lui `unsure` cu schema cerută de jurați este o decizie blocantă**, nu o presupunere.
- Frontend viitor: **Next.js + TypeScript**, cu trei ecrane: (1) editare manuală / upload bulk; (2) procesare și loguri live; (3) rezultate și descărcare.
- Backend, frontend, API și motor de procesare sunt livrate în **același proiect și aceeași imagine/container Docker**. Pot exista mai multe module/procese interne dacă sunt justificate, dar nu se cer servicii externe.
- **Offline complet:** fără internet, API keys, modele descărcate la pornire, baze de date externe sau servicii cloud. Toate modelele, regulile și artefactele necesare trebuie incluse în imagine.
- Resurse de referință: **2 vCPU, 6 GB RAM**; procesarea unui job are buget maxim de **30 de minute**.
- Un utilizator probabil, o singură execuție activă la un moment dat; o singură încărcare bulk; o singură sesiune poate fi observată din mai multe taburi, în limita resurselor.
- **Fără bază de date sau persistență durabilă.** Sesiunile, job-urile și logurile există temporar în memoria procesului. Sunt permise fișiere temporare în container pentru upload/output de dimensiuni mari, șterse după folosire; acestea nu reprezintă stocare permanentă. Restartul containerului pierde tot.
- Rezultatul este **CSV**, disponibil după finalizare, pentru vizualizare read-only și download. Nu se promite recuperare după refresh/restart.
- Nu intră în prima versiune: login, editare bulk, procesare multiplă, pause/resume/cancel din UI, relansarea job-urilor, upload reluabil, istoric permanent sau servicii externe.

## 2. Decizii deschise cu impact asupra contractului

**D1 — Etichetele:** trei etichete declarate (`true`, `false`, `unsafe`) versus `unsure` pentru eșecuri / lipsă de certitudine. Se verifică mai întâi formatul cerut de evaluatori. Nu se mapează `unsure` artificial la `unsafe` ori `false`.

**D2 — Coloanele de intrare și ieșire:** schema CSV este necunoscută, dar outputul trebuie să păstreze numărul de rânduri, ordinea și coloanele. Este imposibil să scriem o etichetă dacă fișierul nu are coloană destinată rezultatului și nici nu putem adăuga una. Contractul trebuie să precizeze: coloană de propoziție, coloană de rezultat existentă **sau** permisiunea explicită de a adăuga o coloană nouă. La detectare ambiguă, se cere selecția coloanei în UI, fără modificarea celulelor în Bulk.

**D3 — Sensul `unsafe`:** trebuie definit după regulamentul competiției. Conținutul periculos, lipsa dovezilor și eroarea tehnică sunt categorii distincte. Regulile de clasificare și exemplele de referință sunt responsabilitatea componentei de inferență.

**D4 — Delimitatorul:** se preferă autodetectare pentru formatele uzuale (virgulă, punct și virgulă, tab), cu preview și confirmare dacă detectarea este ambiguă; encodingul suportat este UTF-8, inclusiv opțional BOM.

**D5 — Ce înseamnă «păstrarea formatului»:** implicit se păstrează schema logică, ordinea coloanelor/rândurilor și valorile nemodificate, nu identitatea byte-cu-byte a ghilimelelor sau newline-urilor. Dacă evaluarea cere identitate byte-cu-byte, implementarea trebuie adaptată.

**D6 — Strategia de inferență offline:** agentul inspectează implementarea existentă și dovedește că poate funcționa cu resursele date. Nu se presupune că un LLM local poate verifica în mod fiabil orice afirmație factuală, mai ales afirmații recente sau fără context. Când nu există suficiente dovezi, se aplică politica de abstinență definită prin D1.

## 3. Separarea responsabilităților

Fluxul logic este: **UI → API versionat → administrare sesiune / dataset → orchestrator job → procesor CSV și motor de clasificare → rezultat temporar → API de rezultate**. Pe lateral, orchestratorul publică **evenimente structurate → buffer temporar → WebSocket → Slide 2**.

Modulele logice recomandate, fără impunerea structurii de foldere:

1. **Session manager:** emite sesiuni fără login, le delimitează și verifică accesul la resurse.
2. **Dataset manager:** primește, validează, inspectează și expune preview pentru inputul manual sau bulk.
3. **Job orchestrator:** alocă job ID, aplică idempotency, limite de concurență, deadline și tranziții de stare.
4. **CSV engine:** parser incremental, identificatori stabili de rând, păstrarea ordinii, serializare și scriere incrementală de output.
5. **Classification engine:** interfață independentă pentru inferență offline; primește o propoziție/context explicit și întoarce decizie + metadate/eroare, fără a cunoaște HTTP sau WebSocket.
6. **Event service:** normalizează loguri, statistici și progres în evenimente numerotate; difuzează către clienți și limitează memoria.
7. **Results service:** summary, preview read-only, detaliile erorilor și streaming pentru CSV-ul final.
8. **Frontend:** trei slide-uri; gestionează CRUD și Undo în memoria browserului înainte de Save și observă job-ul după pornire.

**Regulă:** API-ul se modelează pe resurse și procese, **nu** pe numele slide-urilor. Procesorul trebuie să poată fi executat și testat fără browser, printr-un punct de intrare local/CLI sau interfață internă echivalentă, conform regulilor jurizării.

## 4. Modelul de domeniu și ciclul de viață

- **Session** — ID/token aleator, scope pentru resursele temporare, expirare; nu reprezintă identitate autentificată.
- **Dataset** — ID, mod (`manual`/`bulk`), metadate CSV, schemă detectată/mappată, dimensiune, număr de rânduri când este disponibil; inputul devine **snapshot imuabil** când se creează un job.
- **Job** — ID, dataset ID, progres, timp de început/deadline/final, contori, stare și motiv de eșec; un job nu poate fi pornit de două ori accidental.
- **Event** — ID secvențial per job, timestamp UTC, nivel, tip, componentă, pas, mesaj și metadate structurate; referință opțională către rând.
- **Result** — output CSV temporar, statistici și listă structurată de erori, accesibile doar după finalizare validă.

Stări interne recomandate: `queued → running → finalizing → succeeded | failed | cancelled`. Cele **trei stări terminale** sunt distincte de etichetele pe rând. `cancelled` este rezervată pentru anulări interne / extindere viitoare și nu cere acum buton în UI.

**Politică de eșec:** o eroare izolată de rând nu oprește job-ul; acel rând primește eticheta de fallback **doar dacă este permisă de D1**. Un job poate ajunge `succeeded` cu avertismente și contori de rânduri nereușite, atât timp cât rezultatul CSV este complet și valid. Eșecurile de infrastructură, de parsing nerecuperabil sau imposibilitatea de a genera outputul complet duc la `failed`. Nu se pretinde succes când fișierul este corupt sau incomplet.

**Deadline:** bugetul de 30 min acoperă inferența și finalizarea fișierului. Procesorul trebuie să păstreze timp pentru scrierea rândurilor rămase cu fallback (când fallbackul este permis), flush și validarea outputului; altfel marchează job-ul `failed` cu motiv `timeout`. Nu se promite procesarea semantică a tuturor rândurilor din 10 MB în 30 min.

## 5. Propunere de API REST, v1

Endpoint-urile sunt **contracte orientative**, de adaptat la framework-ul găsit în proiect. Toate răspunsurile JSON trebuie să aibă structuri stabile și identificatori consistenți.

| Domeniu | Rută propusă | Rol |
|---|---|---|
| Sesiune | `POST /api/v1/sessions` | Creează/returnează sesiunea temporară și cookie-ul/tokenul |
| Sesiune | `GET /api/v1/sessions/current` | Verifică sesiunea activă, fără login |
| Manual | `POST /api/v1/datasets/manual` | Save pentru draftul din frontend, validare și snapshot de dataset (max. 1 MB CSV serializat) |
| Bulk | `POST /api/v1/datasets/bulk` | Upload multipart cu un CSV (max. 10 MB) |
| Dataset | `GET /api/v1/datasets/{id}` | Metadate, schema detectată, dimensiune, validare |
| Dataset | `GET /api/v1/datasets/{id}/preview` | Preview paginat/read-only; pentru mapping și verificare |
| Dataset | `PUT /api/v1/datasets/{id}/mapping` | Stabilește/confirmă coloana propoziției și destinația rezultatului **înainte** de a crea jobul; modifică metadate, nu CSV-ul Bulk |
| Job | `POST /api/v1/jobs` | Pornește asincron procesarea unui dataset salvat; folosește `Idempotency-Key` |
| Job | `GET /api/v1/jobs/{id}` | Stare curentă, progres, counters, deadline, status final |
| Realtime | `GET /api/v1/jobs/{id}/stream` | Upgrade la WebSocket și handshake pe job |
| Rezultate | `GET /api/v1/jobs/{id}/result/summary` | Statistici și disponibilitatea outputului |
| Rezultate | `GET /api/v1/jobs/{id}/result/preview` | Preview paginat al CSV-ului final, doar read-only |
| Rezultate | `GET /api/v1/jobs/{id}/result/errors` | Erori și rânduri cu fallback, paginate |
| Export | `GET /api/v1/jobs/{id}/result.csv` | Download CSV prin streaming după finalizare |
| Observabilitate | `GET /api/v1/jobs/{id}/events` | Istoricul temporar al evenimentelor, inclusiv pentru exportul logurilor din UI |

Comportamente contractuale obligatorii:

- `POST /jobs` răspunde repede cu **job ID + stare inițială**, fără să aștepte inferența. Clientul navighează apoi în Slide 2 și deschide WebSocketul. Jobul este respins până la confirmarea mapping-ului de coloane și a validării. Mapping-ul nu se mai poate schimba după creare.
- Fiecare resursă are proprietarul **session ID**; un token din altă sesiune nu poate vedea rezultatele/jobul.
- Dacă există job activ și nu avem capacitate, răspunsul este clar (`409 Conflict` ori `429 Too Many Requests`, convenit și testat), nu pornirea necontrolată a unui al doilea worker.
- Upload invalid, sesiune absentă, ID necunoscut, rezultat încă indisponibil și limită depășită au coduri HTTP corecte și coduri de eroare **stabile** (`INVALID_CSV`, `DATASET_TOO_LARGE`, `JOB_NOT_READY`, `JOB_ALREADY_RUNNING` etc.).
- Toate operațiile semnificative produc `requestId` / `jobId` pentru corelarea diagnosticelor.
- Niciun endpoint nu expune datele complete pentru Bulk într-un răspuns JSON gigantic: previewurile și erorile sunt paginate, CSV-ul se descarcă prin stream.
- `Idempotency-Key` este reținut temporar pe sesiune; aceeași cheie și același payload întorc același job, iar reutilizarea cu payload diferit produce conflict.
- Eliminarea/deconectarea browserului **nu** oprește automat jobul.

## 6. Slide 1 — Manual și Bulk

**Manual:** tabelul pornește gol. Frontend-ul implementează CRUD pentru celule, rânduri, coloane, redenumire, reordonare, duplicare, selecție și copy/paste din foi de calcul. Undo/Redo există **doar în frontend**. Modificările sunt un draft local; butonul **Save** validează și trimite starea finală către `datasets/manual`. Limita de 1 MB se măsoară pe CSV-ul UTF-8 rezultat, nu doar pe dimensiunea obiectului JSON. Nu impunem limite arbitrare de rânduri/coloane, dar aplicăm protecții operaționale împotriva consumului excesiv de memorie.

**Bulk:** upload-ul acceptă **un singur CSV**, max. **10 MB**, fără editare. Serverul oferă metadate, număr de rânduri/coloane dacă se poate calcula eficient, header-ele, preview read-only și diagnostice de parsare. Folosește parsing incremental și nu încarcă obligatoriu tot fișierul în RAM. Dacă upload-ul eșuează, utilizatorul reîncepe de la zero. Nu se lansează alt bulk în timpul jobului.

**În ambele moduri:** definirea coloanei care conține propoziția și a destinației rezultatului este obligatorie înainte de rulare, prin autodetectare **confirmabilă** sau mapping explicit. Parserul suportă CSV corect cotat, câmpuri cu virgule/newline interne, UTF-8 și BOM dacă există. Datele CSV sunt tratate exclusiv ca **date**, niciodată ca instrucțiuni pentru sistem sau cod executabil. Nu se schimbă ordinea rândurilor.

La Process, datasetul salvat devine snapshotul jobului. În v1 nu se editează snapshotul și nu se relansează jobul; pentru un nou test se inițializează un nou dataset/draft.

## 7. Motorul de procesare și politica de clasificare

Se definește un contract intern: **input de rând + schemă/mapping + context permis → etichetă validă sau eroare structurată**. Implementarea concretă poate folosi reguli, modele locale, verificare deterministă, un pipeline hibrid sau cod existent; alegerea este condiționată de benchmarkurile offline pe **2 vCPU / 6 GB RAM**.

Cerințe:

1. Un rând dificil nu blochează restul rândurilor (**best effort**); există timeout pe rând/pas și capturare de excepții.
2. Nu inventează certitudine în lipsa informației. Pentru fapte dependente de data curentă, evenimente externe sau afirmații ambigue, rezultatul trebuie să urmeze politica D1/D3.
3. `unsafe` nu este sinonim cu „nu știu” și nici cu „rând invalid”; semantica se validează cu jurații.
4. Se protejează ordinea outputului chiar dacă inferența este paralelizată; identificarea unui rând este stabilă și independentă de ordinea de completare.
5. Se începe cu **o singură execuție globală** și paralelism intern conservator; nivelul de concurență este configurabil și decis prin măsurători (CPU, memorie, latență), nu ales arbitrar.
6. Numărul total de rânduri, rândurile procesate, cele reușite, cele cu fallback și erorile sunt contabilizate fără dublare.
7. Scrierea rezultatului este incrementală, în fișier temporar; la sfârșit se verifică header-ele, ordinea și numărul de rânduri.

**Avertisment important:** 10 MB poate însemna foarte multe propoziții. O clasificare factuală universală și exactă, offline, pe CPU limitat, într-un timp fix, **nu poate fi garantată** doar din arhitectura API. Agenții trebuie să măsoare rata de procesare și calitatea clasificării pe seturi reprezentative, fără a presupune că simpla integrare a unui LLM rezolvă problema.

## 8. Slide 2 — Evenimente live și loguri

**Opțiune principală:** WebSocket per job (SSE poate fi păstrat ca posibilă alternativă dacă analiza proiectului demonstrează că e mai simplu). Conexiunea se deschide **după** obținerea job ID-ului.

Protocol conceptual:

1. Clientul deschide WebSocket cu sesiunea activă și job ID. Serverul verifică dreptul de acces.
2. Handshake-ul confirmă versiunea protocolului, job ID, statusul curent, ultimul `sequenceId`, capacitatea de replay și opțional timestampul serverului.
3. Se trimite **snapshot de stare** plus evenimentele încă disponibile din buffer, apoi flux live; acest buffer acoperă intervalul dintre `POST /jobs` și conectare.
4. Evenimentele au forme stabile precum `job.started`, `step.started`, `step.completed`, `row.failed`, `progress.updated`, `log.recorded`, `job.completed`, `job.failed`, `heartbeat`.
5. Fiecare eveniment conține `sequenceId`, timestamp UTC ISO 8601, severity, componentă, pas, mesaj, `jobId`, date structurate și, unde există, `rowId`, durată, retry count ori stack trace.
6. Progresul combină **stadiul logic** cu `processedRows / totalRows` și procentul numai dacă numitorul este cunoscut; nu se inventează procentul.
7. Evenimentele frecvente se livrează **în batch-uri** cu limite clare; tranzițiile și erorile critice se transmit prompt. UI folosește listă virtualizată pentru volume mari.
8. Ultimul eveniment terminal este emis **după ce** fișierul rezultat este complet și gata de citit; abia apoi UI trece în Slide 3.

**Reconectare:** userul nu cere recuperare după refresh, dar pentru întreruperi scurte în aceeași sesiune este util un `lastSequenceId` și un ring buffer **limitat** în RAM. Dacă bufferul a eliminat evenimente vechi, serverul semnalează explicit un `gap` și retrimite un snapshot; nu pretinde că istoricul este complet. La restart se pierd logurile și joburile. Mai multe taburi pot observa același job fără a crea execuții noi.

Niveluri disponibile în UI: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`. UI are filtre pe nivel, tip/componentă și export de loguri **cât timp sunt în buffer**, fără search în v1. Se stabilește o limită de memorie pentru loguri și se afișează dacă au fost trunchiate. Nu se promite păstrarea nelimitată a tuturor mesajelor în 6 GB RAM.

## 9. Slide 3 — Rezultate

Se afișează **numai după starea terminală** și, pentru output, doar când fișierul este complet. Conținut: statusul jobului, durata, total rânduri, succes, `unsure`/fallback dacă permis, erori și motivul degradării sau al eșecului. Tabelul este **read-only** și paginat. Erorile tehnice sunt afișate separat cu `rowId`, număr logic de rând, coloană (dacă se cunoaște), cod și mesaj; ele nu se confundă cu eticheta `unsafe`.

Downloadul livrează **doar CSV-ul final**, cu `Content-Type` și nume de fișier coerente; transportul este streaming. JSON pentru statistici și erori servește doar UI-ului, nu se descarcă automat ca artefact separat. Outputul poate exista temporar până la finalizarea downloadului și o **scurtă perioadă de grație** pentru retry; apoi se elimină. Nu există istoric permanent și nu se garantează recuperarea după refresh.

## 10. Sesiuni, securitate și comportament HTTP

Prima accesare creează o sesiune anonimă cu token **criptografic aleator**, preferabil prin cookie `HttpOnly`, `SameSite` și `Secure` când se folosește HTTPS. Este un mecanism de **izolare a sesiunilor, nu de autentificare**. Se verifică sesiunea la toate rutele de dataset, job și WebSocket. Se validează `Origin` pentru WebSocket, se aplică protecție anti-CSRF pentru cererile cu efect și nu se configurează CORS permisiv inutil dacă frontend și API sunt pe aceeași origine.

Autorizarea se implementează printr-un strat înlocuibil, astfel încât ulterior să poată fi adăugat un proxy de acces/identitate fără rescrierea rutelor. Nu se presupune că un simplu token de sesiune este echivalent cu autentificarea oferită de Cloudflare. Erorile sunt tipizate și consistente: cod HTTP, `error.code`, mesaj lizibil și detalii limitate, `requestId`.

Se tratează CSV-ul ca input neîncredere: fișier prea mare, header invalid, encoding incorect, delimitator ambiguu, câmpuri monstruoase și output cu valori ce ar putea fi interpretate ca formule de un spreadsheet. Datele text se escapă corect în UI; procesorul nu execută instrucțiuni aflate în celule. Agenții documentează orice transformare a valorilor care ar afecta fidelitatea exportului.

## 11. Bugete, performanță și curățare

- Setări configurabile: `manualMaxBytes = 1 MB`, `bulkMaxBytes = 10 MB`, `maxConcurrentJobs = 1`, `jobDeadline = 30 min`, limite pentru bufferul de evenimente, sesiuni și previewuri.
- Rezervă de memorie pentru server/UI și runtime; orice model offline trebuie încărcat și testat în **6 GB total**, nu doar în memoria procesorului.
- CSV parsing, preview și export sunt incrementale; evenimentele sunt bounded; procesarea folosește backpressure.
- Cleanup pentru uploaduri temporare, outputuri, sesiuni expirate și joburi terminale după perioada de grație; inclusiv pe căi de eroare.
- Containerul nu depinde de internet la build final / run. Se verifică separat faptul că accesul browserului la serverul local funcționează chiar când accesul outbound la internet este blocat.
- Logs către UI sunt efemere. Eventuala diagnosticare standard a procesului din stdout/stderr nu devine o bază de date a aplicației.

## 12. Ordinea etapelor pentru agenți și criterii de acceptare

### Etapa A — Audit și contract

- Inspectează repository-ul, algoritmul, formatele de input/output, limitele runtime, modul de pornire în Docker și documentația juraților.
- Rezolvă sau consemnează explicit D1–D6. Definește contractul CSV, tabelul de erori, mașina de stări, evenimentele și forma răspunsurilor HTTP.
- **Gata când:** există un document scurt de contract, exemple CSV de input/output și un test de acceptare asupra unei propoziții valide, uneia `unsafe` și unei erori tehnice.

### Etapa B — Procesorul independent

- Izolează motorul de clasificare de HTTP/UI; implementează parsing/serializare incrementală, fallbackul permis și contorii.
- Validează modelele offline, termenul de 30 min și memoria maximă; testează ordinea și numărul de rânduri.
- **Gata când:** același procesor transformă fișiere de test fără browser, internet sau chei de API și respectă contractul de output.

### Etapa C — Sesiuni, dataseturi și upload

- Implementează sesiunea anonimă, upload Manual și Bulk, validare, schema mapping, metadate și previewuri paginate.
- **Gata când:** Manual acceptă Save ≤1 MB, Bulk acceptă un CSV ≤10 MB, datele invalide produc erori clare și nu există consum necontrolat de RAM.

### Etapa D — Job orchestration și API

- Adaugă `POST /jobs`, idempotency, limită la o execuție activă, status, deadline, snapshot și cleanup.
- **Gata când:** un job rulează asincron, dublu-click-ul nu creează două joburi, iar un rând greșit nu oprește procesarea celorlalte.

### Etapa E — Telemetrie și WebSocket

- Implementează evenimentele structurate și numerotate, handshake, snapshot, buffer bounded, heartbeat, fan-out pentru mai multe taburi și semnalizare de gaps.
- **Gata când:** clienții văd progres și erori live, o deconectare temporară nu strică jobul, iar traficul intens nu blochează UI sau procesorul.

### Etapa F — Result API și descărcare

- Implementează summary, preview read-only, erori paginate și export CSV incremental; elimină artefactele la expirare.
- **Gata când:** downloadul este disponibil doar după completarea outputului, iar CSV-ul păstrează contractul de schemă și rânduri.

### Etapa G — Frontend Next.js + TypeScript

- Slide 1: Manual editor cu Undo/Redo, Save, paste tabular, switch Manual/Bulk, validare, upload, preview și mapping.
- Slide 2: status, progress, log viewer virtualizat, filtre, exportul evenimentelor disponibile, reconnect în aceeași vizită.
- Slide 3: sumar, erori, tabel output read-only și buton Download.
- **Gata când:** UI consumă API-ul fără să dubleze logica de procesare sau să cunoască detalii interne ale modelului.

### Etapa H — Docker, testare și predare

- Construiește imaginea unică, include frontendul build-uit și toate artefactele procesorului, pornește totul cu o comandă documentată; fără downloaduri la startup.
- Testează e2e în constrângerile 2 CPU / 6 GB / fără internet, cu intrări normale, volum mare, CSV citat cu newline în câmp, encoding invalid, job timeout, refresh, două taburi, upload eșuat, erori de inferență, restart și output.
- **Gata când:** evaluatorul poate porni imaginea doar cu instrucțiunile furnizate, poate procesa un CSV și poate descărca outputul fără servicii externe.

## 13. Matrice minimă de teste de acceptare

| Scenariu | Comportament așteptat |
|---|---|
| Manual gol → editare → Undo → Save | Datasetul salvat corespunde doar draftului final, în limita de 1 MB |
| Bulk 10 MB valid | Upload și preview fără blocarea procesului sau încărcarea obligatorie integrală în RAM |
| Bulk >10 MB | Refuz explicit, fără job și fără fișiere temporare abandonate |
| CSV cu header, delimitatori și câmpuri citate | Parsing stabil; păstrarea ordinii și a valorilor logice |
| Coloana propoziției ambiguă | Mapping clar înainte de Process, fără alegere arbitrară |
| Un rând produce excepție | Restul se procesează; acel rând primește fallbackul permis și o eroare structurată |
| Două cereri de Process cu aceeași cheie | Un singur job creat |
| Două taburi urmăresc același job | Ambele văd același ID/progres, fără job suplimentar |
| WebSocket cade | Procesarea continuă; reconnect în aceeași sesiune cu snapshot și eventual gap |
| Loguri multe | Utilizare RAM limitată, batch-uri și semnalizare de trunchiere |
| Deadline 30 minute | Finalizare validă cu fallback unde este posibil sau `failed` explicit, niciodată output incomplet prezentat ca succes |
| Download înainte de final | Răspuns controlat `JOB_NOT_READY` |
| Download după final | CSV complet, forma convenită, ordinea și numărul de rânduri corecte |
| Refresh/restart | Nu se promite recuperare; restartul curăță toată starea efemeră |
| Fără internet și fără chei API | Aplicația și procesarea funcționează local, în resursele date |

## 14. Definiția globală de „Done”

Implementarea este acceptabilă doar când: **(a)** contractul de etichete și mapping este stabilit conform evaluării; **(b)** procesorul offline este testat separat și conservă outputul; **(c)** Manual/Bulk folosesc același motor; **(d)** API-ul este versionat, coerent, limitat și idempotent; **(e)** joburile sunt asincrone și monitorizabile live; **(f)** rezultatele sunt descărcabile numai după validare; **(g)** memoriile și fișierele temporare sunt curățate; **(h)** un singur container funcționează fără rețea externă și fără API keys; **(i)** testele e2e verifică scenariile și limitele. Orice decizie nerezolvată trebuie trecută într-un fișier de decizii, nu ascunsă în presupuneri ale codului.

## 15. Instrucțiuni de handoff pentru agenții care lucrează în paralel

Nu se distribuie sarcini pe foldere presupuse, ci pe **responsabilități și contracte**. Un agent poate descoperi o arhitectură diferită în repository; atunci adaptează locațiile, păstrând contractele.

- **Agent Contract/Architecture:** citește regulile competiției și implementarea existentă; soluționează D1–D6, definește contractul CSV/HTTP/WebSocket și testele de interfață între module. Este singurul care poate aproba schimbări incompatibile în contract.
- **Agent Processing:** deține parserul, schema mapping, inferența offline, fallbackul, integritatea outputului și benchmarkurile. Nu modifică protocoalele web fără acordul agentului de contract.
- **Agent API/Runtime:** deține sesiuni, dataseturi, joburi, idempotency, concurență, timeouts, fișiere temporare și endpointurile de rezultate. Folosește procesorul ca modul independent.
- **Agent Realtime/Observability:** deține formatul evenimentelor, bufferul temporar, handshake-ul, WebSocketul, progresul și livrarea controlată către UI. Nu introduce persistență durabilă.
- **Agent Frontend:** deține editorul Manual, upload/preview Bulk, log viewer și pagina de rezultate; consumă doar contractele API, fără acces direct la implementarea procesorului.
- **Agent QA/Container:** validează imaginea Docker completă, operarea offline, limitele 2 CPU/6 GB, deadlineul 30 min și matricea de teste end-to-end.

**Ordinea dependențelor:** Contract → Procesor (poate fi testat independent) + schelet API → integrarea Job/API → Realtime + Results → Frontend → QA final. După fiecare etapă, agentul livrează: (1) modificările implementate, (2) testele rulate și rezultatul lor, (3) incompatibilitățile/deciiziile rămase, (4) instrucțiuni scurte de integrare pentru următorul agent. Evitați rescrierile extinse ale codului existent fără motiv documentat.
