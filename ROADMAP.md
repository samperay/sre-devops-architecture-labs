# Roadmap

Ten projects, in order. Each one is planned work. Nothing in this file is implemented yet.

A project directory is added when that project starts. Milestones ship as pull requests into `master`. See `PROGRESS.md` for status.

## 1. Async Task Processing System

- **Problem.** The initial implementation demonstrates asynchronous task processing using an in-memory queue. Because queued tasks can be lost when the process exits, later milestones introduce persistent task storage, recovery mechanisms, and stronger delivery guarantees.
- **Deliverable.** A Python producer and worker that accept tasks and process them off the request path. Planned, not built: v0.1 is an in-memory queue with no durability guarantee. Multiple workers, failure handling and retries, persistent task storage, RabbitMQ, and observability come in later milestones.
- **Competencies.** Queues, concurrency, retries, idempotency, durability (from v0.4), backpressure. RabbitMQ appears only as an integration at v0.5.
- **Milestones.** v0.1 single producer and worker, in-memory queue, no durability across process exit → v0.2 multiple workers → v0.3 failure handling and retries → v0.4 persistent task storage → v0.5 RabbitMQ integration → v0.6 observability. Detail lives in `projects/01-async-task-processor/README.md`. None of these are implemented.
- **v0.5 scope.** Planned integration into the application from earlier milestones, not a broker study. Replace the in-memory queue with a broker-backed queue, connect that producer and worker to RabbitMQ, compare the two architectures, and identify differences in durability, process boundaries, and operational complexity. Routing, acknowledgments, prefetch, dead letters, and broker failure stay in Project 04.
- **Interview relevance.** Explain why work is queued, what v0.1 loses when the process exits, what a worker crash mid-task implies before and after retries exist, and how the v0.5 broker changes durability and process boundaries compared with the in-memory queue.

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

- **Problem.** Project 01 v0.5 only replaces the in-memory queue with RabbitMQ inside the task processor. Exchanges, acknowledgments, prefetch, dead-letter queues, and broker failure are outside that milestone.
- **Relationship to Project 01.** This project builds on that introductory integration rather than repeating it. It is a deeper, standalone study of message-broker architecture.
- **Deliverable.** A small producer and consumer used to exercise routing, acknowledgments, durable messaging, retries or dead letters, and recovery. Planned work, not an existing lab.
- **Competencies.** Exchanges, queues, bindings, and routing; message acknowledgments and negative acknowledgments; consumer prefetch; persistent messages and durable queues; at-least-once delivery and duplicate processing; retry strategies and dead-letter queues; consumer crashes and recovery; broker failure scenarios; operational monitoring and troubleshooting.
- **Milestones.** Exchange, queue, and binding → manual ack and nack → prefetch → persistent messages and durable queues → duplicate delivery under at-least-once → retry or dead-letter → consumer crash and recovery → broker failure → one monitoring or troubleshooting check.
- **Interview relevance.** Explain ack versus nack, what duplicate delivery looks like, how a consumer crash is recovered, and what you check when the broker is down.

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
