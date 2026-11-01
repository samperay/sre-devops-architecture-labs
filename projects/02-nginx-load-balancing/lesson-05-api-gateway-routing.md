# Project 02 — Lesson 05: Nginx API Gateway Routing

**Learning repository:** `samperay/sre-devops-architecture-labs`  
**Working branch during lab:** `feature/project02-api-gateway-routing`  
**Environment:** Ubuntu Server VM, Nginx 1.18.0, Python 3.10.12  
**Learning framework:** LEARN → INTEGRATE → OPERATE  
**Status:** Practical lab completed and recovery verified; Git commit/PR not verified.  
**Scope:** Standalone Python test backends; **not** an implementation of these routes in the Todo application.

> This document consolidates the architecture, explanations, commands, actual observations, failure investigation, recovery, security considerations, knowledge checks, and follow-up improvements from Lesson 05. Commands are intended for the isolated Ubuntu lab. Avoid applying the configuration unchanged to production.

---

## 1. Learning objectives and outcomes

By the end of the lesson, we aimed to:

1. Explain the difference between a reverse proxy, load balancer, and API gateway.
2. Understand Nginx prefix and exact `location` matching.
3. Explain how the optional URI in `proxy_pass` affects upstream paths.
4. Build path-based routing while preserving the earlier load-balancer configuration.
5. Distinguish gateway-only health from backend and end-to-end health.
6. Reproduce a backend outage, identify the resulting HTTP 502, and find supporting error-log evidence.
7. Restore the backend without reloading Nginx.
8. Reason about failure domains, security boundaries, and shared-dependency capacity.

**Verified outcomes:** The gateway returned HTTP 200 for `/health`, `/api/`, and `/users/` in the healthy state. Stopping Backend A caused `/api/` to return HTTP 502; Nginx logged a failed connection to `127.0.0.1:8081`. Restarting Backend A restored HTTP 200 without an Nginx reload.

## 2. Architecture: from load balancing to path-based routing

### 2.1 Restaurant analogy

A restaurant has a reception desk that directs customers to the right department:

- A request for food goes to the kitchen.
- A request about a bill goes to billing.
- A question about whether reception is open can be answered at reception.

The receptionist's ability to answer does **not** establish that the kitchen can cook or billing can process payments. Likewise, an API gateway can be healthy while an upstream service is down.

### 2.2 Original lab architecture: load balancing on 8080

```text
Client
  |
  v
Nginx :8080 (round-robin load balancer)
  |
  +-- Backend A :8081 (Python HTTP server)
  +-- Backend B :8082 (Python HTTP server)
```

Existing file: `/etc/nginx/sites-available/project02-loadbalancer`

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}

server {
    listen 8080;
    server_name _;

    location / {
        proxy_pass http://project02_backends;
    }
}
```

Here, **both backends are members of the same upstream group**. Requests matching `/` can be distributed among them. The backend selected does not depend on whether the URL starts with `/api/` or `/users/`.

### 2.3 New lab architecture: isolated gateway on 8085

```text
                             Ubuntu VM
                                |
                +---------------+----------------+
                |                                |
                v                                v
         Nginx :8080                      Nginx :8085
         Existing load balancer           New API gateway
                |                                |
           Round-robin                +-----------+-----------+
                |                     |           |           |
           A or B                    /api/      /users/     /health
                                      |           |           |
                                      v           v           v
                                   A :8081    B :8082      Nginx
```

The separate gateway port limits regression risk during experimentation: the existing listener on `8080` remains unchanged. **Port 8085 is a lab choice, not an API gateway standard.**

### 2.4 Reverse proxy vs forward proxy vs load balancer

| Component | Typical role |
|---|---|
| Forward proxy | Acts on behalf of clients making outbound requests. |
| Reverse proxy | Accepts client requests and forwards them to upstream servers. |
| Load balancer | Distributes traffic among interchangeable backend instances. |
| API gateway | Provides an API entry point with routing and potentially authentication, rate limiting, observability, and other policies. |

Nginx in this lesson acts as a **reverse proxy/API gateway**. Our `/api/` and `/users/` destinations are distinct services, not interchangeable failover targets.

---

## 3. LEARN — Nginx request matching and URI rewriting

### 3.1 A catch-all `location /` matches nested paths

The original load balancer used:

```nginx
location / {
    proxy_pass http://project02_backends;
}
```

`location /` is a prefix match that can match `/users/123`, `/api/orders`, and other paths. The absence of an explicit `/users/` location **does not by itself make Nginx return 404**.

We tested:

```bash
curl -i http://127.0.0.1:8080/users/123
```

Observed:

```http
HTTP/1.1 404 File not found
Server: nginx/1.18.0 (Ubuntu)
Content-Type: text/html;charset=utf-8
```

The response body included Python `http.server`'s familiar `Error code: 404` and `File not found` text. This strongly suggests the request reached a Python backend and the requested file/path did not exist. The `Server: nginx` header alone cannot prove whether a 404 originated at the gateway or upstream.

**Key distinction:** Correct routing and a successful application response are separate concerns.

### 3.2 `proxy_pass` with and without a URI

Consider the client request `GET /api/orders`.

**A. No URI after upstream host and port:**

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8081;
}
```

The upstream receives `/api/orders` (original URI in this simple prefix-matching case).

**B. URI `/` supplied after upstream host and port:**

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8081/;
}
```

The upstream receives `/orders`. Nginx replaces the matching location prefix `/api/` with the URI `/` supplied in `proxy_pass`.

| Client URI | Location | `proxy_pass` | Upstream URI |
|---|---|---|---|
| `/api/orders` | `/api/` | `http://127.0.0.1:8081` | `/api/orders` |
| `/api/orders` | `/api/` | `http://127.0.0.1:8081/` | `/orders` |
| `/api/users/123` | `/api/` | `http://127.0.0.1:8081/` | `/users/123` |
| `/users/` | `/users/` | `http://127.0.0.1:8082/` | `/` |

**Operational risk:** A mismatch between gateway rewriting and the backend's expected routes can produce 404s even when the backend is running.

**Nuance:** Nginx has additional URI-processing rules for regex/named locations, variables in `proxy_pass`, and rewrite directives. The examples above describe the simple prefix locations used in this lab.

### 3.3 Exact health route

```nginx
location = /health {
    default_type text/plain;
    return 200 "API Gateway is healthy\n";
}
```

`=` requests an exact match for `/health`. `return` generates the response inside Nginx; it does not contact either backend. Consequently, `/health` is a **gateway-local check**, not proof of end-to-end application readiness.

---

## 4. INTEGRATE — Baseline verification

### 4.1 Validate existing Nginx configuration

```bash
sudo nginx -t
sudo ls -l /etc/nginx/sites-enabled/
sudo cat /etc/nginx/sites-available/project02-loadbalancer
```

**Purpose:** Check configuration validity, enabled sites, and the existing load balancer before introducing changes.

Observed validation:

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

Enabled sites initially included `default` and `project02-loadbalancer`.

### 4.2 Check existing listeners

```bash
sudo ss -lntp | grep -E ':8080|:8081|:8082'
```

Observed:

```text
127.0.0.1:8081 ... python3
127.0.0.1:8082 ... python3
0.0.0.0:8080 ... nginx
```

`ss` confirms **listening sockets**, not that HTTP requests will succeed.

### 4.3 Verify backend HTTP responses directly

```bash
for port in 8081 8082; do
    echo "=== Backend on port $port ==="
    curl -sS -i "http://127.0.0.1:$port/"
    echo
done
```

Observed:

```text
=== Backend on port 8081 ===
HTTP/1.0 200 OK
Server: SimpleHTTP/0.6 Python/3.10.12
...
Response from Backend A - Port 8081

=== Backend on port 8082 ===
HTTP/1.0 200 OK
Server: SimpleHTTP/0.6 Python/3.10.12
...
Response from Backend B - Port 8082
```

These responses establish a known-good baseline and uniquely identify each backend.

### 4.4 Check availability of port 8085

```bash
sudo ss -lntp | grep ':8085' || echo "Port 8085 is available"
```

Observed:

```text
Port 8085 is available
```

This shows no matching TCP listener at that moment; it does **not** reserve the port.

---

## 5. INTEGRATE — Create the isolated gateway

### 5.1 Create the site file

```bash
sudo nano /etc/nginx/sites-available/project02-api-gateway
```

Content used and verified during the lab:

```nginx
server {
    listen 127.0.0.1:8085;
    server_name _;

    location /api/ {
        proxy_pass http://127.0.0.1:8081/;
    }

    location /users/ {
        proxy_pass http://127.0.0.1:8082/;
    }

    location = /health {
        default_type text/plain;
        return 200 "API Gateway is healthy\n";
    }
}
```

**What each directive does:**

| Directive | Explanation |
|---|---|
| `server` | Defines a virtual server. |
| `listen 127.0.0.1:8085` | Listens only on IPv4 loopback for this lab. |
| `server_name _` | Conventional placeholder name; not by itself a universal catch-all mechanism. |
| `location /api/` | Prefix match for the API route. |
| `proxy_pass http://127.0.0.1:8081/` | Sends API requests to A, replacing `/api/` with `/`. |
| `location /users/` | Prefix match for the users route. |
| `proxy_pass http://127.0.0.1:8082/` | Sends users requests to B, replacing `/users/` with `/`. |
| `location = /health` | Exact gateway-local health route. |
| `default_type text/plain` | Sets the health response media type. |
| `return 200 ...` | Responds directly from Nginx. |

**Security boundary:** `127.0.0.1` is reachable only from the local network namespace. `0.0.0.0` listens on all IPv4 interfaces but does not necessarily mean the service is reachable from the internet; routing and firewall policy still matter.

### 5.2 Inspect the file before enabling

```bash
sudo cat /etc/nginx/sites-available/project02-api-gateway
```

The actual output matched the configuration above.

### 5.3 Enable and validate

```bash
sudo ln -s /etc/nginx/sites-available/project02-api-gateway \
           /etc/nginx/sites-enabled/project02-api-gateway

ls -l /etc/nginx/sites-enabled/project02-api-gateway
sudo nginx -t
```

Observed symlink:

```text
/etc/nginx/sites-enabled/project02-api-gateway -> /etc/nginx/sites-available/project02-api-gateway
```

Observed syntax test:

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

**Safety practice:** Validate before reload. If `nginx -t` fails, do not reload; investigate the reported file and line number.

### 5.4 Reload and confirm both listeners

```bash
sudo systemctl reload nginx
sudo ss -lntp | grep -E ':8080|:8085'
```

Observed:

```text
LISTEN ... 127.0.0.1:8085 ... nginx
LISTEN ... 0.0.0.0:8080   ... nginx
```

**Meaning:** The new gateway listener was active while the original load-balancer listener remained active. A successful reload generally allows existing Nginx workers to drain connections while new workers use the updated configuration. Syntax validation alone would not have proved that the listener was activated.

### 5.5 Test the gateway-local health endpoint

```bash
curl -i http://127.0.0.1:8085/health
```

Observed:

```http
HTTP/1.1 200 OK
Server: nginx/1.18.0 (Ubuntu)
Content-Type: text/plain
Content-Length: 23

API Gateway is healthy
```

This checks the gateway's response path, not Backend A/B health.

### 5.6 Verify path-based routing

```bash
curl -i http://127.0.0.1:8085/api/
curl -i http://127.0.0.1:8085/users/
```

Observed:

```text
GET /api/   -> HTTP/1.1 200 OK -> Response from Backend A - Port 8081
GET /users/ -> HTTP/1.1 200 OK -> Response from Backend B - Port 8082
```

Because each `proxy_pass` includes `/`, the matched prefix is replaced with `/`; both Python servers serve their root `index.html` in this lab. **This is routing by URL path, not round-robin distribution between A and B.**

---

## 6. OPERATE — Controlled failure injection

### 6.1 Predict behavior before changing anything

If Backend A is unavailable but B is healthy:

| Request | Expected result | Reason |
|---|---|---|
| `GET /api/` | 502 Bad Gateway | Gateway cannot connect to A. |
| `GET /users/` | 200 OK | Route uses B, independently of A. |
| `GET /health` | 200 OK | Nginx handles it locally. |

The 502 expectation assumes a connection failure to a stopped local listener; different failures can produce different status codes.

### 6.2 Identify the test server before stopping it

```bash
sudo ss -lntp | grep ':8081'
```

Observed before failure:

```text
LISTEN ... 127.0.0.1:8081 ... users:(("python3",pid=242665,fd=3))
```

A controlled graceful termination was requested with `SIGTERM` targeting the verified test server PID:

```bash
sudo kill -TERM 242665
```

**Safety:** PIDs can be reused. Reconfirm the PID and process identity immediately before sending a signal. Never use the recorded historical PID on another machine or later session without checking.

### 6.3 Confirm the backend listener is gone

```bash
sudo ss -lntp | grep ':8081' || echo "Backend A is stopped"
```

Observed:

```text
Backend A is stopped
```

This proves there was no matching listening socket at that moment.

### 6.4 Reproduce the gateway error

```bash
curl -i http://127.0.0.1:8085/api/
```

Observed:

```http
HTTP/1.1 502 Bad Gateway
Server: nginx/1.18.0 (Ubuntu)
Content-Type: text/html

<html>
<head><title>502 Bad Gateway</title></head>
...
</html>
```

**Interpretation:** Nginx could not obtain a valid response from the configured upstream. HTTP 502 alone does not prove the exact cause; the log provides the supporting evidence.

### 6.5 Investigate the Nginx error log

```bash
sudo tail -n 20 /var/log/nginx/error.log
```

Actual relevant line:

```text
2026/11/01 21:17:42 [error] 254361#254361: *10 connect() failed (111: Unknown error) while connecting to upstream, client: 127.0.0.1, server: _, request: "GET /api/ HTTP/1.1", upstream: "http://127.0.0.1:8081/", host: "127.0.0.1:8085"
```

| Field | What it establishes |
|---|---|
| `connect() failed` | Nginx failed to establish an upstream connection. |
| `(111: Unknown error)` | Error number 111 on Linux corresponds to `ECONNREFUSED`; wording in this environment showed `Unknown error`. |
| `request: "GET /api/ HTTP/1.1"` | The failing client request. |
| `upstream: "http://127.0.0.1:8081/"` | The exact destination Nginx attempted. |
| `host: "127.0.0.1:8085"` | The gateway address requested by the client. |
| Timestamp | Supports correlation with the failed request (account for local time/time zones). |

**Evidence-backed incident summary:** Backend A was intentionally stopped. Nginx attempted a TCP connection to port 8081, received an error consistent with connection refusal, and returned HTTP 502 to the client. No Nginx configuration error was needed to explain this failure.

### 6.6 Common HTTP failure distinctions

| HTTP status | Typical interpretation | Important caveat |
|---|---|---|
| 200 | Request succeeded | One success does not establish overall health. |
| 202 | Request accepted for later processing | Does not mean asynchronous work completed. |
| 404 | Requested resource/route not found | May originate from gateway or upstream. |
| 502 | Gateway received no valid upstream response | Often connection refused or invalid response; inspect logs. |
| 503 | Service unavailable | Can arise from application or gateway policy/configuration. |
| 504 | Gateway timed out waiting on upstream | Inspect whether connect/read/send timeout was reached. |

**Connection refused vs timeout:** Refusal is generally prompt when the destination actively rejects the TCP connection, often because nothing is listening. A timeout means the operation did not complete before a configured deadline; it may involve packet filtering, network failure, or a slow/unresponsive upstream. Avoid diagnosing solely from status code.

---

## 7. OPERATE — Restore Backend A and verify recovery

### 7.1 Confirm application files still exist

```bash
ls -la /tmp/project02/backend-a
```

Observed:

```text
index.html
nohup.out
```

The original `index.html` was present. `nohup.out` was an output artifact from an earlier background execution.

### 7.2 Restart the lab server

The user chose a background process with explicit document directory and log redirection:

```bash
nohup python3 -m http.server 8081 \
  --bind 127.0.0.1 \
  --directory /tmp/project02/backend-a \
  >/tmp/project02/backend-a.log 2>&1 &
```

Observed shell response:

```text
[1] 263317
```

**Explanation:**

- `nohup` helps keep the process running after the terminal disconnects.
- `python3 -m http.server` starts a basic static HTTP server.
- `--bind 127.0.0.1` keeps it local.
- `--directory` specifies the served directory independently of the shell's current working directory.
- `>... 2>&1` redirects standard output and standard error to the same log.
- `&` launches the command as a background job.

The shell job/PID output proves launch was attempted, **not** that the server is healthy. The following HTTP test establishes recovery.

**Production note:** `nohup` and `python -m http.server` are suitable for this controlled lab, not as a production application service. Production deployments should use an appropriate process supervisor/orchestrator and production HTTP server.

### 7.3 Verify recovery through the gateway

**No Nginx reload was performed.**

```bash
curl -i http://127.0.0.1:8085/api/
```

Observed:

```http
HTTP/1.1 200 OK
Server: nginx/1.18.0 (Ubuntu)
Content-Type: text/html
Content-Length: 36

Response from Backend A - Port 8081
```

### 7.4 Recovery evidence table

| Stage | Backend A state | `/api/` result | Verified? |
|---|---|---|---|
| Initial baseline | Running | 200 | Yes |
| Failure injection | No listener | 502 | Yes |
| Restoration | Background server restarted | 200 | Yes |
| Nginx config/reload during recovery | Unchanged | Not required | Yes, based on lab sequence |

**Why no Nginx reload?** The gateway's upstream destination remained `127.0.0.1:8081`. Once a process resumed accepting connections there, subsequent proxy requests could succeed.

---

## 8. Troubleshooting runbook

### Symptom A — `/api/` returns 502, `/health` returns 200

**Hypothesis:** Gateway itself is responsive; failure likely involves the upstream request path.

Check in order:

```bash
# 1. Is the expected backend port listening?
sudo ss -lntp | grep ':8081'

# 2. Can we reach the backend directly?
curl -i http://127.0.0.1:8081/

# 3. Does the request fail only through the gateway?
curl -i http://127.0.0.1:8085/api/

# 4. What did Nginx report?
sudo tail -n 30 /var/log/nginx/error.log

# 5. What configuration would Nginx load?
sudo nginx -T
```

**Interpretation:** If direct backend access fails, investigate backend startup, bind address, port, process logs, and dependencies. If direct access works but gateway access fails, investigate Nginx routing, URI rewriting, upstream address, security controls, and logs. Do not conclude that Nginx itself is defective without evidence.

### Symptom B — 404 through gateway

1. Determine whether the request reached the backend.
2. Verify `location` matching and `proxy_pass` trailing slash.
3. Compare the backend's expected route with the URI Nginx sends.
4. Test the relevant upstream path directly.
5. Use access-log upstream fields where configured (`$upstream_status`, `$upstream_addr`) to help distinguish origin; a `Server: nginx` response header alone is insufficient.

### Symptom C — New port 8085 does not listen after reload

```bash
sudo systemctl status nginx
sudo nginx -t
sudo nginx -T
sudo journalctl -u nginx --no-pager -n 50
sudo ss -lntp | grep ':8085'
```

Check whether the site is enabled, whether the `listen` address/port is correct, and whether reload succeeded. Nginx can remain active with an older configuration even when a reload fails.

### Symptom D — Connection refused vs upstream timeout

- **Refused:** Confirm the upstream is listening on the configured address and port. Check process state and immediate error logs.
- **Timed out:** Inspect network path, firewall behavior, connect/read timeouts, backend saturation, and application latency.
- **Unexpected 502:** Look for invalid upstream response, connection reset, protocol mismatch, or other errors in the Nginx error log.

### Symptom E — Gateway `/health` is 200 but application work is failing

Do not equate a gateway-local 200 with application readiness. Check the real application path and dependencies, plus worker/queue progress if the architecture includes asynchronous processing.

---

## 9. Reliability, security, and architecture trade-offs

### 9.1 Isolation of the new configuration

**Decision:** Use `127.0.0.1:8085` in a separate site rather than replacing the existing `0.0.0.0:8080` load balancer.

**Benefits:** Easier testing, less regression risk, preserves previous lab functionality, and reduces external exposure of the experimental gateway.

**Trade-off:** A localhost-only listener cannot be accessed directly from another VM. A later multi-VM or production design would need an intentionally designed ingress/network boundary.

### 9.2 Path-based routing is not automatic failover

Our gateway configuration maps `/api/` only to Backend A and `/users/` only to Backend B. If A fails, Nginx does **not** send `/api/` to B because B is a different service.

To achieve failover for an API service, deploy multiple **compatible API instances** and configure an appropriate upstream group. Then define health/failure handling and verify retry semantics. Do not silently redirect traffic to an unrelated service.

### 9.3 Health endpoint scope

| Check | Proves | Does not prove |
|---|---|---|
| Gateway `/health` | Nginx can return a local response | Backend availability or business success |
| Direct backend `/` | Test server can serve a simple request | Full application readiness |
| End-to-end business test | Specific workflow works at test time | Every workflow and sustained reliability |

For a real service, monitoring should consider request error rate, latency, saturation, dependency health, and representative user journeys.

### 9.4 Safety and rollback

Before modifying a running gateway, validate configuration and preserve a known-good state. For this lab, the original load balancer was preserved on port 8080. A future rollback of the *new gateway only*, if needed and approved, would disable its symlink, validate, and reload Nginx; do not remove unrelated sites or restart production services indiscriminately.

### 9.5 Production considerations not implemented here

This exercise intentionally did **not** implement TLS termination, authentication/authorization, rate limiting, request tracing, structured access logging, active health checks, service discovery, Kubernetes ingress, or production-grade application hosting. Those are potential future design topics, not verified current capabilities.

---

## 10. Extended architect exercise — Application readiness and database connection pools

This was a **hypothetical discussion** to strengthen operational reasoning. It was **not implemented in the Todo repository**.

### 10.1 Why HTTP 200 can be misleading

Imagine:

```text
Client -> Gateway -> Todo API -> Queue -> Worker -> Database
```

The API may return `202 Accepted` when a task is enqueued, while the worker fails to process it. The request was accepted; the business operation is not necessarily complete.

Useful signals include:

- Worker availability and readiness.
- Queue depth and age of oldest queued item.
- Task completion and failure rates.
- Worker logs and dependency errors.
- API error rates and latency.

A worker process marked `RUNNING` is not necessarily making progress.

### 10.2 Hypothetical incident: worker blocked on database

```text
Worker process:          RUNNING
Queue connection:        CONNECTED
CPU:                     5%
Memory:                  30%
Task completion:         0/min
Worker log:              Waiting for database connection
Database connections:    100/100
```

**Likely immediate bottleneck:** Database connection exhaustion. Adding more workers could worsen connection demand rather than fix throughput.

**Safe investigation:** Determine which clients own connections, whether pools are oversized, whether sessions/transactions are being returned correctly, and whether idle connections are expected pool capacity or leaked/stale sessions. Avoid indiscriminate connection termination.

### 10.3 Connection-pool arithmetic

**Example A:** Four application instances × 30 maximum connections each = **120 potential connections**. A database limit of 100 cannot satisfy all 120 simultaneously.

**Example B:** Five API instances × 20 = 100, plus four workers × 15 = 60; total potential demand **160**. Against a 200-connection limit, the theoretical remaining headroom is **40**, assuming no other clients.

Theoretical maximum pool capacity is **not** the same as current open connection count. Capacity planning must include other clients, reserved/admin connections, and connection spikes.

### 10.4 Restaurant analogy

The restaurant has 100 seats. Four tour operators each plan to bring 30 customers: total potential demand is 120. Even though each operator obeys its own limit, the combined demand exceeds restaurant capacity. Similarly, individually reasonable per-instance pool limits can collectively overwhelm a shared database.

---

## 11. Consolidated knowledge-check review

| Topic | Correct conclusion | Learning evidence |
|---|---|---|
| Prefix matching | `location /` matches nested paths | Corrected after initial misconception |
| Backend-generated 404 | Nginx can forward an upstream 404 | Observed Python-style 404 body |
| `proxy_pass` URI | Trailing `/` replaces matched prefix | Correctly explained after revision |
| Isolated gateway | Separate listener reduces regression risk | Correct answer |
| Loopback binding | `127.0.0.1` limits direct remote access | Correct with clarification about `0.0.0.0` |
| Gateway-local health | `/health` can return 200 when backends fail | Correct answer |
| Path-based failure | `/api/` does not automatically fail over to `/users/` service | Correct explanation |
| HTTP 502 vs 404 | Refused upstream connection yields 502 in this lab | Corrected and verified empirically |
| Recovery | Restoring A does not require Nginx reload | Correct answer, verified |
| Full application health | One HTTP 200 does not prove end-to-end readiness | Required coaching/revision |
| Worker progress | Running worker may still be blocked | Understood after discussion |
| Connection pool limits | Sum pool maxima across instances | Corrected, then solved 160/40 example |

**Assessment:** Lesson 05 practical work **APPLIED**. Architect-level mastery remains an ongoing goal, particularly production readiness, observability, security policy, and trade-off justification.

---

## 12. Command reference

| Command | Purpose |
|---|---|
| `sudo nginx -t` | Validate Nginx configuration syntax and loadability. |
| `sudo nginx -T` | Dump the complete configuration Nginx would load. |
| `sudo systemctl reload nginx` | Activate validated configuration without a full service restart. |
| `sudo systemctl status nginx` | Check service state. |
| `sudo journalctl -u nginx --no-pager -n 50` | Inspect recent service journal entries. |
| `sudo ss -lntp` | Inspect listening TCP sockets and processes. |
| `curl -i URL` | Show HTTP headers and response body. |
| `curl -sS -i URL` | Quiet progress output while showing errors and headers. |
| `sudo tail -n 20 /var/log/nginx/error.log` | Inspect recent Nginx errors. |
| `sudo cat FILE` | Read configuration contents. |
| `sudo ln -s SOURCE LINK` | Enable site by symbolic link. |
| `sudo kill -TERM PID` | Request graceful termination of a verified lab process. |
| `nohup ... >log 2>&1 &` | Start temporary background lab server with combined log redirection. |

---

## 13. Suggested repository structure and PR checklist

**Suggested location:**

```text
projects/02-nginx-load-balancing-api-gateway/
  lessons/
    lesson-05-api-gateway-routing-complete.md
```

If the repository already uses another lesson-document convention, follow that structure instead. This file path is a **suggestion**, not a verified existing directory.

Before opening the PR:

1. Confirm you are on `feature/project02-api-gateway-routing` and that the branch is up to date with the intended base.
2. Add this single comprehensive Markdown lesson in the project's established documentation location.
3. Verify all example commands and configuration are accurately scoped to the local VM.
4. Review the Markdown diff and ensure no secrets, tokens, or environment-specific sensitive values are committed.
5. Commit, push, and open a PR targeting the repository's current default branch (previously `master`; verify before opening).
6. In the PR description, include verified test evidence: gateway 200s, failure 502, error-log diagnosis, recovery 200.
7. Do not mark the PR merged or the repository updated until confirmed.

**Example commands** (replace the path with the repository's actual convention):

```bash
git status --short --branch
mkdir -p projects/02-nginx-load-balancing-api-gateway/lessons
# Copy this Markdown file into the lessons directory.
git add projects/02-nginx-load-balancing-api-gateway/lessons/lesson-05-api-gateway-routing-complete.md
git diff --cached --check
git diff --cached --stat
git commit -m "docs(project02): document API gateway routing and recovery lab"
git push -u origin feature/project02-api-gateway-routing
```

The commands above are examples and should be reviewed against the actual repository structure before execution. No repository write or PR creation is claimed by this document.

---

## 14. Final progress checkpoint

| Field | Verified status |
|---|---|
| Project | 02 — Nginx Load Balancing & API Gateway |
| Lesson | 05 — API Gateway Routing |
| Learning stages | LEARN, INTEGRATE, OPERATE exercised |
| Routing config | Created, enabled, syntax-validated, and activated |
| Gateway health | 200 verified |
| Backend A path `/api/` | 200 verified |
| Backend B path `/users/` | 200 verified |
| Failure injection | Backend A stopped; no listener on 8081 |
| Failure observation | `/api/` returned 502 |
| Log diagnosis | Connection failure to 127.0.0.1:8081 confirmed |
| Recovery | Backend A restarted; `/api/` returned 200 without Nginx reload |
| Knowledge checks | Completed with corrections on 404/502, URI rewriting, readiness, and pool sizing |
| Competency state | **APPLIED** (not yet ARCHITECT READY) |
| Git commit/PR | Not verified |
| Next recommended step | Review, commit, and PR this lesson; then choose the next scoped lesson |

### Resume/interview evidence (only after repository work is verified)

> Designed and validated an isolated Nginx API gateway with path-based routing and URI rewriting; performed controlled upstream failure injection, diagnosed HTTP 502 using Nginx logs, and verified recovery without proxy reload.

### Architecture interview prompts for later revision

1. When should two paths route to separate services versus instances of the same service?
2. What failure modes can a gateway-local `/health` endpoint miss?
3. How would you add TLS, authentication, and rate limiting without duplicating policy in every backend?
4. How would you design safe retries for non-idempotent API requests?
5. What metrics and logs would you use to distinguish upstream connection failures, timeouts, and application 5xx responses?
6. How would you migrate this single-VM lab to a multi-node design while preserving security boundaries?

**End of Lesson 05.**
