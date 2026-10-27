# Roadmap

Ten projects, in order. Each one is planned work. Nothing in this file is implemented yet.

A project directory is added when that project starts. Milestones ship as pull requests into `master`. See `PROGRESS.md` for status.

## 1. Async Task Processing System

- **Problem.** Work arrives faster than it can be handled inline. Callers need a durable hand-off, and workers need a safe way to retry failed work.
- **Deliverable.** A Python producer and worker that accept tasks, process them off the request path, retry failures, and later persist tasks.
- **Competencies.** Queues, concurrency, retries, idempotency, durability, backpressure.
- **Milestones.** v0.1 single producer and worker → v0.2 multiple workers → v0.3 failure handling and retries → v0.4 persistent task storage → v0.5 RabbitMQ → v0.6 observability. Detail lives in `projects/01-async-task-processor/README.md`.
- **Interview relevance.** Explain why work is queued, what happens when a worker dies mid-task, and how you avoid processing the same task twice.

## 2. Nginx and API Gateway

- **Problem.** Clients should not talk to application processes directly. Traffic needs a single entry point that can route and balance load.
- **Deliverable.** An Nginx (or equivalent) reverse proxy in front of more than one application instance, with path-based routing and a documented load-balancing choice.
- **Competencies.** Reverse proxy, routing, load balancing, health checks, timeouts, TLS termination boundaries.
- **Milestones.** Single upstream → multiple upstreams and a balancing method → path or host routing → timeouts and failure behavior → a short design note on what belongs in the gateway versus the app.
- **Interview relevance.** Draw the request path, justify the balancing method, and describe what the client sees when one upstream is down.

## 3. Redis Caching

- **Problem.** Repeated reads hit the source of truth even when the answer rarely changes. A cache can hide latency and load, and it can also serve stale or missing data.
- **Deliverable.** A small application that caches reads in Redis, with an explicit TTL and a defined behavior when Redis is unavailable.
- **Competencies.** Cache-aside (or another chosen pattern), TTL, invalidation, consistency, failure handling.
- **Milestones.** Cache a single read path → set TTL and observe expiry → define invalidation → run with Redis stopped and record the fallback.
- **Interview relevance.** Name the consistency window, what happens on a cache miss versus a cache outage, and which data you would refuse to cache.

## 4. RabbitMQ Messaging

- **Problem.** In-memory queues disappear on process exit, and producers and consumers need an independent broker with explicit delivery guarantees.
- **Deliverable.** A producer and consumer using RabbitMQ, with acknowledgments, durable queues, and a retry path for failed messages.
- **Competencies.** Acknowledgments, prefetch, durable messaging, dead-letter or retry strategy, at-least-once delivery.
- **Interview relevance.** Explain ack versus nack, what duplicate delivery looks like, and how a consumer crash is recovered.
- **Milestones.** Publish and consume one queue → manual ack → durable queue and persistent messages → retry or dead-letter on failure → note the difference from the in-memory queue in project 1.

## 5. Authentication and Authorization

- **Problem.** Callers must prove who they are, and the system must enforce what they are allowed to do. Mixing those checks into business logic hides the security boundary.
- **Deliverable.** An application that authenticates with OAuth2/OIDC, validates JWTs, and enforces at least two authorization rules at a clear boundary.
- **Competencies.** OAuth2, OIDC, JWT validation, token lifetime, authentication versus authorization, trust boundaries.
- **Milestones.** Protect one endpoint → validate JWT claims and expiry → separate authn from authz → reject tampered, expired, and wrong-audience tokens → document the trust boundary.
- **Interview relevance.** Walk through a token from issuer to resource server, and say which checks fail closed.

## 6. Observability

- **Problem.** A system that only “works on my machine” cannot be operated. You need signals for user impact, causes, and alerts that a person can act on.
- **Deliverable.** Metrics, structured logs, and traces for one service, plus one SLO and one alert tied to that SLO.
- **Competencies.** Metrics, logs, tracing, RED or USE signals, SLOs, alert routing, dashboard versus alert.
- **Milestones.** Expose basic metrics → add request logs with a correlation id → add one trace across a call → define an SLI and SLO → add one alert and say what the on-call person does.
- **Interview relevance.** Distinguish an SLI from a log line, and justify why an alert pages someone.

## 7. Containerized Application Platform

- **Problem.** A process that depends on a laptop environment is not a deployable unit. Packaging, networking, and data lifetime have to be explicit.
- **Deliverable.** A Docker Compose (or equivalent) stack that runs the application and its dependencies, with a defined network and a volume for data that must survive restart.
- **Competencies.** Images versus containers, networking, port publishing, volumes, restart behavior, configuration via environment.
- **Milestones.** One container → app plus dependency on a user-defined network → persist data across restart → document what is ephemeral.
- **Interview relevance.** Explain what survives `docker compose down`, and how containers reach each other without host networking shortcuts you cannot justify.

## 8. Kubernetes Platform

- **Problem.** A single container host does not give you deployment, scaling, or recovery as platform behavior.
- **Deliverable.** A Kubernetes deployment of the application with more than one replica, a Service, resource requests, and a demonstrated recovery from a killed Pod.
- **Competencies.** Deployments, Services, probes, scaling, scheduling, persistent storage choices, rollout and rollback.
- **Milestones.** One Deployment and Service → multiple replicas → readiness and liveness → scale and record behavior → delete a Pod and show recovery → note what you still operate yourself.
- **Interview relevance.** Explain the difference between a container restart and a Deployment rollout, and what a failed probe does to traffic.

## 9. Infrastructure as Code

- **Problem.** Infrastructure created by hand cannot be reviewed, repeated, or safely changed.
- **Deliverable.** Terraform that creates a small, reviewable environment for one earlier component, with remote or documented state, and a plan/apply/destroy cycle you have actually run.
- **Competencies.** Terraform workflow, state, modules only where they earn their cost, least privilege, drift, lifecycle (create, change, destroy).
- **Milestones.** One resource from code → review `plan` output → apply and destroy in a lab account or local emulator → add one security control (restricted network or IAM) → document state handling.
- **Interview relevance.** Read a plan and say what will change in place, what will be replaced, and what happens if state is lost.

## 10. Production Architecture Challenge

- **Problem.** The earlier labs are separate. A production system has to combine them under explicit reliability and cost trade-offs.
- **Deliverable.** An end-to-end design and a minimal running slice: ingress, application, async work, data store, and observability, with written failure modes and the trade-offs you accepted.
- **Competencies.** End-to-end design, dependency choice, failure domains, SLOs, operational load, security boundaries, communicating a design to reviewers.
- **Milestones.** Context and requirements → architecture sketch with trade-offs → implement the thin slice → run one game-day failure → revise the design from what you observed.
- **Interview relevance.** Present the system in a few minutes, name the risks you did not remove, and say what you would measure in the first week of production.
