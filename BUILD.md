# Build and runtime

## Current frontend

The existing frontend is static HTML, local assets and `server.js`. It has no
dependencies or compilation step: `npm start` runs `node server.js`.
`Dockerfile.frontend` packages that application using an official Node 24 image
pinned by digest. It copies only the server and its public assets; it does not
copy repository metadata, datasets or credentials.

Container build and runtime verification are still pending.

Build from the repository root with Docker running in Linux container mode:

```sh
docker build --platform linux/amd64 -f Dockerfile.frontend -t neuron5-frontend .
```

Run and open <http://localhost:3000>:

```sh
docker run --rm --name neuron5-frontend --platform linux/amd64 --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,size=128m,mode=1777 -p 127.0.0.1:3000:3000 neuron5-frontend
```

Stop with Ctrl+C. The container starts Node directly, runs as user 10001 and
uses `/tmp` as its home and cache location. No `npm install` is needed.

The current page is a landing page. It does not yet show the system architecture
or run rows. Although the Rive JavaScript and mascot are local, the Rive loader
still fetches its WebAssembly runtime from a CDN. A fully offline demo would
also need that matching WASM asset bundled and its URL configured locally.

## Competition image: integration still required

The authoritative requirements are in [contracts/README.md](contracts/README.md).
There is no classification/generation engine in this checkout, so there is no
root `Dockerfile` for the evaluator yet. A frontend server as its default command
would wait for HTTP requests instead of producing the required output.

Before adding that Dockerfile, the engine owner must provide its actual startup
command, dependency versions and any model/data artifacts. The frontend's live
execution interface must also be agreed with that engine. The existing files do
not establish a Python, Node or other backend interface.

The root image must implement the following contract:

| Item | Required behavior |
| --- | --- |
| Build | `docker build --platform linux/amd64 .`; image at most 3 GiB unpacked |
| Default command | Run the real engine as a batch process and exit; the evaluator supplies no command override |
| User | End the Dockerfile with `USER 10001` |
| Filesystem | Read-only root; no home directory; only `/tmp` and `/output` writable |
| Dependencies | Install and package all dependencies/artifacts during build; no network during execution |
| Input | Read `/universe/universe.csv` and `/universe/lexicon.json`; runtime CSV has no `form` column |
| Output | UTF-8 `/output/output.csv`, at most 16 MiB, with the six columns in the contract |
| Publication | Write a temporary file inside `/output`, then rename it to `output.csv` when complete |
| Resources | 2 CPUs, 6 GiB RAM, 256 processes/threads; `/tmp` 128 MB, `/output` 256 MB |
| Deadline | Read Unix seconds from `ARENA_DEADLINE`; allow for SIGTERM and the 10-second termination window |

The engine must label every unlabelled input row and generate exactly 1,000 new
true claims. Packaging cannot supply that missing algorithm. Practice data and
its forms may be included in the image; runtime input must come from `/universe`.

Once the real engine and root Dockerfile exist, use the supplied checker from a
Linux shell with Docker and Python 3 available:

```sh
MINUTES=5 scripts/check.sh
scripts/check.sh
```

The checker enforces the sandbox and basic output format. It does not establish
claim truth or fully validate claim text, schemas and lexicon names.
