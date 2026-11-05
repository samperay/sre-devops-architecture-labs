SRE/DevOps Architect Journey — Progress Tracker

Last updated: 2026-11-05
Repository: samperay/sre-devops-architecture-labs
Current learning phase: Project 02 completed for the current learning scope; Kubernetes preparation next.

⸻

1. Purpose

This document tracks practical learning progress toward becoming an SRE/DevOps Architect.

Progress is based on:

* Completed hands-on exercises.
* Terminal output and practical evidence.
* GitHub pull requests.
* Architecture discussions.
* Troubleshooting exercises.
* Technical understanding.
* Operational experience.
* Architectural decision-making.

A completed lab does not automatically mean a technology is mastered.

The objective is to develop the ability to design, implement, troubleshoot, operate, secure, scale, and justify production systems.

⸻

2. Learning Methodology

Every project follows:

BUILD → UNDERSTAND → BREAK → FIX → DESIGN

BUILD

Implement the smallest working system.

UNDERSTAND

Explain the architecture, components, request flow, and technical decisions.

BREAK

Introduce controlled failures to understand system behavior.

FIX

Investigate failures, identify root causes, and restore service.

DESIGN

Evaluate trade-offs and propose production-ready improvements.

Learning activities also follow:

LEARN → INTEGRATE → OPERATE

LEARN

Understand the technology through concepts, architecture, analogies, and standalone labs.

INTEGRATE

Evaluate how the technology could be applied to a real application, including the Todo project.

OPERATE

Practice monitoring, troubleshooting, security, failure recovery, and production operations.

⸻

3. Progress States

State	Definition
NOT STARTED	No verified learning or implementation evidence
IN PROGRESS	Learning or implementation underway
LAB COMPLETED	Practical exercises completed with evidence
UNDERSTOOD	Architecture, concepts, and failure behavior explained
APPLIED	Technology implemented and exercised in practical scenarios
ARCHITECT READY	Can design, implement, troubleshoot, operate, and justify architectural decisions

Important: Progress states represent demonstrated capability, not simply the number of commands executed.

A merged PR provides implementation or documentation evidence, but does not automatically establish architect readiness.

⸻

4. Overall Project Progress

The curriculum contains ten planned architecture projects.

Project	Technology	Current progress	Notes
01	Async Task Processing System	APPLIED — v0.1	Six labs completed; future versions pending
02	Nginx and API Gateway	APPLIED	Six lessons covered; documentation merged
03	Redis Caching	NOT STARTED	Planned
04	RabbitMQ Messaging	NOT STARTED	Planned
05	Authentication and Authorization	NOT STARTED	Planned
06	Observability	NOT STARTED	Planned in this lab repository
07	Containerized Application Platform	NOT STARTED	Docker revision planned
08	Kubernetes Platform	NOT STARTED	Next major learning focus proposed
09	Infrastructure as Code	NOT STARTED	Planned
10	Production Architecture Challenge	NOT STARTED	Planned

Note: The proposed Kubernetes-first sequence differs from the current numerical roadmap order. The roadmap should be updated separately if that sequence is formally adopted.

No overall curriculum-completion percentage is reported because the total number of required milestones and assessments has not been finalized.

⸻

5. Project 01 — Async Task Processing System

Status

Current progress: APPLIED — v0.1

Implementation milestone: v0.1 completed.

Completed Learning

Lab	Topic	Status
01	Task Model	LAB COMPLETED
02	Producer and Queue	LAB COMPLETED
03	Single Worker	LAB COMPLETED
04	Task Lifecycle and Logging	LAB COMPLETED
05	Graceful Shutdown	LAB COMPLETED
06	Automated Testing	LAB COMPLETED

Practical Evidence

The following functionality was implemented and tested:

* Python in-memory task queue.
* Producer and consumer architecture.
* Task identifiers.
* Task lifecycle management.
* Asynchronous task processing.
* Worker execution.
* Graceful shutdown.
* Concurrent task submission.
* Automated testing.

Test Results

Previously recorded:

22 automated tests passed.

GitHub Evidence

PR #2 — Merged

https://github.com/samperay/sre-devops-architecture-labs/pull/2

Merged: 2026-10-28

The PR contains the v0.1 source files, six lab files, specifications, and automated tests.

Architecture Competencies

Competency	Assessment
Producer-consumer architecture	UNDERSTOOD
Python queue operations	APPLIED
Task lifecycle management	APPLIED
Graceful shutdown	APPLIED
Concurrency testing	APPLIED
Persistent task storage	NOT STARTED
Retry and recovery architecture	NOT STARTED
Distributed workers	NOT STARTED
Message broker integration	NOT STARTED

Deferred Milestones

* v0.2 — Multiple workers.
* v0.3 — Failure handling and retries.
* v0.4 — Persistent task storage.
* v0.5 — RabbitMQ integration.
* v0.6 — Observability.

Architect Readiness

Not yet verified.

Further evidence is required for durability guarantees, failure recovery, distributed processing, operational monitoring, and architectural trade-offs.

⸻

6. Project 02 — Nginx and API Gateway

Status

Current progress: APPLIED

Current learning scope: Completed.

Advanced production operations: Deferred.

Learning Environment

* Ubuntu Server virtual machine.
* Nginx 1.18.0.
* Python HTTP backend services.
* OpenSSL.
* curl.
* Localhost-based network configuration.

Architecture

                     Client
                        |
                        | HTTPS :8443
                        v
                Nginx TLS Endpoint
                        |
                        | HTTP :8085
                        v
                 Nginx API Gateway
                        |
              +---------+---------+
              |                   |
            /api/              /users/
              |                   |
              v                   v
          Backend A           Backend B
            :8081               :8082

A separate load-balancing lab uses Nginx on port 8080 to distribute requests across backend services.

These are standalone learning environments and do not imply the same architecture has been implemented in the Todo application.

⸻

6.1 Lesson Progress

Lesson	Topic	Status
01	Nginx Load Balancing Fundamentals	APPLIED
02	Reverse Proxy, Upstreams, and Round Robin	APPLIED
03	Load Balancing Algorithms	APPLIED
04	Reliability, Timeouts, and Retries	APPLIED
05	API Gateway Routing	APPLIED
06	TLS/HTTPS and Security Boundaries	APPLIED

Six lessons covered.

The learning record includes practical exercises, troubleshooting discussions, and architecture assessments.

⸻

6.2 Load Balancing

Completed

* Nginx reverse proxy fundamentals.
* Upstream configuration.
* Multiple backend services.
* Round-robin request distribution.
* HTTP request forwarding.
* Backend failure testing.
* Nginx configuration validation.
* Service reload.
* HTTP 502 troubleshooting.

Verified Lab Architecture

              Client
                 |
                 v
             Nginx :8080
                 |
          +------+------+
          |             |
          v             v
      Backend A     Backend B
        :8081         :8082

Practical Evidence

* Both backend services responded successfully.
* Nginx forwarded requests to upstream services.
* Round-robin distribution was observed.
* Upstream failures were investigated.

⸻

6.3 Reliability and Failure Handling

Topics Covered

* HTTP 502 Bad Gateway.
* HTTP 503 Service Unavailable.
* HTTP 504 Gateway Timeout.
* Connection failures.
* Upstream availability.
* Request timeouts.
* Retry behavior.
* Failure recovery.
* Retry amplification.
* Capacity considerations.

Architecture Learning

Automatic retries require careful evaluation.

Important considerations:

1. Whether the operation is safe to retry.
2. Whether another healthy backend exists.
3. Whether retry traffic can overload the system.
4. Whether the operation is idempotent.
5. Whether the retry policy has bounded attempts and timeouts.

Knowledge Assessment

The distinction between HTTP 502 and HTTP 504 was discussed and clarified.

Further production-scale retry policy design remains an area for continued practice.

⸻

6.4 API Gateway Routing

Completed

Configured an Nginx API gateway on:

127.0.0.1:8085

Routes:

Endpoint	Destination
/health	Nginx gateway health response
/api/	Backend A — port 8081
/users/	Backend B — port 8082

Verified Results

* /health returned HTTP 200.
* /api/ returned the Backend A response.
* /users/ returned the Backend B response.
* Backend A failure caused /api/ to fail.
* /health remained available during the backend failure.
* Backend A recovery restored /api/ functionality.

Architecture Learning

A successful gateway health check does not guarantee that every upstream application is healthy.

Application monitoring should distinguish:

* Gateway availability.
* Backend availability.
* End-to-end request success.

GitHub Evidence

PR #6 — Merged

https://github.com/samperay/sre-devops-architecture-labs/pull/6

Merged: 2026-11-01

⸻

7. Lesson 06 — TLS/HTTPS and Security Boundaries

Status

Current progress: APPLIED

Hands-on TLS fundamentals: Completed.

Production certificate lifecycle operations: Deferred.

Completed Learning

* TLS architecture.
* TLS termination.
* Public and private keys.
* Self-signed certificates.
* Certificate Subject Alternative Names.
* Certificate permissions.
* Nginx HTTPS configuration.
* Certificate trust verification.
* TLS protocol negotiation.
* Certificate fingerprints.
* Certificate expiration checks.
* Basic Bash monitoring.
* Monitoring failure classification.

HTTPS Architecture

Client
   |
   | HTTPS
   v
Nginx :8443
   |
   | HTTP
   v
API Gateway :8085
   |
   +---- Backend A :8081
   |
   +---- Backend B :8082

Certificate Details

Certificate location:

/home/ubuntu/tls-lab/server.crt

Private key:

/home/ubuntu/tls-lab/server.key

Certificate subject:

CN=localhost

Certificate expiration:

2026-12-04 11:54:41 GMT

TLS Protocol Validation

Protocol	Observed result
TLS 1.0	Rejected
TLS 1.1	Rejected
TLS 1.2	Accepted
TLS 1.3	Accepted

HTTPS Validation

Verified:

* Nginx HTTPS listener.
* Certificate trust using curl with a specified CA certificate.
* Successful HTTPS gateway health request.
* Successful HTTPS requests to Backend A and Backend B.
* Live certificate inspection using OpenSSL.
* Matching live and on-disk certificate fingerprints.

Certificate Monitoring

Completed exercises included:

* Certificate expiration inspection.
* Thirty-day warning threshold.
* Seven-day critical threshold.
* Bash severity classification.
* Missing certificate failure injection.
* Missing certificate file detection.

Verified Monitoring Results

WARNING: Certificate expires within 30 days
Unable to load certificate
Exit status: 1
UNKNOWN: Certificate file does not exist:
 /home/ubuntu/tls-lab/nonexistent.crt

Architecture Learning

A certificate monitoring system must distinguish:

* Healthy certificates.
* Expiring certificates.
* Expired certificates.
* Missing or unreadable certificates.
* Invalid certificate data.
* Unavailable HTTPS endpoints.

A successful certificate check does not guarantee application health.

Documentation Evidence

PR #7 — Merged

https://github.com/samperay/sre-devops-architecture-labs/pull/7

Merged: 2026-11-05

This PR added:

* Lesson 01 documentation.
* Lesson 06 documentation.
* Consolidated Project 02 learning notes.

⸻

8. Project 02 — Deferred Production Operations

Status

NOT STARTED — Deferred until after Kubernetes learning

These activities are not considered completed.

Milestone 07 — Certificate Renewal and Rollback

Planned learning:

1. Certificate renewal planning.
2. Generate or obtain a replacement certificate.
3. Validate certificate and private-key compatibility.
4. Validate certificate SAN and validity dates.
5. Back up existing certificate material securely.
6. Deploy the replacement certificate.
7. Validate Nginx configuration.
8. Perform a graceful Nginx reload.
9. Verify the certificate served by the live endpoint.
10. Validate HTTPS application connectivity.
11. Simulate a failed deployment safely.
12. Restore the previous certificate.
13. Verify recovery.
14. Document the operational runbook.

Milestone 08 — Production-Grade Certificate Monitoring

Planned learning:

1. Monitor live HTTPS endpoints.
2. Check certificate expiration.
3. Validate certificate hostname.
4. Validate certificate trust.
5. Distinguish WARNING, CRITICAL, and UNKNOWN.
6. Handle malformed or unreadable certificates.
7. Detect monitoring configuration errors.
8. Configure meaningful alert thresholds.
9. Avoid noisy alerts.
10. Develop a certificate expiration runbook.
11. Evaluate certificate monitoring in Kubernetes.
12. Compare manual renewal with automated certificate management.

Completion Criteria

These milestones require practical evidence of:

* Successful certificate renewal.
* Safe deployment.
* Live certificate verification.
* Successful rollback.
* Monitoring failure handling.
* Operational troubleshooting.
* Documented architecture decisions.

They must not be marked completed until the corresponding exercises are performed and reviewed.

⸻

9. Project 02 — Architecture Competency Assessment

Competency	Current assessment
Explain reverse proxy architecture	UNDERSTOOD
Configure Nginx load balancing	APPLIED
Troubleshoot upstream failures	APPLIED
Explain API gateway routing	UNDERSTOOD
Configure API gateway routing	APPLIED
Explain TLS termination	UNDERSTOOD
Configure HTTPS	APPLIED
Validate certificate trust	APPLIED
Test TLS protocol compatibility	APPLIED
Perform basic certificate monitoring	LAB COMPLETED
Design safe retry policies	UNDERSTOOD — further practice recommended
Design idempotent operations	UNDERSTOOD — implementation not demonstrated
Perform production certificate renewal	NOT STARTED
Perform certificate rollback	NOT STARTED
Implement production-grade monitoring	NOT STARTED
Defend complete production architecture	Further assessment required

Overall Assessment

Project 02: APPLIED

The current learning scope is complete.

The project is not yet classified as ARCHITECT READY because advanced operational scenarios and complete production architecture assessments remain outstanding.

⸻

10. GitHub Pull Request Evidence

PR	Description	Status
#2	Async Task Processor v0.1 implementation	MERGED
#3	Nginx reverse proxy lesson documentation	MERGED
#6	API Gateway routing documentation	MERGED
#7	Project 02 consolidated learning documentation	MERGED

References

* PR #2: https://github.com/samperay/sre-devops-architecture-labs/pull/2
* PR #3: https://github.com/samperay/sre-devops-architecture-labs/pull/3
* PR #6: https://github.com/samperay/sre-devops-architecture-labs/pull/6
* PR #7: https://github.com/samperay/sre-devops-architecture-labs/pull/7

⸻

11. Next Learning Milestones

Immediate

* Merge the updated progress documentation.
* Preserve the remaining TLS operational milestones.
* Review the existing Kubernetes tutorial.
* Establish the Kubernetes learning baseline.

Proposed Next Phase — Kubernetes

The planned focus is:

* Kubernetes architecture.
* Control plane and worker nodes.
* Pods and Deployments.
* Services and networking.
* Ingress and Gateway API.
* Readiness and liveness probes.
* Resource requests and limits.
* Scheduling.
* Scaling.
* Rollouts and rollbacks.
* Security boundaries.
* Troubleshooting.
* Failure recovery.
* Production operations.

Docker fundamentals will be revised only where knowledge gaps are identified.

The Kubernetes project has not started yet.

Post-Kubernetes

Return to Project 02 for:

* Certificate renewal.
* Certificate rollback.
* Live certificate verification.
* Production-grade certificate monitoring.

Then continue the remaining architecture projects according to the agreed roadmap.

⸻

12. Learning Principles

1. Do not repeat completed exercises without a clear reason.
2. Use practical evidence to verify progress.
3. Teach one exercise at a time.
4. Explain objectives before commands.
5. Review terminal output before advancing.
6. Prefer architecture reasoning over command memorization.
7. Use controlled failure injection.
8. Document troubleshooting observations.
9. Distinguish implementation completion from architecture readiness.
10. Avoid introducing unnecessary infrastructure.
11. Preserve existing working environments.
12. Prioritize production engineering judgment.

⸻

13. Current Learning Checkpoint

Field	Value
Current project	Project 02 — Nginx and API Gateway
Current milestone	Documentation and current learning scope completed
Latest merged PR	#7
Latest completed exercise	Lesson 06 — Exercise 36
Current progress state	APPLIED
Architect readiness	Not yet verified
Deferred topics	TLS renewal, rollback, live verification, production monitoring
Next recommended activity	Kubernetes architecture baseline
Next proposed project	Project 08 — Kubernetes Platform

Next session: Begin Kubernetes learning after reviewing the existing tutorial and verifying the local environment.

⸻

Progress tracking policy: Update this document only when supported by actual learning evidence, lab output, architecture assessment, or verified pull request history.