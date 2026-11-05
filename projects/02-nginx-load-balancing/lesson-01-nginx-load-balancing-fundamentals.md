# Lesson 01 — Nginx Load Balancing Fundamentals

> **Project:** 02 — Nginx and API Gateway  
> **Course:** SRE/DevOps Architect Journey  
> **Repository:** `samperay/sre-devops-architecture-labs`  
> **Document prepared:** 2026-11-05  
> **Learning approach:** LEARN → INTEGRATE → OPERATE; BUILD → UNDERSTAND → BREAK → FIX → DESIGN  
> **Learning status:** Foundational lab previously demonstrated; documentation reconstructed retrospectively.

## 0. Scope, provenance, and how to use this page

This standalone page restores the missing Lesson 01 training material without requiring the lab to be repeated. It combines the concepts, architecture, example commands, observed outcomes, troubleshooting discussions, and design lessons from our Project 02 learning history.

**Evidence convention:**

- **Observed in earlier lab:** Results explicitly recorded in the course history, including two Python backend services on ports `8081`/`8082`, Nginx on `8080`, successful load distribution, and an upstream failure producing HTTP `502`.
- **Reconstructed command/configuration:** A safe, representative way to reproduce the concept; not a claim that the command or exact file contents match the original terminal session byte-for-byte.
- **Future design:** An architectural application to the Todo system; not evidence that Todo already uses Nginx or the proposed topology.

**Repository note:** The root `ROADMAP.md` calls Project 02 **Nginx and API Gateway** and specifies reverse proxying, load balancing, routing, timeouts, and TLS boundaries. Repository progress metadata should be reconciled against actual merged PRs; this learning page is not itself proof of a merged implementation.

---

## 1. Objectives and prerequisites

By the end of Lesson 01, you should be able to:

1. Explain why a reverse proxy is placed in front of application processes.
2. Distinguish a forward proxy, reverse proxy, API gateway, and load balancer.
3. Draw the complete client → Nginx → backend request path.
4. Explain **upstream**, **round robin**, and **backend instance**.
5. Run two lightweight backend services and route traffic through one Nginx listener.
6. Observe distribution and explain what happens when a backend fails.
7. Distinguish a healthy Nginx process from a healthy end-to-end application.
8. Identify operational risks and appropriate production improvements.

**Lab environment previously used:** Ubuntu VM, Nginx `1.18.0`, Python 3 standard-library HTTP server, loopback backends on `127.0.0.1:8081` and `127.0.0.1:8082`, Nginx HTTP listener on port `8080`. No cloud infrastructure is required.

> **Safety:** All examples are local lab exercises. Before changing an existing Nginx installation, inspect enabled sites, choose a non-conflicting port, back up any file you intend to edit, and use `sudo nginx -t` before reload. Do not replace the default site or expose test backends publicly without a specific reason.

---

## 2. LEARN — What problem are we solving?

### 2.1 Direct access to application instances

Without a reverse proxy, clients need to know which backend address and port to contact:

```text
Client A --------------------> Application A :8081
Client B --------------------> Application B :8082
```

This exposes implementation details and makes routing, maintenance, and adding instances harder. If one instance fails, clients may need to change destinations themselves.

### 2.2 Reverse proxy as a stable entry point

A **reverse proxy** accepts client requests on behalf of backend services. The client addresses the proxy, while the proxy decides which internal service receives the request.

```text
                    HTTP request
Client --------------------------------> Nginx :8080
                                             |
                                 upstream project02_backends
                                         /       \
                                        v         v
                                  Backend A   Backend B
                                    :8081       :8082
```

Nginx can centralize routing, connection management, TLS termination (covered in Lesson 06), access logging, and selected failure-handling behavior. It does **not** automatically make an unhealthy application healthy.

### 2.3 Restaurant analogy

- **Customer:** API client or browser.
- **Reception desk:** Nginx reverse proxy, the single address customers know.
- **Two equivalent kitchen stations:** Backend A and Backend B serving the same kind of request.
- **Host assigning the next station:** Load-balancing algorithm.
- **Station closed:** Backend failure; reception must handle the impact.

**Todo mapping (proposed, not verified implementation):** A future Todo API might run as multiple equivalent service instances behind Nginx. Clients call a stable API endpoint instead of knowing individual instance addresses. The same pattern supports maintenance and scaling when the instances are genuinely interchangeable.

### 2.4 Terminology and boundaries

| Term | Meaning | Lesson 01 example |
|---|---|---|
| Forward proxy | Acts on behalf of clients when reaching external services | Not used |
| Reverse proxy | Acts on behalf of servers when receiving requests | Nginx on `:8080` |
| Backend / upstream server | Application process that handles proxied requests | Python servers `:8081`, `:8082` |
| Upstream group | Named set of possible destination servers | `project02_backends` |
| Load balancing | Choosing among eligible equivalent instances | Round robin |
| API gateway | Entry point that can route different paths/services and enforce policies | Covered in Lesson 05 |
| Health check | Evidence that a component or request path can serve traffic | Not equivalent to merely checking a process exists |
| 502 Bad Gateway | Proxy could not obtain a valid response from its upstream | Observed during backend failure |

**Important:** In this lesson, A and B are interchangeable targets for load balancing. Later, the API gateway lab routes `/api/` to A and `/users/` to B; those are **different service roles**, so you cannot assume failover from one route to the other.

---

## 3. BUILD — Lab topology and backend setup

### 3.1 Verify Nginx is available

**Objective:** Establish the proxy version and service state before making changes.

```bash
nginx -v
sudo systemctl status nginx --no-pager
```

**Expected:** An Nginx version and a service state such as `active (running)` if already started. The earlier lab baseline was Nginx `1.18.0` on Ubuntu. Exact package/version output depends on the host.

### 3.2 Start two independent test backends

**Objective:** Make two distinguishable HTTP servers so we can observe where Nginx forwards each request.

The following is a **reconstructed equivalent setup**, not the original session's exact command history. Run each server in a separate terminal, or manage them as explicit background test processes.

**Terminal A:**

```bash
mkdir -p /tmp/project02-backend-a
printf 'Response from Backend A - Port 8081\n' > /tmp/project02-backend-a/index.html
cd /tmp/project02-backend-a
python3 -m http.server 8081 --bind 127.0.0.1
```

**Terminal B:**

```bash
mkdir -p /tmp/project02-backend-b
printf 'Response from Backend B - Port 8082\n' > /tmp/project02-backend-b/index.html
cd /tmp/project02-backend-b
python3 -m http.server 8082 --bind 127.0.0.1
```

**Why bind to `127.0.0.1`?** These are intentionally local test services, not publicly exposed applications.

**Direct verification (third terminal):**

```bash
curl -sS http://127.0.0.1:8081/
curl -sS http://127.0.0.1:8082/
```

**Expected:** Distinguishable Backend A and Backend B responses. **Observed earlier:** Both backend ports were reachable and responses identified the backend.

> **Operational caution:** `python3 -m http.server` is a simple learning fixture, not a production application server.

---

## 4. BUILD — Nginx upstream and reverse proxy

### 4.1 Minimal configuration

**Objective:** Give clients one listener and distribute requests across two equivalent backends.

The following is a **representative configuration** matching the recorded topology. It is not a verified copy of the exact original configuration file.

```nginx
# In the http context, e.g. a dedicated file included by nginx.conf:
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}

server {
    listen 8080;
    server_name _;

    location / {
        proxy_pass http://project02_backends;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

**Explanation:**

- `upstream` names a pool of backend destinations.
- `server` inside `upstream` adds an eligible backend.
- `listen 8080` accepts incoming client requests on port 8080.
- `location /` matches requests under the root path.
- `proxy_pass` forwards the request to the upstream group.
- The `proxy_set_header` directives preserve useful request context. Only trust forwarded client-address headers when the surrounding proxy trust boundary is designed correctly.
- Without another balancing directive, Nginx uses **round robin** for this basic upstream configuration.

**Port safety:** `listen 8080` commonly binds available network interfaces unless constrained elsewhere. For a strictly local reconstruction, `listen 127.0.0.1:8080;` is safer, but that would differ from the previously observed `0.0.0.0:8080` listener. Do not change the existing lab listener solely to match this document.

### 4.2 Validate and reload

**Objective:** Catch syntax problems before applying configuration changes.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo ss -lntp | grep ':8080'
```

**Expected:** Syntax test succeeds; Nginx reloads without replacing the entire service; port `8080` is listening. **Previously observed:** Nginx was listening on `0.0.0.0:8080` and the load-balancing tests worked.

**Why reload instead of restart?** A graceful reload applies valid configuration with less disruption to existing connections. Always verify the effective configuration and request behavior after reloading.

---

## 5. UNDERSTAND — Round-robin distribution

### 5.1 Send multiple requests through the proxy

**Objective:** Observe that the client uses one address even though multiple backends respond.

```bash
for i in 1 2 3 4 5 6; do
    curl -sS http://127.0.0.1:8080/
done
```

**Illustrative output:**

```text
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
```

**Previously observed:** Requests were distributed between the two backend ports. The exact order is not a contractual guarantee; connections, active upstream state, and configuration can affect observed distribution.

### 5.2 What round robin does—and does not do

Round robin selects successive eligible backend servers in turn. It is simple and useful when instances have similar capacity and request cost.

It does **not** guarantee:

- Identical CPU utilization across instances.
- Equal request duration or equal concurrent load.
- Application-level readiness.
- Session affinity.
- Automatic recovery of every failed in-flight request.

**Architect question:** If Backend A is much slower than Backend B, would equal request counts imply equal load? **No.** Request cost, latency, and concurrency also matter. This motivates later discussion of least-connections, weighting, and health-aware routing.

---

## 6. BREAK — Backend failure and HTTP 502

### 6.1 Controlled failure scenario

**Objective:** Learn to distinguish proxy availability from upstream availability.

**Earlier lab observation:** Stopping a backend produced an HTTP `502` in the relevant test. This is recorded evidence, not a guarantee that every single request to a two-server upstream will return 502: Nginx may retry another eligible upstream depending on the failure type, request method, and configuration.

For a safe reproduction, stop only a known test backend (for example, press `Ctrl+C` in its dedicated `python3 -m http.server` terminal). Do not kill unrelated services or edit production configuration.

```bash
curl -i http://127.0.0.1:8080/
```

**Possible observations:**

- `HTTP/1.1 200 OK` from the remaining healthy backend.
- `HTTP/1.1 502 Bad Gateway` if Nginx cannot obtain a valid upstream response and no successful retry occurs.
- A temporary mixture depending on which server is selected and Nginx's upstream failure handling.

**Key distinction:** A running Nginx process is not proof that every application request can succeed.

### 6.2 Troubleshooting decision tree

```text
Client reports failure
        |
        v
Can the client connect to Nginx :8080?
        | no  -> listener, firewall, binding, service status
        | yes
        v
Does Nginx return 200, 502, 504, or another code?
        | 502 -> upstream connection/response failure
        | 504 -> upstream timeout
        | 200 -> inspect body; did the correct backend respond?
        v
Can the Nginx host reach each backend directly?
        | no  -> process, port, bind address, routing
        | yes -> inspect proxy config, logs, timeouts, backend behavior
```

**Safe diagnostic commands:**

```bash
sudo nginx -t
sudo ss -lntp | grep -E ':8080|:8081|:8082'
curl -i --max-time 5 http://127.0.0.1:8081/
curl -i --max-time 5 http://127.0.0.1:8082/
curl -i --max-time 5 http://127.0.0.1:8080/
sudo tail -n 30 /var/log/nginx/error.log
```

**HTTP error correction from later discussion:**

- `502 Bad Gateway`: proxy cannot obtain a valid upstream response, including certain connection failures.
- `504 Gateway Timeout`: proxy waited too long for an upstream response.
- A **direct** request to a stopped Python server commonly produces a connection error rather than an HTTP 502, because no gateway is generating the status code.

---

## 7. FIX — Restore service and validate the request path

**Objective:** Demonstrate recovery after the controlled backend interruption.

1. Restart the stopped test backend using its original command in its dedicated terminal.
2. Confirm the backend responds directly.
3. Confirm the Nginx endpoint responds.
4. Repeat several requests to verify both backends are again represented.
5. Inspect Nginx error logs if behavior differs from expectations.

```bash
curl -sS http://127.0.0.1:8081/
curl -sS http://127.0.0.1:8082/
for i in 1 2 3 4; do curl -sS http://127.0.0.1:8080/; done
```

**Expected:** Both backends are reachable and proxied requests succeed. Do not infer complete recovery solely from a single successful request; sample enough requests to exercise both destinations.

---

## 8. INTEGRATE — How this applies to the Todo application

This section is **architectural design guidance**, not a statement of currently implemented Todo functionality.

```text
                  Browser / API client
                          |
                          v
                    Stable API URL
                          |
                          v
                       Nginx
                          |
                   load balancing
                      /       \
                     v         v
                Todo API A  Todo API B
                     \         /
                      v       v
                  Shared data store
```

**Requirements to decide before integration:**

1. Are API replicas **stateless** or do they store local session/task state?
2. Can both instances serve the **same endpoints** and use compatible configuration?
3. Where does shared persistent state live?
4. What constitutes **readiness** to receive requests?
5. How will authentication and client identity propagate safely?
6. Are write operations safe to retry after ambiguous failures?
7. What are the target availability, latency, and capacity requirements?

**Spec-driven integration workflow:** Requirements → Specification → Plan → Tasks → Implementation → Testing → CI → Pull Request. No Todo application code should be changed without explicit approval.

**Important distinction:** Running two processes behind Nginx does not provide high availability if both depend on one VM, one database, or one network path. Identify the shared failure domain.

---

## 9. OPERATE — Production SRE thinking

### 9.1 Signals to monitor

| Layer | Signal | Why it matters |
|---|---|---|
| Client → Nginx | Connection success, response code, latency | Detect user-visible impact |
| Nginx | Request rate, 5xx rate, upstream errors | Identify proxy/upstream failures |
| Backend | Readiness, error rate, latency, saturation | Distinguish overloaded vs unavailable instances |
| Host | CPU, memory, file descriptors, network | Identify resource bottlenecks |
| End-to-end | Representative API transaction | Verify useful application behavior |

**A healthy `/health` endpoint at the proxy does not prove that every backend or business operation works.** Later Lesson 05 exercises demonstrated that the gateway `/health` could return 200 while `/api/` returned 502 when Backend A was stopped.

### 9.2 Failure scenarios and design trade-offs

| Scenario | Likely impact | Architectural response |
|---|---|---|
| One equivalent backend stops | Reduced capacity, possible errors | Route to healthy replicas; verify retry policy |
| Both backends stop | API unavailable | Alert on end-to-end failure; restore capacity |
| Nginx stops | Entry point unavailable | Consider redundant ingress for production |
| Backend slows down | Latency, possible 504 | Timeouts, capacity controls, profiling |
| Burst traffic | Queueing, saturation | Capacity planning, rate limits, autoscaling where justified |
| Retry storm | Amplified backend load | Bounded retries, backoff/jitter, retry budgets |
| Non-idempotent write retried | Duplicate effects | Idempotency keys and atomic backend enforcement |

### 9.3 Architecture decision record (example)

**Decision:** Use Nginx as a stable HTTP entry point with a round-robin upstream for two equivalent test backends.

**Why:** Minimal moving parts; observable request distribution; appropriate for understanding reverse proxy and load-balancing behavior.

**Trade-offs:** Equal selection is not equal resource use; passive upstream failure handling is not a substitute for application readiness; a single Nginx instance is a single point of failure; test servers do not represent production application behavior.

**Alternatives to evaluate later:** Weighted round robin, least connections, platform-native Service load balancing, managed ingress, dedicated gateway solutions. Choose based on measured requirements rather than adding infrastructure by default.

---

## 10. Discussion notes and architect knowledge checks

**Q1. Why use Nginx rather than asking clients to select a backend?**  
A stable entry point hides instance addresses and centralizes routing and selected operational policies. It also creates an ingress dependency that must be operated.

**Q2. If Nginx responds, is the application healthy?**  
Not necessarily. The listener may be reachable while an upstream is unavailable or returns errors.

**Q3. What does HTTP 502 tell you?**  
A gateway/proxy could not obtain a valid upstream response. Investigate upstream connectivity and logs; do not assume the gateway process itself is down.

**Q4. What happens if one of two backends fails?**  
Behavior depends on retry rules, failure detection, the request method, and whether another eligible backend exists. Validate actual responses rather than promising uninterrupted service.

**Q5. Is round robin always the best choice?**  
No. It is a reasonable baseline for similar instances and request costs; uneven workloads may justify other algorithms or application-level controls.

**Q6. Can a failed `POST /todos` always be retried?**  
No. If the backend committed the write but the response was lost, retrying could duplicate work. A client-supplied idempotency key and atomic server-side deduplication can make this safer. This concept was refined in our later architecture discussion; it was not part of the original Lesson 01 implementation.

**Q7. What should an SRE do first when users report 502?**  
Verify user impact, identify the affected path, inspect proxy status/error logs, test upstreams directly from an authorized host, and check recent changes before choosing a recovery action.

---

## 11. Evidence and progress checkpoint

| Item | Evidence | Status |
|---|---|---|
| Nginx installed | Earlier Ubuntu lab baseline: Nginx 1.18.0 | Demonstrated |
| Two test backends | A on `127.0.0.1:8081`, B on `127.0.0.1:8082` | Demonstrated |
| Reverse proxy listener | Nginx on port `8080` | Demonstrated |
| Round-robin behavior | Requests returned responses from both backends | Demonstrated |
| Upstream failure | HTTP 502 observed in failure exercise | Demonstrated |
| Restoration and recovery | Discussed and exercised across Project 02 | Earlier-session evidence; exact Lesson 01 sequence not independently re-audited |
| Architecture explanation | Proxy, upstream, failure modes and monitoring discussed | UNDERSTOOD / APPLIED across later lessons |
| Lesson 01 Markdown | Previously missing; this file reconstructs it | Documented |
| Git PR/merge for this document | Not yet provided | Pending |

**Current learning assessment:** Lesson 01 fundamentals have been **APPLIED** in later gateway, failure, and TLS exercises. Do not infer `ARCHITECT READY` from this document alone. The formal repository tracker should be updated only after PR evidence is verified.

**Next in the lesson series:** Lesson 02 — Reverse Proxy and Load Balancing; Lesson 03 — Algorithms; Lesson 04 — Reliability, Timeouts, and Retries; Lesson 05 — API Gateway Routing; Lesson 06 — TLS/HTTPS and Security Boundaries. The operational follow-ups for Lesson 06 (renewal, rollback, live post-renewal verification, and production-grade certificate monitoring) remain deferred for later study.

---

## 12. Reference commands (quick lookup)

```bash
# Check the proxy
nginx -v
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo ss -lntp | grep -E ':8080|:8081|:8082'

# Test backends independently
curl -i --max-time 5 http://127.0.0.1:8081/
curl -i --max-time 5 http://127.0.0.1:8082/

# Test the single Nginx entry point
curl -i --max-time 5 http://127.0.0.1:8080/
for i in 1 2 3 4 5 6; do curl -sS http://127.0.0.1:8080/; done

# Investigate errors
sudo tail -n 30 /var/log/nginx/error.log

# Only after a validated configuration change
sudo nginx -t && sudo systemctl reload nginx
```

**Documentation principle:** Keep the exact commands and outputs from a future reproduction alongside the PR if a full audit is required. This retrospective lesson intentionally does not invent original timestamps, command histories, or merge evidence.
