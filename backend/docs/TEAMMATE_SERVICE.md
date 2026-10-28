# Ce trimite backend-ul către serviciul de clasificare al colegilor

Backend-ul (FastAPI, `backend/`) **nu clasifică local**. La fiecare job face un
singur request HTTP către serviciul echipei de clasificare și stochează răspunsul
ca tabelul de rezultat al jobului.

> Notă: cât timp `NEURON_CLASSIFIER_URLS` nu e setat, backend-ul folosește mock-ul
> intern DEMO (`app/engine/mock_engine.py`) și frontend-ul funcționează complet, cu
> avertisment „DEMO classifier” în logul jobului. Nu trebuie pornit niciun proces separat.

## Configurare (fără cod)

```sh
NEURON_CLASSIFIER_URLS=http://<host>:<port>/<path>   # obligatoriu; listă cu virgule = fallback
NEURON_CLASSIFIER_MODE=csv                            # csv (default) | rows
NEURON_CLASSIFIER_FIELD_NAME=file                     # numele câmpului multipart
NEURON_CLASSIFIER_TIMEOUT_SECONDS=1800
NEURON_CLASSIFIER_TOKEN=<bearer>                      # opțional
```

## Request

### mode=csv (recomandat pentru „fișier CSV direct”)

`POST <url>`, `multipart/form-data`:

| câmp | valoare |
| --- | --- |
| `file` (sau `NEURON_CLASSIFIER_FIELD_NAME`) | snapshot-ul CSV al datasetului (UTF-8, virgulă, header inclus: `id,text,date,label,form`) |
| `asOf` | data de referință, ex. `2026-10-29` |
| `mapping` | JSON string: `{"textColumn","dateColumn","idColumn","resultColumn"}` |

### mode=rows

`POST <url>`, `application/json`:

```json
{
  "asOf": "2026-10-29",
  "mapping": {"textColumn": "text", "dateColumn": "date", "idColumn": "id", "resultColumn": "label"},
  "columns": ["id", "text", "date", "label"],
  "rows": [{"id": "p-1", "text": "...", "date": "2026-01-12", "label": "", "form": "[{...}]"}]
}
```

## Răspuns acceptat (oricare formă)

1. **CSV direct** (`Content-Type: text/csv`) — tabelul final complet.
2. `{"csv": "<conținut CSV>"}`
3. `{"columns": [...], "rows": [[...], ...]}`
4. `{"rows": [{"<coloanele originale>": "...", "label": "true|false|unsure"}, ...]}`
5. `{"results": [{"id": "...", "label": "true|false|unsure", "confidence": 0.9}, ...]}`
   — etichete înguste; backend-ul le îmbină cu snapshot-ul (păstrează coloanele,
   ordinea și numărul de rânduri; coloana rezultat se completează sau se adaugă).
6. listă JSON de obiecte (ca la 4/5) sau obiect cheiat pe id.

Etichete: `true`, `false`, `unsure` (acceptă și `unknown`/`uncertain` → `unsure`).
`confidence` 0.5–1 pentru `true`/`false`, gol pentru `unsure`.
Rezultatul trebuie să păstreze rândurile snapshot-ului (număr și ordine) și coloana
rezultat; altfel jobul eșuează `INVALID_OUTPUT` (vezi `API_CONTRACT.md` §7).

## Verificare rapidă

```sh
cd backend
python -m app.engine.cli --input ../data/practice.csv --output /tmp/out.csv \
    --classifier-url http://<host>:<port>/<path>
```

Până e gata serviciul real: `python -m app.mock_classifier` pe
`http://127.0.0.1:8010/classify` (etichete DEMO, marcate ca atare).