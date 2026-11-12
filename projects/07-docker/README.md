# Project 07 — Docker Engineering, Security, Compose and Production Operations

> **SRE & DevOps Architect Journey**  
> **Learning stages:** LEARN → INTEGRATE → OPERATE  
> **Progress:** APPLIED overall; **not yet ARCHITECT READY**  
> **Environment:** Apple Silicon M4; Docker Desktop 4.71.0; Engine 29.4.1 (`linux/arm64`); Compose v5.1.3  
> **Evidence:** User-provided terminal output and learning-session review through 12 November 2026.  
> **Scope:** Standalone labs. No changes to the real Todo application are implied.

## Purpose and learning approach

This project refreshes Docker fundamentals through production-oriented experiments, then evaluates the ability to explain design decisions, isolate faults, and operate containerized systems. The goal is to prepare for Kubernetes without spending unnecessary time repeating familiar fundamentals.

**Restaurant analogy:** An image is a repeatable kitchen blueprint; a container is a running kitchen; a bridge network is a staff-only communication corridor; a published port is the customer entrance; a volume is a storeroom whose contents survive replacement of the kitchen; Compose coordinates multiple kitchens and supporting services. In the Todo analogy, the API handles requests while PostgreSQL retains task data.

**Learning loop:** BUILD → UNDERSTAND → BREAK → FIX → DESIGN. Exercises are safe and isolated. Avoid removing unrelated Docker resources or named volumes containing valuable data.

## 07.01 — Docker architecture and container lifecycle

### LEARN

Docker packages an application and its dependencies into an image and runs it as an isolated process in a container. The image is immutable at runtime; the container has a writable layer that is not a substitute for durable storage. Docker Desktop runs a Linux engine within its managed environment on macOS.

- **Image:** build artifact and filesystem layers.
- **Container:** isolated running or stopped process created from an image.
- **Registry:** image distribution service.
- **Engine:** builds, runs, networks, and manages containers.
- **Namespaces/cgroups:** Linux mechanisms for isolation and resource accounting/limits.

### Evidence and observations

The environment reported Docker Engine 29.4.1, architecture `linux/arm64`. At baseline no containers were running. Previously stopped containers included a Todo API and Prometheus. An earlier Todo container showed exit code 137 but `OOMKilled=false`: **exit 137 alone does not prove an out-of-memory kill**.

### OPERATE

Use `docker ps -a`, `docker inspect`, `docker logs`, `docker stats`, and `docker events` to distinguish process exit, OOM termination, failed health checks, and external stops. Inspect the exit code and OOM flag together before assigning a root cause.

## 07.02 — Docker networking and isolation

### LEARN

Containers on the same user-defined bridge network can resolve each other by container/service name. Containers on isolated networks cannot automatically resolve or reach one another. A published host port is distinct from a container's internal listening port.

### Lab: service-to-service communication

A user-defined bridge network `lab07-network` was created (observed subnet `172.19.0.0/16`). An Nginx container named `kitchen` and a curl client named `waiter` joined the network. From `waiter`, `http://kitchen` returned **HTTP 200**.

Representative commands:

```bash
docker network create lab07-network
docker run -d --name kitchen --network lab07-network nginx:alpine
docker run --rm --network lab07-network curlimages/curl -I http://kitchen
docker network inspect lab07-network
```

The test verified name resolution and HTTP communication, not merely that containers were running.

### Lab: isolation

A separate `lab07-isolated` network was created. A client attached only to that network could not resolve `kitchen`; curl returned error **6** (DNS resolution failure). This demonstrated a network boundary rather than an application error.

### Lab: host port publication

The `kitchen-web` container published container port 80 to host address `127.0.0.1:8088`. A host-side request to `http://127.0.0.1:8088` returned **200**. Binding to loopback restricts exposure compared with binding to all host interfaces.

**Architect decision:** Keep databases internal; publish only necessary ingress ports. Avoid hard-coding container IPs because they can change after recreation.

## 07.03 — Storage: named volumes and bind mounts

### LEARN

The container writable layer is ephemeral relative to container replacement. A **named volume** is Docker-managed durable storage. A **bind mount** maps a specific host path into a container; it is useful for development configuration and local source code but creates host-path coupling.

### Lab: named-volume persistence

Created `lab07-todo-data`, mounted at `/app/data`, wrote `tasks.txt`, recreated the container, and confirmed the data remained. This establishes persistence across container recreation.

### Lab: read-only bind mount

A host directory `$HOME/docker-storage-lab` was mounted read-only at `/app/config`. Changes to `config.txt` on the host became visible inside the running container. The application still needs to reload configuration if it caches settings.

**Operational warning:** `docker compose down` normally retains named volumes; `docker compose down -v` removes declared named volumes and can destroy lab or customer data. Never use `-v` indiscriminately. An anonymous volume may remain on disk after container removal yet not be remounted automatically by a new container: **data inaccessible is not necessarily data lost**.

## 07.04 — Resource limits and failure diagnosis

### LEARN

Memory and CPU limits help control noisy neighbors and define resource boundaries. A memory limit does not guarantee application availability; applications need headroom, appropriate sizing, and monitoring.

### Lab: memory pressure

A container constrained to **64 MiB** was deliberately pushed beyond its limit. Inspection showed **exit code 137** and **OOMKilled=true**. This differs from the previously observed stopped Todo container, where exit code 137 was present but `OOMKilled=false`.

Useful diagnostic commands:

```bash
docker inspect <container> --format '{{.State.ExitCode}} {{.State.OOMKilled}}'
docker stats --no-stream
docker logs --tail 100 <container>
```

**Architect decision:** Treat OOM as evidence to investigate workload memory, concurrency, limits, and trends; do not reflexively raise limits without understanding the failure mode.

## 07.05 — Dockerfile engineering and image construction

### LEARN

A Dockerfile describes a reproducible image. Layer order affects cache reuse. A `.dockerignore` reduces build context and avoids accidentally including local secrets. Prefer non-root processes and minimal, maintained base images.

### Lab evidence

A Python application image was built in `~/docker-build-lab` using `python:3.12-slim`. Dependency installation was separated from application source copying to demonstrate build cache behavior. A `.dockerignore` excluded `.env`. The runtime user had UID **10001** rather than root. The observed image size was approximately **216 MB**.

Representative Dockerfile structure (illustrative, not a verbatim reproduction of the original lab file):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home appuser
USER 10001
CMD ["python", "app.py"]
```

**Trade-off:** Alpine uses musl libc; Debian slim typically uses glibc. Base-image selection affects native dependencies, compatibility, image size, patch cadence, and vulnerability exposure.

## 07.06 — Runtime security and vulnerability management

### LEARN

Defense in depth includes non-root execution, least privilege, reduced capabilities, immutable filesystem where feasible, secret hygiene, and vulnerability scanning.

### Lab: hardened runtime

The container was launched with controls equivalent to:

```bash
--cap-drop=ALL
--security-opt=no-new-privileges
--read-only
--tmpfs /tmp:rw,nosuid,nodev,size=32m,mode=1777
```

The user verified **effective capabilities = 0**, **NoNewPrivs = 1**, a writable temporary directory, and a read-only application filesystem. These controls reduce attack surface but do not replace patching, authorization, or network isolation.

### Vulnerability scan

Docker Scout v1.20.4 reported **36 vulnerabilities** in the tested image: **0 critical, 2 high, 6 medium, 28 low**. The high findings involved zlib. The recommendation output did not offer a newer Python 3.12-slim tag as an automatic fix at that time.

**Architect decision:** Rebuild with patched dependencies/base images when available, validate in CI, and document temporary risk acceptance and compensating controls. Do not claim that an image is secure merely because it runs as non-root.

## 07.07 — Docker Compose and multi-service deployment

### LEARN

Compose declares related services, their networks, volumes, configuration, and startup dependencies. Compose provides convenient local orchestration, but `depends_on: condition: service_healthy` gates **initial startup**; it does not provide automatic runtime recovery when a dependency fails later.

### Lab architecture

```text
                 Compose project: lab07-compose
              ┌──────────────────────────────┐
              │  api (Python 3.12 Alpine)    │
              │       │ DNS: db              │
              │       ▼                      │
              │  db (PostgreSQL 16 Alpine)   │
              │       │                      │
              │       ▼                      │
              │  postgres-data named volume │
              └──────────────────────────────┘
```

Compose project network: `lab07-compose_default`, observed subnet `172.21.0.0/16`. PostgreSQL listens on internal port 5432; **no host publication** was configured.

### Compose configuration used in the lab

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: todo
      POSTGRES_PASSWORD: lab-only-password
      POSTGRES_DB: tododb
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U todo -d tododb"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s

  api:
    image: python:3.12-alpine
    depends_on:
      db:
        condition: service_healthy
    command:
      - python
      - -u
      - -c
      - |
        import socket
        print("Todo API starting")
        with socket.create_connection(("db", 5432), timeout=5):
            print("Database TCP connection successful")

volumes:
  postgres-data:
```

**Scope note:** The API is a **short-lived TCP probe**, not the actual Todo application, a long-running web server, or a PostgreSQL SQL client. Its successful output proves DNS/TCP connectivity only, not database authentication or SQL correctness. The password is an intentionally lab-only placeholder, not production secret-management guidance.

### Exercise: validate configuration and startup ordering

```bash
docker compose -p lab07-compose config --quiet
docker compose -p lab07-compose up
docker compose -p lab07-compose ps -a
```

Observed: Compose waited until PostgreSQL was healthy, then started the API; the API printed `Todo API starting` and `Database TCP connection successful`, then exited **0** as designed.

### Exercise: named volume and existing data

An earlier PostgreSQL instance used an anonymous volume (observed long Docker volume ID). The lab was updated to use `postgres-data`, producing Docker volume `lab07-compose_postgres-data`. The inspected mount destination was `/var/lib/postgresql/data`. The anonymous volume was **not** deliberately deleted.

**Learning:** A database can be healthy yet appear empty because it is mounted to a different volume. First inspect mount identity and the actual data path before assuming data loss.

### Exercise: SQL record verification

Commands:

```bash
docker compose -p lab07-compose exec -T db \
  psql -U todo -d tododb \
  -c "CREATE TABLE IF NOT EXISTS lab_tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL);"

docker compose -p lab07-compose exec -T db \
  psql -U todo -d tododb \
  -c "INSERT INTO lab_tasks (id, title) VALUES (1, 'Verify Docker volume persistence') ON CONFLICT (id) DO NOTHING;"

docker compose -p lab07-compose exec -T db \
  psql -U todo -d tododb \
  -c "SELECT * FROM lab_tasks;"
```

Observed output:

```text
NOTICE: relation "lab_tasks" already exists, skipping
CREATE TABLE
INSERT 0 0

 id |              title
----+----------------------------------
  1 | Verify Docker volume persistence
(1 row)
```

The existing table and `INSERT 0 0` showed the row already existed; the conflict clause prevented a duplicate.

### Exercise: recreate database and verify persistence

```bash
docker compose -p lab07-compose up -d --no-deps --force-recreate db
docker compose -p lab07-compose ps db
docker compose -p lab07-compose exec -T db \
  psql -U todo -d tododb -c "SELECT * FROM lab_tasks;"
```

**Actual evidence:** `lab07-compose-db-1` was recreated, reported `Up ... (healthy)`, and the query still returned the record with ID **1**. This confirms persistence across database container replacement using the named volume. It does **not** establish backup/restore capability.

### Exercise: fresh API connectivity after database recreation

```bash
docker compose -p lab07-compose run --rm --no-deps api
```

Actual output:

```text
Container lab07-compose-api-run-c356b16063c4 Creating
Container lab07-compose-api-run-c356b16063c4 Created
Todo API starting
Database TCP connection successful
```

**Conclusion:** A newly started API probe can reach the recreated database over TCP. It does **not** prove automatic recovery of an existing connection pool or successful authenticated queries.

### Architecture discussion: retries and idempotency

A database may commit an insert even if the response connection breaks. Blind client retries can create duplicate tasks. Use transactionally enforced idempotency keys or suitable unique constraints, bounded retries with backoff, and careful handling of ambiguous outcomes. Stale connection pools must validate/discard dead connections and establish new ones. Do not assume that startup ordering solves runtime resilience.

## 07.08 — Production incident assessment

### Scenario: Todo API returns HTTP 500 after deployment

Simulated evidence:

```text
INFO  Todo API started successfully
INFO  Listening on port 8000
ERROR Database query failed
ERROR sqlalchemy.exc.ProgrammingError:
      relation "tasks" does not exist
INFO  GET /health 200
ERROR GET /api/tasks 500
```

Additional scenario facts: Nginx and PostgreSQL healthy, network and authentication working, new API image deployed, missing schema migration.

### Investigation and reasoning

The user proposed inspecting `docker logs`, Docker networking, application health, and API-to-database communication. Review added the need to inspect **deployment changes**, schema expectations, and the distinction between TCP reachability, authentication, and query correctness.

Representative triage:

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose config
```

**Caution:** Resolved Compose configuration can expose secrets; redact before sharing.

**Root cause identified:** Application/database schema incompatibility, not Docker networking or database availability.

**Recovery decision:** Applying the missing migration may be appropriate if it is reviewed, tested, compatible, and safe. Rolling back the API may be safer if the migration is untested or destructive, but rollback also requires compatibility with the current database. Validate real API functionality (`/api/tasks`), not only container startup or `/health`.

**Prevention:** CI integration tests against the expected schema; versioned migrations; predeployment compatibility checks; migration execution and verification; API rollout; postdeployment functional checks; alerting and rollback criteria.

### Zero-downtime schema changes: expand → migrate → contract

Renaming `task_name` directly to `title` breaks old API instances still using the former name during rolling or blue-green deployments. Blue-green routing and container health checks alone cannot prevent this.

1. **Expand:** Add `title` without removing `task_name`.
2. **Migrate:** Backfill data and use a safe dual-write or other synchronization/compatibility strategy.
3. **Deploy:** Roll out API versions that coexist with both columns.
4. **Verify:** Confirm reads/writes, data consistency, error rates, and rollback compatibility.
5. **Contract:** Remove `task_name` in a later release after no remaining consumers require it.

A database backup supports recovery, but restoring it can discard newer writes; it is not equivalent to reverting an application container.

## OPERATE — Production design checklist

| Concern | Questions for an architect |
|---|---|
| Availability | Does a process being up mean real requests succeed? |
| Networking | Which services need host ingress, and which must remain private? |
| Persistence | Which named volume holds production data? How is it backed up and restored? |
| Recovery | Do clients handle stale connections and ambiguous write outcomes safely? |
| Security | Non-root? Least capabilities? Read-only filesystem? Patched base image? |
| Performance | What happens when memory limits or connection pools are exhausted? |
| Deployments | Can old and new application versions coexist with the database schema? |
| Observability | Are errors, saturation, health, and business-level requests monitored? |
| Rollback | Is rollback compatible with any schema or data changes already applied? |

## Progress checkpoint — 12 November 2026

| Lesson | Evidence | State |
|---|---|---|
| 07.01 Architecture and lifecycle | Runtime inspection and exit-code reasoning | UNDERSTOOD |
| 07.02 Networking | DNS, isolation, localhost publication | UNDERSTOOD |
| 07.03 Storage | Named volume and bind mount persistence | APPLIED |
| 07.04 Resource limits | OOM vs non-OOM exit 137 | UNDERSTOOD |
| 07.05 Dockerfile | Cached build, .dockerignore, non-root image | UNDERSTOOD |
| 07.06 Security | Capability restrictions, read-only rootfs, vulnerability scan | UNDERSTOOD |
| 07.07 Docker Compose | PostgreSQL health, named volume recreation, TCP probe | APPLIED |
| 07.08 Production incident | Root-cause isolation, migration and rollout discussion | UNDERSTOOD; schema evolution requires revision |

**Overall Project 07:** APPLIED, **not ARCHITECT READY**. The user demonstrated practical execution and sound initial incident reasoning. Still to prove: full recovery of long-running connections, backup restoration, monitoring/alerting, and zero-downtime schema compatibility in an actual implementation. These are not claimed as completed.

**Next:** Kubernetes architecture and operations, with a targeted readiness assessment instead of repeating Docker fundamentals. Revisit deployment/schema compatibility during Kubernetes rolling-update lessons.

## Repository and safety notes

- This is documentation of standalone local Docker exercises, **not** evidence that Docker changes were implemented in `samperay/todo`.
- The example Compose credentials are lab-only.
- No production resources, unrelated containers, or volumes should be deleted to follow this tutorial.
- Keep lab evidence and proposed production practices clearly separated.
