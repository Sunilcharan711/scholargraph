# Private VPS deployment

This deployment is for one owner and one shared library. Caddy protects every
page and API route with HTTP Basic authentication over HTTPS. It is not a
multi-user system. The local Compose file remains suitable for localhost trials;
always add `compose.vps.yml` on a server so internal ports are removed.

## Prerequisites and setup

Use a Linux VPS with Docker Engine, Compose 2.24.4 or newer, Git and Python 3.11+.
Size memory for the model, its context, the database and the document collection;
measure on your host before treating local timing as a service target. CPU model
generation on real papers can take over a minute. A GPU is optional and requires
separate host/runtime configuration. This Compose configuration uses CPU inference.

Point a domain's DNS to the VPS. Allow inbound TCP 80/443 and your SSH access;
do not open 3000, 8000, 5432 or 11434. No cloud resources or domain are provisioned
by these files. Keep the Docker socket and host administration private.

```sh
git clone https://github.com/Sunilcharan711/scholargraph.git
cd scholargraph
cp deploy/vps.env.example deploy/vps.env
chmod 600 deploy/vps.env
docker run --rm -it caddy:2.11.9-alpine caddy hash-password
```

The last command prompts for your password; save its bcrypt hash as the
single-quoted `AUTH_PASSWORD_HASH` value in `deploy/vps.env`. Set a strong random
URL-safe database password, `AUTH_USER`, `SITE_ADDRESS=your.domain`, and
`SITE_ORIGIN=https://your.domain`. Do not commit this private file or use the
example placeholders. Keep an encrypted copy of configuration separately from
data backups. The browser will show a native login prompt. To end a session,
close the private browser window; Basic authentication does not provide an
application logout button.

For the following commands, define a shell helper in the repository root:

```sh
dc() { docker compose --env-file deploy/vps.env -f docker-compose.yml -f compose.vps.yml "$@"; }
dc config --quiet
dc up --build -d --wait --wait-timeout 180
dc exec ollama ollama pull qwen3:4b
dc ps
```

Caddy obtains and renews a public TLS certificate when DNS and ports are correct.
Its certificate state persists in `caddy_data`. Ollama and embedding weights
persist separately; the first upload may download the pinned embedding model.
Do not publish the app's internal service ports to bypass authentication.
The deployment allows 25 MiB PDFs with a 26 MiB proxy request limit for multipart
framing. Page and extracted-character limits remain enforced in the backend.
Requests with foreign browser origins cannot write or delete data. Proxy logs
are not enabled by default, and container logs rotate at 10 MB with three files.

## Readiness and monitoring

`/api/health` checks process liveness. `/api/ready` checks the database schema
and that Ollama lists the configured answer model; it does not run an inference
or guarantee embedding weights are already cached. Both routes require proxy
authentication. The model can be unavailable while paper search still works.

```sh
export AUTH_USER=sunil
read -r -s -p 'Monitoring password: ' AUTH_PASSWORD; echo
export AUTH_PASSWORD
python3 scripts/check_vps.py https://your.domain
unset AUTH_PASSWORD
dc logs --tail 100 backend frontend proxy
df -h
```

The monitor exits nonzero if authentication is absent or dependencies fail.
Schedule this command using your server monitoring system with credentials in a
restricted secret file, and route nonzero exits to an alert channel you control.
No external alerts or recurring jobs have been enabled automatically. Watch disk
usage, model readiness and backup age as well as process health. Protect the
monitoring password like your application password.

## Backups and restore drills

```sh
python3 scripts/manage_backup.py backup data/backups/first-backup \
  --project scholargraph_vps --env-file deploy/vps.env
```

Use a new destination directory each time. The command temporarily stops the
backend/frontend, makes a PostgreSQL custom-format dump and an archive of uploaded
PDFs, records checksums, and restarts only services that were previously running.
Expect downtime during this operation. Stop other writers, import scripts and
administrative database changes first. The database contains chunks and vectors;
model caches can be downloaded again. Never use `docker compose down --volumes`
on the live project to perform an upgrade.

Backups contain private documents and extracted text. Encrypt and copy them to
separate storage, set a retention policy, and regularly perform a restore drill.
A local backup on the same VPS is not protection against loss of that VPS.
These scripts do not implement point-in-time recovery or an off-site storage account.

```sh
python3 scripts/manage_backup.py restore data/backups/first-backup \
  --project scholargraph_vps_restore --env-file deploy/vps.env
```

Restore accepts only a project ending in `_restore`, an empty database and empty
upload volume. It verifies archive checksums and rejects traversal, links and
duplicate archive members. It never clears an existing database. Restore only
your own trusted backups: PostgreSQL dumps can contain executable SQL. Inspect
restored paper IDs, vector/chunk counts and PDF hashes before promoting a restored
instance. Do not start its proxy on the live ports during a drill. Failed restores
leave their isolated target for inspection; use a new empty project when retrying.

## Upgrade

Back up first, review changes, then `git pull` and run `dc up --build -d --wait`.
The backend applies migrations before serving. Do not roll an old image back onto
a migrated database without checking migration compatibility; restore into a
separate instance if a rollback requires old database state. Review pinned image
versions periodically for security updates and rerun the deployment checks after
updating them.

## Verification and limits

The deployment was tested locally with isolated PostgreSQL/upload volumes:
authentication, rejected cross-site writes, upload limits, backup creation and
restored database/PDF checksum equality. Public DNS, certificate issuance on your
domain, VPS capacity and off-site backup delivery still require your actual server.
Local HTTPS was checked with Caddy's trusted local CA. The local drill used the
host's Ollama 0.34.2 service; pulling and running the pinned Ollama container
still needs verification on the VPS (the registry check hit a network error).

References: [Caddy authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth),
[Compose merge rules](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/),
[PostgreSQL dumps](https://www.postgresql.org/docs/current/app-pgdump.html).
