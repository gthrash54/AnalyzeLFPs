# Deploying dbsspeech

Everything here is one lab machine running Docker Compose: an API, a worker, and
the recordings mounted read-only. There is no cloud service and nothing leaves
the machine.

Read this before the first deployment, not during it.

> **Not yet verified end to end.** The image has never been built. It was written
> against the code it installs, and the first `docker compose build` on a machine
> with a working Docker daemon is the step that proves it. Expect to fix
> something, and write down what, in `docs/backlog.md` for now and in
> `docs/troubleshooting.md` once step 4.4 creates it.

## Before anything

Two questions belong to your IT department and neither is answered yet:

- Where may de-identified research data be hosted, and is this machine an
  acceptable place?
- What is the network boundary? Campus-only behind VPN is the default assumption
  and the one to argue up from, not down from.

Until they answer, run it bound to `127.0.0.1`, which is the default. That is a
real deployment: the analyst sits at the machine. Reaching it from another
computer is the part that is blocked, not the app.

## What runs

| Service | What it does | Fails how |
|---|---|---|
| `api` | HTTP, and serves the built front end | nothing is reachable |
| `worker` | executes queued runs | the app answers, and submitted runs never start |

They are the same image with different commands, so a recipe cannot behave
differently depending on which one executed it.

The worker is the piece people forget. The Status screen exists to say so, in
those words, before anyone concludes the app is broken.

## First deployment

```bash
cd /path/to/dbsspeech
cp docker/.env.example docker/.env
```

Read `docker/.env` end to end and edit it. `DATA_DIR` is the one that will be
wrong: on this machine `data/` is a symlink into cloud-synced storage, and a
symlink does not survive a bind mount. Point `DATA_DIR` at the directory the
symlink resolves to.

```bash
readlink -f data       # this is what DATA_DIR should be
```

Then build, stamping in the commit so run records can name the code that
produced them:

```bash
GIT_COMMIT=$(git rev-parse HEAD) \
GIT_DIRTY=$(test -n "$(git status --porcelain)" && echo true || echo false) \
docker compose -f docker/compose.yml build
```

Building from a dirty tree is allowed and is recorded. Every run from that image
is then marked as coming from code in no commit, which is what a provisional
result should say about itself.

Start it:

```bash
docker compose -f docker/compose.yml up -d
docker compose -f docker/compose.yml ps
```

Create the first account. There is no self-service registration and no default
password:

```bash
docker compose -f docker/compose.yml exec api python -m dbsspeech users add
```

Open http://127.0.0.1:8000 and sign in. Go to Status. It should say one worker,
heard from seconds ago.

## Checking it works

```bash
curl -s http://127.0.0.1:8000/api/health | python -m json.tool
```

`ok` is true when the manifest validates, both databases open, and either a
worker is responsive or nothing is queued. The interesting fields:

- `queue.workers_responsive`: false with jobs queued means runs are piling up.
- `databases.*.ok`: false means a volume is mounted read-only or the host
  directory is not writable by uid 10001, which is the user inside the container.
- `versions`: the libraries whose version can change a number.

Submit a run from the web app and watch it move from queued to ok on the Status
screen. If it stays queued, the worker is not running:

```bash
docker compose -f docker/compose.yml logs worker
```

## Permissions

The container runs as uid 10001. The host directories behind the writable
volumes have to be writable by that uid:

```bash
sudo chown -R 10001:10001 derivatives runs var
```

`data/` is mounted read-only and is deliberately not in that list. The app never
writes to raw recordings, and the container is not the place to discover that
something changed.

## Updating

```bash
git pull
GIT_COMMIT=$(git rev-parse HEAD) GIT_DIRTY=false \
  docker compose -f docker/compose.yml build
docker compose -f docker/compose.yml up -d
```

Back up first. Always. See below.

Config edited from the config admin screen lives in `configs/` on the host and
survives a rebuild, because `configs/` is a mounted directory rather than image
content. That is deliberate: baked into the image it would look editable in the
browser and silently reset on the next update.

## Backups

```bash
scripts/backup.sh /path/to/backups
```

One gzipped tar per run, holding `runs/`, `derivatives/`, `var/`, `configs/`,
and `manifest/`. The two SQLite databases are snapshotted with `sqlite3 .backup`
rather than copied, because a plain copy of a database being written to is a
corrupt database and this runs while a worker may be finishing a run.

`data/` is not in the backup. The recordings are large, read-only, and backed up
where they live.

Nightly, at 02:15, keeping the last 30:

```cron
15 2 * * * cd /path/to/dbsspeech && ./scripts/backup.sh /path/to/backups >> /var/log/dbsspeech-backup.log 2>&1
```

Set `DBSSPEECH_BACKUP_KEEP` to change the retention. Old backups that fill a disk
take the app down with them.

### Restoring

Test this once, before you need it. A backup nobody has restored is a
hypothesis.

```bash
docker compose -f docker/compose.yml down
tar -xzf /path/to/backups/dbsspeech_YYYYMMDD_HHMMSS.tar.gz -C /path/to/dbsspeech
sudo chown -R 10001:10001 derivatives runs var
docker compose -f docker/compose.yml up -d
```

The archive restores in place with one untar: the database snapshots are stored
at their real paths, `var/app.db` and `derivatives/runs.db`.

Then check that what you restored is what you meant to:

```bash
docker compose -f docker/compose.yml exec api python -m dbsspeech status
```

## TLS and a hostname

Only when the lab needs it, and only after IT has said what the network rules
are. `docker/nginx.conf` proxies to the API and expects a certificate and key in
`docker/tls/`:

```bash
docker compose -f docker/compose.yml --profile nginx up -d
```

The API already serves the built front end, so this is not needed for a working
deployment. It is for TLS and a name.

## Running without Docker

Docker is a convenience, not a dependency. On a machine with the repository and
the environment, the same two processes:

```bash
uv run python -m dbsspeech serve       # or ./scripts/dev.sh for both plus Vite
uv run python -m dbsspeech worker
```

`scripts/dev.sh` starts the API, a worker, and the Vite dev server together.

## Settings

Every setting is listed with its consequences in `docker/.env.example`. The two
worth knowing by heart:

- `DBSSPEECH_REQUIRE_AUTH` must be true for anything that binds past localhost.
  `serve` refuses otherwise, and that refusal is the point: the failure worth
  preventing is not a weak password, it is an unauthenticated app answering on a
  hospital network.
- `DBSSPEECH_EXECUTOR` must be `queue` in a deployment. `background` runs
  recipes inside the API process, where a restart loses the run and no other
  process can see its status.

## What the first real deployment found (2026-09-10)

The image built on the first try once the daemon was reachable; the things
that bit were around it, not in it.

- **The docker group.** `usermod -aG docker <you>` takes effect at the next
  login. In a shell that predates it, `newgrp docker` opens a subshell with the
  group; `sg` is not installed on this machine.
- **`DATA_DIR` is the parent of the subject directories**, not `data/`. Here
  `data/` holds one symlink per subject into a local folder, and a symlink does
  not survive a bind mount, so `DATA_DIR` is the directory those symlinks
  resolve into. `manifest/subjects.csv` `root_relpath` is relative to it.
- **The mounted directories must be writable by uid 10001.** The host owns
  them as the login user, so without an ACL the API cannot open `var/app.db`
  for writing:
  `setfacl -R -m u:10001:rwX -m d:u:10001:rwX derivatives runs var configs`.
  `scripts/ship.sh up` does this.
- **Public URL without a server.** `tailscale funnel --bg 8000` publishes the
  API's localhost port at `https://<machine>.<tailnet>.ts.net` with a real
  certificate. `BIND` in `docker/.env` stays `127.0.0.1`; Funnel is the only
  thing that reaches it from outside, and the app's own login is the gate.
  Funnel and HTTPS certificates have to be enabled once in the tailnet admin
  console; the first `tailscale funnel` prints the link.
- **The build context.** `.dockerignore` already excludes recordings, results,
  environments and documents; a build sends about 30 MB. Check it before adding
  any directory at the repository root.
- The scripted path is `scripts/ship.sh` (`up`, `admin`, `funnel`, `status`).
