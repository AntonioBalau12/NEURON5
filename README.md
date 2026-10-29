# Hype Arena starter

## Run the NEURON5 frontend

The application lives in `frontend/`. From the repository root:

```sh
cd frontend
yarn install --frozen-lockfile
yarn dev
```

Open http://localhost:3000. Start the API separately using [backend/README.md](backend/README.md).
For a production build, run `yarn build` followed by `yarn start` inside `frontend/`.
The old static HTML previews, root Node server and duplicate assets have been removed.

## Run the full application in Docker

The image contains the production Next.js frontend, FastAPI backend and local model.
From the repository root, build and start both services with Docker Compose:

```powershell
docker compose up --build
```

Open http://localhost:3000 after the frontend and API report that they are ready.
Stop any local frontend or backend using ports 3000 and 8000 before starting the container.
Compose runs both services in the same container in `web` mode and binds their ports to localhost.
No local Node.js or Python installation is required. The frontend calls the API at http://localhost:8000.

Stop the application with Ctrl+C, or run this from another terminal:

```sh
docker compose down
```

The image still defaults to competition mode (`arena`) when run outside Compose:
it reads `/universe/universe.csv` and writes `/output/output.csv`, then exits.
The existing `scripts/check.sh` command continues to use arena mode without publishing web ports.

## Competition and jury run

Build the submission image from the repository root. The build may use the network;
the competition run is offline:

```sh
docker build --platform linux/amd64 -t neuron5:submission .
```

For a local run with the jury's input files, place `universe.csv` and `lexicon.json`
in `./universe/`. The output is written to `./output/output.csv`:

```sh
mkdir -p universe output
chmod 755 universe
chmod 777 output
deadline=$(($(date +%s) + 30 * 60))

docker run --rm --init --name neuron5-jury --platform linux/amd64 \
  --network none --read-only --user 10001:10001 \
  --cpus 2 --memory 6g --memory-swap 6g --pids-limit 256 \
  --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,size=128m,mode=1777 \
  -v "$PWD/universe:/universe:ro" -v "$PWD/output:/output" \
  -e ARENA_DEADLINE="$deadline" \
  neuron5:submission
```

The `chmod` commands prepare local host directories for the bind mounts: the input
is readable, and the output is writable by container user `10001`. They do not
change the image or make its read-only root filesystem writable. The official
`scripts/check.sh` uses the same permissions for its temporary mounts; the jury
provides its own mounts and permissions.

The image runs in its default `arena` mode: it reads `/universe/universe.csv` and
`/universe/lexicon.json`, then writes `/output/output.csv`. Do not set
`NEURON_MODE=web` for the competition run. The run is limited to 30 minutes; at the
deadline it receives `SIGTERM`, followed by a forced stop 10 seconds later.

Before submission, run the repository checker from a Bash shell with Docker and
Python 3 available. It builds an image when no tag is passed, hides every fifth
practice label, runs offline with the competition resource limits, and validates
the resulting table:

```sh
bash scripts/check.sh
```

The checker saves its result as `./output.csv`. It exercises the practice dataset;
the jury run uses the full mounted universe.

To run a custom CSV in `arena` mode, mount the file into the container and pass its
container path with `--csv=...`. The CSV must have `id`, `text`, `date` and `label`
columns. The packaged lexicon is used, and the result is written to `output/output.csv`:

```powershell
New-Item -ItemType Directory -Force .\output | Out-Null

docker run --rm --init --name neuron5-custom `
  --network none --read-only --tmpfs /tmp:rw,size=128m `
  -v "${PWD}\input.csv:/input/input.csv:ro" `
  -v "${PWD}\output:/output" `
  neuron5:local --csv=/input/input.csv
```

In `web` mode, upload the CSV through the frontend instead; `--csv` is an `arena`-mode argument.

## Final pipeline integration

The ML, retrieval and claim-generation code was merged from
`feat/p17-p2-p3-anytime-final` at commit `9c4c481c40c58fa568ef12afea1b91b1cff3f501`.
The default model is `ml/classical/results_m2_v2/model.joblib` with its serialized
calibration/abstention policy. Both the web classifier and `runner.py` use the
same M2 inference implementation: text/date features, temporal graph and BM25 evidence.
The previous adapter remains available through an explicit `NEURON_MODEL_PATH` override.
Runtime dependencies pin scikit-learn 1.9.1, matching the final artifact. The older
version described in the historical P3 integration report applies to previous models.

During `docker build`, `scripts/build_reference_graph.py` populates
`/app/artifacts/reference_graph.pkl` from the packaged practice dataset and lexicon.
The snapshot preserves verified evidence, unverified candidates, dates and source IDs;
its source fingerprints are checked before reuse. Local development builds the graph
in memory when no matching snapshot exists. Only trusted, application-built snapshots
may be supplied through `NEURON_GRAPH_SNAPSHOT`.
The web API preloads this reference graph during startup and retains it for the process
lifetime. The arena runner preloads the same graph and builds its `/universe` P3 store
once before inference, then reuses it throughout claim generation.

M2 retrieval uses reference evidence only, matching the final model's calibration.
Runtime query rows exclude their own evidence IDs. P3 separately builds its runtime
graph from the mounted universe plus reference evidence; new unlabeled rows are never
promoted to verified support by a prediction. Its anytime runner writes validated,
atomic classification and claim checkpoints to `/output/output.csv`.

The web API retains its mapped-input CSV output and runs M2 classification. Full P3
claim generation runs in `arena` mode. It can publish fewer than 1,000 verified claims
when evidence is insufficient; a successful partial run is not full competition compliance.

## [hype-arena.vercel.app](https://hype-arena.vercel.app/)

## The universe

**Hooly** is a fictional company in a fictional universe, made for the QA DNA challenge of the NEXXT AI Hackathon. Its name alludes to Hooli, the tech giant of the TV series *Silicon Valley*. Its products carry the names of real Google products, used fictitiously: nothing here describes those products or their makers. Its people carry the names of the series' characters with a few letters changed.

Hooly's people, events, decisions and figures are invented, and the universe departs from the series and from Google's real history on purpose. **The truth is what the universe says.** A system that fills gaps from the web, or from what a pretrained model already knows, learns facts the universe contradicts.

The universe is a year of Hooly's pages, docs, posts, decks and press releases, in which prices, headcounts, dates and names change, and some pages lie. You get a part of it as sentences, each labelled.

## The task

Build a system that does two things with rows about Hooly, each with how sure your system is:

- **It labels rows.** Given rows of the universe, some labelled and some not, it labels each unlabelled row `true`, `false` or `unsure`.
- **It writes new content.** It writes exactly 1,000 new claims about Hooly that connect what the universe says, every one of them true.

How you build it is yours to decide.

- **LLMs may help you build your system,** and make what it learns from, but the system itself may not be an LLM.
- **Fork this repository and work in your fork,** so we can follow your work. Forks are public.
- **Your system has a frontend:** a working page that shows the architecture of your system as a diagram and runs the system live on rows you give it. Start it however you like: your video shows it running.
- **At 09:00 on 29 Oct we add a sample of 20 rows to this repository,** as one CSV file, `sample/sample.csv`: new rows, in the shape of the run's input with every `label` empty (`id`, `text`, `date`, `label`). The video you hand in at 11:00 shows your frontend running your system live on them, beside its architecture diagram.
- **Your submission is a pull request** from your fork to this repository, one per team, titled with your team's name and opened before 11:00 on 29 Oct. It holds both the `Dockerfile` we run your system from, as [`contracts/README.md`](contracts/README.md) says, and what starts your frontend. What it holds at 11:00 is what we run: a push to it, or closing it, after 11:00 disqualifies the team.
- **We run every team's system** after 11:00, offline, for up to 30 minutes, on about 20,000 rows of the universe, the practice rows among them with their labels. It hands in one table, `/output/output.csv`: a label for each of the roughly 18,000 unlabelled rows and exactly 1,000 new claims, every one true, and we judge both. How it runs, what it reads and what it hands in is in [`contracts/README.md`](contracts/README.md).

## What is here

| Path | What |
| --- | --- |
| `data/practice.csv` | The practice dataset: one row per sentence of the practice part of the universe, each labelled `true`, `false` or `unsure`, with the facts it states |
| `data/lexicon.json` | The subjects the dataset names, with their aliases and attributes, and the events |
| `contracts/` | What you get, how we run your system and what it hands in |
| `sample/sample.csv` | From 09:00 on 29 Oct: the 20 rows of the sample, unlabelled |
| `scripts/check.sh` | Runs your system as we will, on the practice data, and checks its table |

## Check your system

`scripts/check.sh` builds the image from your `Dockerfile` and runs it as we will: offline, as user 10001, on a read-only root, with 2 CPUs and 6 GiB, until it exits or 30 minutes pass. Its input is the practice dataset in the run's shape, with every fifth row's label hidden. It then checks your table's columns, ids, lengths, labels and confidences, that it holds exactly 1,000 new claims, and counts your labels on the hidden rows against the practice labels. It needs Docker and Python 3.

It does not check a claim's text against `claim-forms.md`, its form against `entry.schema.json`, or its names against the lexicon: we check those after the run. And an image that holds `data/practice.csv` knows the hidden labels, so the label count here is an upper bound.

```sh
scripts/check.sh                 # build the image and run it
scripts/check.sh my-image:tag    # run an image you built
MINUTES=5 scripts/check.sh       # a shorter run
```

A run that passes here can still fail ours on what the practice data does not hold.
