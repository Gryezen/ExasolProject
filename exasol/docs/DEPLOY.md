# Deploying to Render.com

## Read this first: the Exasol reachability problem

Locally this project talks to Exasol at `EXASOL_DSN=localhost:8563` —
the address the **Exasol Personal Local starter kit** listens on, because
it runs as a container/process on your own machine, right next to the
Flask app.

Once the Flask app is deployed to Render, "localhost" means *Render's
container*, not your laptop. `localhost:8563` will refuse to connect —
that's not a bug, it's the correct behavior of the word "localhost" on a
different machine. Same problem for `GEMINI_API_KEY`-style secrets that
happen to be fine locally: those work anywhere, but the *database*
address is the one thing that's environment-specific.

You have three practical options, in order of how well they fit a demo:

**1. Exasol SaaS (recommended for a deployed demo).**
Exasol offers a cloud/SaaS service reachable over the public internet.
Point `EXASOL_DSN` / `EXASOL_RO_DSN` at that instance's host:port instead
of `localhost:8563`, load `schema.sql` and `docs/mcp-grants.sql` against
it the same way you did locally, and everything else in this app is
unchanged — `database/db.py` already just uses whatever DSN it's given.

**2. A reachable tunnel to your local Exasol (fine for a live demo, not for
anything left running unattended).**
Tools like `ngrok` or a Cloudflare Tunnel can expose your local
`localhost:8563` as a public TCP endpoint for the duration of a demo.
Point `EXASOL_DSN` at the tunnel's address. This is fragile (dies if
your laptop sleeps or the tunnel drops) but requires no data migration —
useful if you want to keep developing against the local starter kit
until just before you present.

**3. Skip Render for the live demo; run everything locally.**
`python -m api.routes` plus the Exasol Personal Local starter kit on the
same machine, presented directly. This sidesteps the whole problem and
is often the least risky choice for a timed hackathon demo — you're not
depending on a cloud DB, a cold-started Render free-tier instance, or
network conditions in the room. Deploy to Render afterward, once you've
moved to option 1, for a shareable link.

Whichever you pick, `GEMINI_API_KEY` and the Exasol credentials are set
as environment variables in the Render dashboard (or your platform of
choice) — never commit real values to `.env`; only `.env.example` (names,
no values) belongs in git.

## Deploying (once you have a reachable Exasol)

1. Push this repo to GitHub or GitLab.
2. In Render: **New +** → **Blueprint**, point it at the repo. Render
   reads `render.yaml` and provisions the web service from `Dockerfile`
   (the Dockerfile installs `tesseract-ocr` and `poppler-utils` — the
   OS packages `pytesseract`/`pdf2image` need — which Render's native
   Python buildpack cannot install on its own).
3. Fill in the env vars Render prompts for (everything marked
   `sync: false` in `render.yaml`): `EXASOL_DSN`, `EXASOL_USER`,
   `EXASOL_PASSWORD`, `EXASOL_RO_DSN`, `EXASOL_RO_USER`,
   `EXASOL_RO_PASSWORD`, `GEMINI_API_KEY`.
4. Deploy. Render builds the image, runs
   `gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:$PORT api.routes:app`,
   and health-checks `/api/config`.
5. Open the assigned `*.onrender.com` URL — the dashboard is served at
   `/`, same as locally.

## Uploaded files are ephemeral

`UPLOAD_DIR` (default `/app/data/uploads` in the container) is **not**
persisted across deploys or restarts on Render's default disk. For a
demo this is usually fine — everything meaningful (extracted fields,
audit log, discrepancies) lives in Exasol, not on local disk. If you
need uploaded source files to survive restarts, attach a
[Render Disk](https://render.com/docs/disks) at `UPLOAD_DIR`.

## Running without Docker

If you deploy somewhere that doesn't build the `Dockerfile` (a plain
Python buildpack host), you're responsible for getting `tesseract-ocr`
and `poppler-utils` installed by some other means — `pytesseract` and
`pdf2image` will raise at runtime, not at import time, if those binaries
are missing, so a scan-heavy upload is where you'd notice it first. The
included `Procfile` (`gunicorn ... api.routes:app`) is there for hosts
that use one directly.
