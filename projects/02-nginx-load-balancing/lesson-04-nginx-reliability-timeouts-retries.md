# Project 02 — Lesson 04: Nginx Reliability, Timeouts, Retries & Failure Handling

**Repository:** `samperay/sre-devops-architecture-labs`  
**Branch:** `feature/project02-nginx-reliability-timeouts-retries`  
**Canonical document:** `projects/02-nginx-load-balancing/lesson-04-nginx-reliability-timeouts-retries.md` (adjust if your existing lesson lives elsewhere).  
**Progress:** APPLIED — exercises completed and verified against recorded terminal evidence (see Part II).  
**Prerequisites:** Ubuntu VM; Nginx 1.18.0; existing Lesson 03 site on `8080` with original backends `8081` and `8082`. Do not modify the Todo application.

> **Learning protocol:** Complete one numbered exercise at a time. Before executing a command, read its objective and expected observations. Share terminal output for review. Do not advance automatically. Use actual evidence rather than claiming expected results occurred.

> **Single-source lesson:** This document combines the original guided tutorial **and** the verified hands-on results, troubleshooting, command outputs, architectural reasoning, and cleanup. Part I is the reusable exercise guide; Part II records what happened in this learning session. No second Lesson 04 Markdown file is required.

## Contents

- **Part I — Guided tutorial:** concepts, analogy, safety, setup, commands, expected results, knowledge checks.
- **Part II — Completed lab record:** observed outputs, connection failure, 504, retries, passive health checks, `BrokenPipeError`, `nohup`, logs, restoration, decisions, and next-session checkpoint.

## Part I — Guided Tutorial

## Outcomes

By the end, explain the difference between connection failure, connection timeout, read timeout, upstream retry, and client-visible error; distinguish HTTP 502 from 504; explain why retries can duplicate non-idempotent operations; inspect error/access logs; and restore the lab safely. Architecture readiness requires reasoning and troubleshooting beyond simply running commands.

## LEARN — Architecture and mental model

```text
                      Client
                        |
                        v
                 Nginx gateway
             /  proxy to upstream \
            v                      v
       Backend A              Backend B
       (application)          (application)
```

**Restaurant analogy:** Nginx is the restaurant manager; backends are kitchens. A connection failure is a closed kitchen door. A connection timeout is waiting too long for the kitchen to answer. A read timeout is a kitchen that accepted an order but has not delivered the meal in time. A retry is sending the order to another kitchen. If the first kitchen was already preparing it, a retry can produce two meals.

**Todo mapping:** Client → Nginx → Todo API instance A/B. `GET /todos` is generally safe to repeat. `POST /todos` creates state and may create duplicates if retried without a deduplication mechanism. Do not assume the Todo application already implements idempotency keys.

### Key Nginx directives

| Directive | Meaning | Important nuance |
|---|---|---|
| `proxy_connect_timeout` | Deadline to establish connection to upstream | Connection refused is immediate failure, not a timeout. |
| `proxy_read_timeout` | Maximum inactivity between successive reads from upstream | Not necessarily a cap on total request duration. |
| `proxy_send_timeout` | Maximum inactivity between successive writes to upstream | Relevant for sending request data. |
| `proxy_next_upstream` | Conditions for trying another upstream | Defaults commonly include `error timeout`; inspect active configuration. |
| `proxy_next_upstream_tries` | Limit upstream attempts | `0` means no explicit limit beyond available peers. |
| `proxy_next_upstream_timeout` | Total time allowed for retries | Separate from per-attempt timeouts. |
| `max_fails`, `fail_timeout` | Passive upstream failure handling | Failure is learned from traffic; not a standalone active health probe. |

**502 versus 504:** `502 Bad Gateway` commonly indicates an invalid or failed upstream connection/response. `504 Gateway Timeout` commonly indicates that Nginx waited beyond an upstream timeout. Actual status depends on retry settings, whether another peer succeeds, and when response headers were sent. Diagnose with logs; don't infer root cause from status alone.

**Retry safety:** HTTP methods are not all equally safe to retry. Nginx does not normally retry non-idempotent methods such as POST once the request has been sent upstream unless `non_idempotent` is explicitly enabled. Even when the proxy does not retry, clients and other intermediaries may. Never turn on `non_idempotent` merely to make a demonstration work.

## INTEGRATE — Design choices for Todo (discussion only)

1. What is the client-visible response if one API instance refuses connections and the other is healthy?
2. If the API commits a new Todo item but its response times out, can the caller distinguish failure from success?
3. Would you use an idempotency key for creation requests? Where would its record be stored, and for how long?
4. Where should retry policy live: client, gateway, or application? Consider HTTP method, side effects, and request budget.

**Spec-driven path for any future Todo changes:** Requirements → Specification → Plan → Tasks → Implementation → Testing → CI → Pull Request. No application code changes in this lesson.

## OPERATE — Safe, isolated lab environment

**Isolation rule:** Keep the Lesson 02/03 site on `8080` and original backends on `8081/8082` untouched. Use temporary lab ports `8083` (Nginx), `8091` (slow/failure backend), and `8092` (fast backend). Verify ports are free before binding. Use only loopback addresses for lab backends.

### Section A — Baseline and safety checks

**Objective:** Confirm the branch, service state, existing config, and availability of temporary ports.

```bash
cd ~/sre-devops-architecture-labs
git branch --show-current
git status --short
sudo nginx -t
sudo systemctl is-active nginx
sudo ss -lntp | grep -E ':(8080|8081|8082|8083|8091|8092)\b' || true
sudo nginx -T 2>&1 | grep -A 5 'upstream project02_backends'
```

**Expected:** Branch `feature/project02-nginx-reliability-timeouts-retries`; Nginx syntax OK and active; `8080/8081/8082` already used; `8083/8091/8092` unused. Stop if temporary ports are occupied; do not kill unknown processes.

**Actual evidence:** _Pending terminal output._

### Section B — Create standalone test backends (not Todo)

**Objective:** Prepare controllable upstream behavior without touching production-like site configuration.

```bash
mkdir -p /tmp/project02/lesson04
cat > /tmp/project02/lesson04/backend.py <<'PY'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import time

PORT = int(os.environ.get('PORT', '8091'))
NAME = os.environ.get('NAME', 'slow')
DELAY = float(os.environ.get('DELAY', '0'))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(DELAY)
        payload = f'{NAME} backend response\n'.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            print('client disconnected before response', flush=True)

    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        self.rfile.read(size)
        print(f'{NAME}: POST received (simulated side effect)', flush=True)
        time.sleep(DELAY)
        payload = f'{NAME} POST processed\n'.encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            print('client disconnected after processing', flush=True)

print(f'{NAME} backend listening on 127.0.0.1:{PORT}, delay={DELAY}s', flush=True)
ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
PY
```

Start **two separate terminal sessions** (keep them open):

```bash
# Terminal A — slow backend
PORT=8091 NAME=slow DELAY=3 python3 /tmp/project02/lesson04/backend.py
```

```bash
# Terminal B — fast backend
PORT=8092 NAME=fast DELAY=0 python3 /tmp/project02/lesson04/backend.py
```

From a third terminal:

```bash
time curl -fsS http://127.0.0.1:8091/
time curl -fsS http://127.0.0.1:8092/
```

**Expected:** `slow backend response` in about 3 seconds; `fast backend response` nearly immediately. Both processes run only on loopback.

**Actual evidence:** _Pending terminal output._

### Section C — Add a temporary Nginx lab site

**Objective:** Observe gateway behavior with an isolated config on `8083`.

**Before writing:** Confirm port 8083 is free and inspect any existing file with the same name. Do not overwrite an existing site. Create the file only if absent.

```bash
sudo test ! -e /etc/nginx/sites-available/project02-lesson04 || echo 'STOP: lab config already exists'
sudo test ! -e /etc/nginx/sites-enabled/project02-lesson04 || echo 'STOP: lab site already enabled'
```

If both checks indicate no conflict, create:

```bash
sudo tee /etc/nginx/sites-available/project02-lesson04 >/dev/null <<'NGINX'
upstream project02_lesson04_backends {
    server 127.0.0.1:8091;
    server 127.0.0.1:8092;
}
server {
    listen 127.0.0.1:8083;
    server_name localhost;
    access_log /var/log/nginx/project02-lesson04-access.log;
    error_log /var/log/nginx/project02-lesson04-error.log info;
    location / {
        proxy_pass http://project02_lesson04_backends;
        proxy_connect_timeout 1s;
        proxy_read_timeout 1s;
        proxy_next_upstream error timeout;
        proxy_next_upstream_tries 2;
    }
}
NGINX
sudo ln -s /etc/nginx/sites-available/project02-lesson04 /etc/nginx/sites-enabled/project02-lesson04
sudo nginx -t
```

**Stop if validation fails; do not reload.** If valid:

```bash
sudo systemctl reload nginx
curl -i --max-time 8 http://127.0.0.1:8083/
```

**Expected:** An HTTP 200 may come from fast backend after slow backend times out. First request may depend on round-robin selection; use logs to identify actual attempts.

**Actual evidence:** _Pending terminal output._

### Section D — Connection refusal versus timeout

**Objective:** Distinguish immediate `ECONNREFUSED` from an elapsed connection timeout.

Stop only the lab **slow backend** in Terminal A with Ctrl+C; leave fast backend running. Then:

```bash
sudo ss -lntp | grep ':8091' || echo 'lab slow backend stopped'
for i in $(seq 1 4); do curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8083/; done
sudo tail -n 20 /var/log/nginx/project02-lesson04-error.log
```

**Expected:** With fast backend healthy, requests may still return 200. Logs may show `connect() failed ... while connecting to upstream` for 8091. **This is connection refusal, not proof of `proxy_connect_timeout` expiry.** A true connection-timeout lab requires an upstream that accepts no connection within the deadline; avoid firewall modifications in this lesson.

**Actual evidence:** _Pending terminal output._

### Section E — Read timeout and HTTP 504

**Objective:** Observe read timeout with no healthy alternate peer to mask it.

Restart slow backend in Terminal A (`DELAY=3`), then stop **only the lab fast backend** in Terminal B. For an unambiguous 504, use a temporary second location in the lab site with an explicit single slow upstream, or disable retries for this isolated test; validate before reload. Suggested additional block inside the lab `server`:

```nginx
location /slow-only/ {
    proxy_pass http://127.0.0.1:8091/;
    proxy_read_timeout 1s;
    proxy_next_upstream off;
}
```

Then:

```bash
sudo nginx -t && sudo systemctl reload nginx
time curl -i --max-time 8 http://127.0.0.1:8083/slow-only/
sudo tail -n 15 /var/log/nginx/project02-lesson04-error.log
```

**Expected:** `HTTP/1.1 504 Gateway Time-out` after roughly 1 second; error log typically shows `upstream timed out ... while reading response header from upstream`. The slow backend may finish its work after the client has received 504.

**Actual evidence:** _Pending terminal output._

### Section F — Retry behavior and operational trade-offs

**Objective:** Observe a retry masking a slow upstream failure. Restart fast backend. Use the original `/` location with two peers and `proxy_next_upstream error timeout; proxy_next_upstream_tries 2;`.

```bash
for i in $(seq 1 6); do curl -sS -w 'status=%{http_code} duration=%{time_total}s\n' http://127.0.0.1:8083/; done
sudo tail -n 30 /var/log/nginx/project02-lesson04-error.log
```

**Expected:** Some requests may be delayed about 1 second by a slow attempt, then succeed via fast backend; other requests may reach fast directly. Passive failure handling can temporarily avoid slow peer. Do not promise an exact split.

**Actual evidence:** _Pending terminal output._

### Section G — POST and idempotency reasoning

**Objective:** Show why an upstream can complete a side effect even when its response times out. **The lab only prints a simulated side-effect message; it does not create Todos or change persistent data.**

Use `/slow-only/` after slow backend is running:

```bash
time curl -i --max-time 8 -X POST -d 'example=1' http://127.0.0.1:8083/slow-only/
```

**Expected:** The gateway can return 504 after 1 second while the slow backend prints `POST received (simulated side effect)` and continues processing. Compare server output and gateway output. **Do not infer automatic POST retries.** Discuss how client retries could cause duplicate creation, and how idempotency keys plus a durable deduplication record could prevent it.

**Actual evidence:** _Pending terminal output._

### Section H — Logs and failure classification

**Objective:** Correlate timestamp, client request, upstream endpoint, error category, and response code.

```bash
sudo tail -n 30 /var/log/nginx/project02-lesson04-access.log
sudo tail -n 30 /var/log/nginx/project02-lesson04-error.log
```

Fill out an evidence table: request time, status, selected upstream(s), error, client impact, and whether the backend may still have completed work. Avoid claiming root cause from unrelated historical log lines.

**Actual evidence:** _Pending terminal output._

### Section I — Restore and verify environment

**Objective:** Remove only the temporary Lesson 04 lab site and stop only the temporary lab backends. **Do not touch** `project02-loadbalancer` or original 8080/8081/8082 servers.

1. Stop the two lab Python processes with Ctrl+C in their terminals.
2. Confirm the enabled lab file is the expected symlink and the available file is the expected lab config before deleting:

```bash
ls -l /etc/nginx/sites-enabled/project02-lesson04
sudo sed -n '1,100p' /etc/nginx/sites-available/project02-lesson04
```

3. Only if confirmed:

```bash
sudo rm /etc/nginx/sites-enabled/project02-lesson04
sudo rm /etc/nginx/sites-available/project02-lesson04
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl is-active nginx
for i in $(seq 1 6); do curl -fsS http://127.0.0.1:8080/; done | sort | uniq -c
sudo ss -lntp | grep -E ':(8083|8091|8092)\b' || echo 'Lesson 04 lab ports free'
```

**Expected:** Nginx active; original 8080 site returns A/B (typically 3/3 for six requests); lab ports unused. Keep the lab script in `/tmp` for optional reuse; do not remove other users' files.

**Actual evidence:** _Pending terminal output._

## Architect decision record — draft

**Decision question:** Which retries belong at the gateway and which belong in the application/client?  
**Candidate default:** Retry connection/timeout failures selectively for safe requests within a bounded latency budget; do not indiscriminately retry writes; implement application-level idempotency before permitting retries of state-changing operations.  
**Trade-offs:** Availability vs duplicated side effects; shorter timeouts vs false failures; more retries vs overload amplification.  
**Observability:** Response status, upstream response time, retry count/attempts (if logged), request ID, error type, and user-visible failure rate.  
**Security boundary:** Do not expose internal backend addresses or diagnostic logs to untrusted clients. Keep test servers loopback-only.

## Knowledge checks — answer after exercises

1. What is the difference between connection refusal and connection timeout?
2. Why can an HTTP 504 coexist with a successful database commit?
3. When is retrying a GET safer than retrying a POST? Are there exceptions?
4. How can retries amplify overload during a partial outage?
5. Which two signals would you alert on, and why?
6. Explain in three minutes whether Todo should rely on gateway retries for create operations.

## Evidence and progress checkpoint

| Section | Status | Evidence |
|---|---|---|
| A — Baseline | NOT STARTED | Pending |
| B — Backends | NOT STARTED | Pending |
| C — Temporary gateway | NOT STARTED | Pending |
| D — Connection failure | NOT STARTED | Pending |
| E — Read timeout | NOT STARTED | Pending |
| F — Retries | NOT STARTED | Pending |
| G — POST safety | NOT STARTED | Pending |
| H — Logs | NOT STARTED | Pending |
| I — Restoration | NOT STARTED | Pending |

**Next action:** Begin Section A only. Share actual output; update this file with verified evidence before moving to Section B.


---

## Part II — Actual Lab Execution, Troubleshooting, Evidence & Architecture Notes

**Date:** 1 November 2026  
**Project:** `sre-devops-architecture-labs` — Project 02, Nginx Load Balancing & API Gateway  
**Learning branch:** `feature/project02-nginx-reliability-timeouts-retries`  
**Suggested repository path:** `projects/02-nginx-load-balancing/tutorials/lesson-04-nginx-reliability-lab-results-and-troubleshooting.md`  
**Status:** **APPLIED (lab)** — the behavior described below was observed in the Ubuntu VM; this does **not** imply production deployment or architect-level mastery.  
**Scope:** Standalone Nginx and Python test backends. **No Todo application code was changed.**

> **Evidence policy:** “Observed” means the user shared terminal output during the lesson. “Inferred” means a technically plausible explanation supported by the configuration and timing, but not proven by per-request upstream tracing. Do not confuse sample outputs with recorded evidence.

---

#### 1. Purpose and learning outcomes

This lesson explored how a reverse proxy behaves when an upstream application is unavailable or slow. The goals were to:

- Distinguish connection refusal, connection timeout, read timeout, upstream failure, and client-visible HTTP status.
- Configure and observe `proxy_connect_timeout`, `proxy_send_timeout`, `proxy_read_timeout`, and `proxy_next_upstream`.
- Test a fallback/backup backend and understand retry-related latency and duplicate-work risks.
- Observe Nginx Open Source passive failure detection using `max_fails` and `fail_timeout`.
- Diagnose the Python `BrokenPipeError` caused by a caller abandoning a slow request.
- Explain why health endpoints, monitoring, and traffic-routing decisions are separate mechanisms.
- Restore the original Nginx load balancer safely, verify it, and retain the experiment configuration for reference.

#### LEARN → INTEGRATE → OPERATE

- **LEARN:** Timeouts, retry semantics, passive health checks, and failure modes.
- **INTEGRATE (design only):** Apply the same reasoning to future Todo API replicas, without assuming those replicas, health endpoints, or idempotency keys are already implemented.
- **OPERATE:** Introduce controlled failures, inspect logs and latency, and restore the lab.

#### 2. Restaurant analogy and Todo mapping

Imagine a restaurant with a front-desk manager (Nginx) and multiple kitchens (upstream applications):

1. **Connection refused:** A kitchen's door is closed; the manager immediately knows it cannot accept the order.
2. **Connection timeout:** The manager cannot establish contact within the allowed time.
3. **Read timeout:** The kitchen accepted the order but has not sent a response within the manager's waiting interval.
4. **Retry/failover:** The manager sends the request to another kitchen.
5. **Late completion:** The original kitchen may still prepare the meal after the manager has left, wasting work or causing duplicates.
6. **Passive health checking:** After enough failed orders, the manager temporarily stops selecting that kitchen; later it is eligible to receive an order again.
7. **Monitoring:** A supervisor observes delays and alerts staff. The supervisor's alert alone does not automatically change which kitchen receives orders.

**Todo application mapping (hypothetical):** Client → Nginx → Todo API replicas. Retrying a read-only request is often safer than retrying `POST /todos`: a create operation could commit successfully even when the response is lost. An application-level idempotency key and a durable deduplication record can help make retries safe, but these features were **not verified as implemented in Todo**.

#### 3. Verified lab topology

```text
                                Client (curl)
                                     |
                +--------------------+-------------------+
                |                                        |
                v                                        v
        Nginx original :8080                     Nginx lab :8084
        round-robin upstream                     isolated retry site
                |                                        |
          +-----+-----+                           primary C :8083
          |           |                           slow Python server
          v           v                           sleeps 5 seconds
    Backend A     Backend B                             |
    :8081         :8082                          read timeout 2s
    fast          fast                                  |
                                                     retry
                                                        v
                                                backup B :8082
```

**Environment:** Ubuntu VM, Nginx 1.18.0, Python 3.10. Original Nginx site was left intact on port 8080. Backend A and B returned identifying text. Slow Backend C ran a custom Python HTTP server and slept for 5 seconds before responding.

| Component | Address | Purpose | Final observed state |
|---|---|---|---|
| Original Nginx load balancer | `0.0.0.0:8080` | Round-robin A/B | Listening and functional |
| Backend A | `127.0.0.1:8081` | Original upstream | Functional in final test |
| Backend B | `127.0.0.1:8082` | Original upstream and retry backup | Functional in final test |
| Backend C | `127.0.0.1:8083` | Deliberately slow upstream | Used during tests; final process shutdown not verified |
| Isolated Nginx timeout site | `127.0.0.1:8084` | Timeout/retry experiments | Disabled; port no longer listening |

**Important discrepancy:** An earlier prepared Lesson 04 tutorial used *different hypothetical lab ports and paths*. This document records the **actual commands, paths, and ports used** in the completed session; do not copy expected results from the older tutorial as if they were executed.

#### 4. Original Nginx baseline

The original load balancer was configured separately from the timeout experiment:

**File:** `/etc/nginx/sites-available/project02-loadbalancer`

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

**Baseline check:**

```bash
sudo nginx -t
sudo systemctl is-active nginx
sudo ss -lntp | grep -E ':8080|:8081|:8082'
for i in $(seq 1 6); do
    curl -fsS http://127.0.0.1:8080/
done | sort | uniq -c
```

The original service was verified as round-robin, returning three responses from each backend in a six-request run. The same verification succeeded again after cleanup (see Section 12).

#### 5. Experiment A — Connection failure and automatic failover

**Objective:** Understand what happens when a selected upstream is not listening.

**Observed situation:** Backend A was unexpectedly absent from port 8081. A listener check returned no output:

```bash
sudo ss -lntp | grep ':8081'
```

Requests through the original load balancer still returned **HTTP 200** because another upstream remained available. The Nginx error log included a connection failure:

```text
2026/11/01 01:41:44 [error] ... connect() failed (111: Unknown error)
while connecting to upstream ... upstream: "http://127.0.0.1:8081/"
... host: "127.0.0.1:8080"
```

**Explanation:** Connection refusal is typically immediate: the TCP connection cannot be established because no process is accepting it. This differs from a *connection timeout*, where the connection attempt does not complete within the allowed period. Nginx can log a failed upstream attempt yet still return **200** to the client after selecting another backend.

**Resolution:** Backend A was restarted and checked directly. A subsequent six-request test through Nginx returned A=3, B=3. No change to the original upstream configuration was required.

**SRE lesson:** A successful client response does not mean every upstream attempt succeeded. Monitor upstream errors, not just overall HTTP 5xx counts.

#### 6. Experiment B — Read timeout with retry disabled

**Objective:** Isolate a read timeout and observe a client-visible **HTTP 504**.

#### Slow backend

**Path:** `/tmp/project02/slow-backend/server.py`  
**Port:** `127.0.0.1:8083`  
**Behavior:** Print that a request arrived, sleep for five seconds, then send a simple HTTP 200 response.

Start it in the foreground:

```bash
python3 /tmp/project02/slow-backend/server.py
```

Observed startup:

```text
Slow backend listening on 127.0.0.1:8083
```

A direct `curl` to port 8083 returned HTTP 200 in approximately **5.007693 seconds**. That confirmed the application was reachable but deliberately slow.

#### Isolated Nginx timeout configuration

**File:** `/etc/nginx/conf.d/project02-timeout-lab.conf`

```nginx
server {
    listen 127.0.0.1:8084;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_connect_timeout 2s;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;
        proxy_next_upstream off;
    }
}
```

After validating and reloading:

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -sS -o /dev/null \
  -w 'HTTP %{http_code}, total %{time_total}s\n' \
  http://127.0.0.1:8084/
```

**Observed:** `HTTP 504` in **2.003889 seconds**.

**Why:** Nginx connected to the backend, but no response arrived before the configured read-inactivity interval expired. Since retries were disabled, Nginx returned a gateway timeout to the caller.

**Precision:** `proxy_read_timeout` is a timeout **between successive upstream reads**, not necessarily a universal maximum duration for a complete request. Here the backend produced no response for five seconds, so a two-second read timeout was sufficient to reproduce the failure.

#### 7. Experiment C — Retry to a backup backend

**Objective:** Show how a retry can preserve HTTP success while adding latency.

The isolated lab configuration was changed to:

```nginx
upstream project02_retry_backends {
    server 127.0.0.1:8083;
    server 127.0.0.1:8082 backup;
}

server {
    listen 127.0.0.1:8084;
    server_name localhost;

    location / {
        proxy_pass http://project02_retry_backends;
        proxy_connect_timeout 2s;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;
        proxy_next_upstream error timeout;
        proxy_next_upstream_tries 2;
    }
}
```

**Directive meanings:**

| Directive | Meaning in this experiment |
|---|---|
| `backup` | Select B when the primary upstream cannot serve the request. |
| `proxy_next_upstream error timeout` | Permit another upstream attempt on qualifying errors/timeouts. |
| `proxy_next_upstream_tries 2` | Limit a request to at most two upstream attempts. |
| `proxy_connect_timeout 2s` | Bound connection-establishment time. |
| `proxy_send_timeout 2s` | Bound inactivity while sending request data upstream. |
| `proxy_read_timeout 2s` | Bound inactivity while waiting for/reading the upstream response. |

**Observed:**

```text
Response from Backend B - Port 8082
HTTP Status: 200
Total Time: 2.005445s
```

The Nginx error log confirmed the first attempt timed out while reading the response header:

```text
2026/11/01 05:28:17 [error] ... upstream timed out (110: Unknown error)
while reading response header from upstream ... upstream: "http://127.0.0.1:8083/"
... host: "127.0.0.1:8084"
```

**Interpretation:** The client received HTTP 200 from the backup backend, but the request still took about two seconds because Nginx waited for the primary attempt to time out first. **Availability was preserved, but latency was degraded.** A successful status alone is insufficient to establish compliance with an SLO (service-level objective).

#### Retry safety and duplicate work

- Retrying a GET is often appropriate, provided the endpoint is actually safe and the retry budget is bounded.
- Retrying a POST or another state-changing operation can repeat a side effect if the original upstream completed the work but failed to return a response.
- Nginx normally avoids retrying a non-idempotent request **after it has been sent upstream**, unless explicitly configured with `non_idempotent`; other clients or intermediaries may still retry.
- Idempotency keys should be validated and enforced by the application with suitable persistence; the proxy cannot reliably determine whether a business operation committed.
- Retries can amplify load during an outage. Limit attempts and total request budgets, and observe retry rates.

#### 8. Experiment D — Passive failure detection (`max_fails` and `fail_timeout`)

**Objective:** Observe temporary upstream exclusion after repeated qualifying failures.

The upstream section was changed while leaving the server block unchanged:

```nginx
upstream project02_retry_backends {
    server 127.0.0.1:8083 max_fails=3 fail_timeout=20s;
    server 127.0.0.1:8082 backup;
}
```

The user verified the file and syntax:

```bash
sudo grep -A 3 'upstream project02_retry_backends' \
  /etc/nginx/conf.d/project02-timeout-lab.conf
sudo nginx -t
```

**Observed:** The grep showed the two upstream definitions above, and `nginx -t` reported syntax OK and test successful. Nginx was reloaded.

#### Meaning of the settings

- `max_fails=3`: Three qualifying unsuccessful attempts are needed within the configured failure-counting interval before the peer is considered unavailable.
- `fail_timeout=20s`: The time window for counting qualifying failures **and** the approximate period the peer is considered unavailable after reaching the threshold.
- `proxy_next_upstream_tries=2`: A different control: the maximum number of upstream attempts **per client request**, not the health-failure threshold.
- `proxy_read_timeout=2s`: The upstream read-inactivity timeout, not the exclusion duration.

These controls solve different problems. Do not conflate them.

#### Evidence from error logs

```text
2026/11/01 05:59:23 [error] ... upstream timed out ... 127.0.0.1:8083
2026/11/01 05:59:25 [error] ... upstream timed out ... 127.0.0.1:8083
2026/11/01 05:59:27 [error] ... upstream timed out ... 127.0.0.1:8083
2026/11/01 06:01:32 [error] ... upstream timed out ... 127.0.0.1:8083
```

The three closely spaced timeouts are consistent with reaching the configured failure threshold. The later timeout is consistent with Backend C becoming eligible for another attempt. These are **not** a per-request upstream selection trace.

#### Five-request latency experiment

Command:

```bash
for i in $(seq 1 5); do
    curl -sS -o /dev/null \
      -w "Request $i: HTTP %{http_code}, time %{time_total}s\n" \
      http://127.0.0.1:8084/
done
```

**Actual terminal output:**

```text
Request 1: HTTP 200, time 2.002760s
Request 2: HTTP 200, time 0.001295s
Request 3: HTTP 200, time 0.001459s
Request 4: HTTP 200, time 0.000655s
Request 5: HTTP 200, time 0.000428s
```

**Interpretation:** The first request likely encountered a two-second timeout on C and succeeded via B. The next four requests were much faster, consistent with C being temporarily excluded and B handling requests immediately. All five were HTTP 200. This strongly supports passive failover, although upstream-specific access logs would be needed to prove each selection.

#### Recovery eligibility test

After waiting more than the 20-second exclusion interval, the user ran:

```bash
curl -sS \
  -w '\nHTTP Status: %{http_code}\nTotal Time: %{time_total}s\n' \
  http://127.0.0.1:8084/
```

**Actual output:**

```text
Response from Backend B - Port 8082

HTTP Status: 200
Total Time: 2.003567s
```

**Interpretation:** Consistent with C becoming eligible again, still taking too long, and the request being retried to B. The approximately two-second latency is evidence of a renewed slow attempt, but a fresh correlated upstream log would be needed to prove the exact route for this request.

**Important nuance:** Passive health checking does not continuously poll a failed backend or guarantee that it has recovered. Once eligible, it may be selected again and cause another user-visible delay. In Nginx OSS, failure counters may be maintained separately by worker processes unless the upstream uses an appropriately configured shared-memory `zone`; results can vary with worker routing.

#### Why 20 seconds is not a universal production setting

A 20-second exclusion does **not** directly add 20 seconds to every request. It changes backend eligibility. The trade-offs are:

- Too short: a persistently slow backend may be retried frequently, adding latency.
- Too long: recovered capacity remains unused longer than necessary.
- Any exclusion: surviving backends must have enough spare CPU, memory, connections, and concurrency capacity to absorb traffic.
- An aggressive `proxy_read_timeout` (2s here) can falsely classify legitimate 5s work as a failure.
- Choose thresholds using measured latency distributions, failure patterns, SLOs, and load tests—not a universal default.

#### 9. Troubleshooting — Python `BrokenPipeError`

**Observed command:**

```bash
python3 /tmp/project02/slow-backend/server.py
```

**Observed output (excerpt):**

```text
Slow backend listening on 127.0.0.1:8083
Request received. Sleeping for 5 seconds...
127.0.0.1 - - [01/Nov/2026 06:01:35] "GET / HTTP/1.0" 200 -
...
File "/tmp/project02/slow-backend/server.py", line 16, in do_GET
    self.wfile.write(body)
BrokenPipeError: [Errno 32] Broken pipe
```

#### Root cause and timeline

```text
Time 0s  Nginx forwards request to Backend C.
         Python handler starts sleeping for 5s.
Time 2s  Nginx reaches proxy_read_timeout and closes/abandons that
         upstream attempt; Nginx retries Backup B.
Time ~2s Client receives HTTP 200 from B.
Time 5s  Python attempts to write to the abandoned socket.
         The write fails: BrokenPipeError (EPIPE).
```

**Critical distinctions:**

- The two-second **delay is caused by Nginx waiting for the upstream timeout**, not by the later Python exception.
- The Python server's `200` log line does **not** prove the response reached the client. The failure occurred while writing the body to a closed connection.
- A request-handler exception does not necessarily mean the entire Python server process crashed.
- The original backend may continue consuming CPU, memory, or database resources after the caller has stopped waiting.
- This matters especially for operations with side effects: a timeout does not prove that the operation was rolled back.

**Optional lab-only noise reduction (not executed/verified):**

```python
try:
    self.wfile.write(body)
except BrokenPipeError:
    print('Client disconnected before response completed', flush=True)
```

This suppresses the traceback but does not prevent the timeout or cancel the work. A production solution must consider cancellation, bounded processing, idempotency, and observability.

#### 10. Troubleshooting — Why `nohup` was not writing updates

The slow server was started in the foreground:

```bash
python3 /tmp/project02/slow-backend/server.py
```

Therefore, its output appeared in the **terminal**, not in a `nohup` log. `nohup` was not involved in this invocation.

A different backend had previously been started using a background command of this form:

```bash
nohup python3 -m http.server 8081 \
  --bind 127.0.0.1 \
  --directory /tmp/project02/backend-a \
  >/tmp/project02/backend-a.log 2>&1 &
```

That redirects stdout and stderr to `/tmp/project02/backend-a.log`.

**If background logging is desired in a future lab (example only, not executed in this session):**

```bash
nohup python3 -u /tmp/project02/slow-backend/server.py \
  >/tmp/project02/slow-backend/server.log 2>&1 &
```

- `nohup`: prevents SIGHUP from terminating the process when its terminal disconnects; it is **not** a logging system.
- `>`: redirects standard output to a file.
- `2>&1`: redirects standard error to the same destination.
- `&`: starts the command in the background.
- `-u`: makes Python stdout/stderr unbuffered so log lines appear promptly.
- `print(..., flush=True)`: flushes an individual print immediately.

**SRE practice:** For real services, prefer a supervised service manager and centralized logs over unmanaged `nohup` processes.

#### 11. Troubleshooting — Nginx error logs and client status

The user inspected:

```bash
sudo tail -10 /var/log/nginx/error.log
```

Examples from the session:

```text
2026/11/01 01:41:44 [error] ... connect() failed (111: Unknown error)
... upstream: "http://127.0.0.1:8081/" ... host: "127.0.0.1:8080"

2026/11/01 05:28:17 [error] ... upstream timed out (110: Unknown error)
while reading response header from upstream
... upstream: "http://127.0.0.1:8083/" ... host: "127.0.0.1:8084"
```

| Observation | Interpretation | Caution |
|---|---|---|
| `connect() failed` | Upstream TCP connection failed, such as no listener. | Check the exact address, port, and listener state. |
| `upstream timed out ... reading response header` | Backend did not produce response headers before read timeout. | Backend may still be processing. |
| Client HTTP 504 | Nginx could not obtain a timely upstream response under the active retry policy. | A different backend may have changed the result. |
| Client HTTP 200 after a timeout log | A retry may have succeeded. | The successful status masks failed upstream attempts. |
| Fast HTTP 200 after failures | Consistent with temporarily excluding the slow peer. | Verify upstream selection before claiming exact routing. |

**Note:** The exact wording `Unknown error` in this Ubuntu environment should not distract from the numeric error codes and Nginx context: `111` denotes connection refusal, and `110` denotes timeout on Linux.

#### Better production observability (design recommendation, not implemented)

A dedicated Nginx access-log format could record `$request_id`, `$status`, `$request_time`, `$upstream_addr`, `$upstream_status`, `$upstream_response_time`, and `$upstream_connect_time`. This makes it easier to correlate a client request with multiple upstream attempts. Changes to logging configuration would need separate validation and approval.

Useful alerts include rising upstream timeout rate, 5xx rate, tail latency (p95/p99), retry count, backup-backend utilization, active connections, CPU/memory, and saturation. Alerts should be tied to user impact and actionable thresholds.

#### 12. Cleanup — Safely restore the original Nginx service

**Objective:** Disable the isolated experiment without deleting evidence or disturbing the original port 8080 site.

#### Step 1 — Preserve the lab configuration outside the active include directory

**Commands executed:**

```bash
sudo mkdir -p /etc/nginx/project02-lab-backup
sudo mv \
  /etc/nginx/conf.d/project02-timeout-lab.conf \
  /etc/nginx/project02-lab-backup/project02-timeout-lab.conf
sudo nginx -t
```

**Actual validation:**

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

**Why move instead of delete?** Nginx's normal `conf.d/*.conf` include no longer picks up the moved file. The configuration remains available for future review. The original `/etc/nginx/sites-available/project02-loadbalancer` was not modified.

#### Step 2 — Reload and verify listening ports

**Commands executed:**

```bash
sudo systemctl reload nginx
sudo ss -lntp | grep -E ':8080|:8084'
```

**Actual output:**

```text
LISTEN 0      511          0.0.0.0:8080       0.0.0.0:*    users:(("nginx",pid=223877,fd=8),("nginx",pid=162394,fd=8))
```

**Interpretation:** Nginx was listening on port 8080, and there was no listener shown for the isolated lab port 8084.

#### Step 3 — Verify round-robin remains healthy

**Command executed:**

```bash
for i in $(seq 1 6); do
    curl -fsS http://127.0.0.1:8080/
done | sort | uniq -c
```

**Actual output:**

```text
      3 Response from Backend A - Port 8081
      3 Response from Backend B - Port 8082
```

**Result:** Original Nginx listener and round-robin behavior were verified after cleanup. The isolated Nginx port 8084 was disabled. **Stopping the separate slow Python process on port 8083 was not verified**, so do not claim that every temporary process was removed.

**Optional future check, only if needed:**

```bash
sudo ss -lntp | grep ':8083' || echo 'No slow backend listener on 8083'
```

If the server is still running in its own terminal, stop it with **Ctrl+C** in that terminal. Do not indiscriminately kill processes.

#### 13. Health checks, external monitoring, and traffic routing

The architecture discussion distinguished three separate capabilities:

```text
Application /health endpoint ----> Monitoring / alerting ----> Engineer
            |                                  |
            |                                  +-- informs humans / automation
            |
            +-- must be integrated with a routing mechanism
                before it can automatically remove a backend

Client ----> Nginx ----> eligible upstream(s)
```

**User's design reasoning:** Introduce application health endpoints and external monitoring to identify unavailable or degraded backends, notify an engineer, and protect traffic capacity and latency during bursts.

**Refinement:** An endpoint and an alert do **not** automatically cause Nginx Open Source 1.18 to poll that endpoint or exclude the application. The basic upstream behavior tested here was **passive**: it inferred failures from real requests. Active probing requires a compatible load balancer, an appropriately supported module/solution, or integration with an orchestrator/service discovery system. Avoid introducing such infrastructure into this lab without a concrete requirement.

**Production design considerations:**

- Distinguish **liveness** (process is running) from **readiness** (instance can safely serve traffic).
- Health checks should be lightweight, meaningful, and protected from exposing sensitive internal details.
- Monitor latency, error rates, saturation, and available capacity, not just whether a process exists.
- Consider the consequences of a dependency outage: a health check that marks every replica unready can eliminate all serving capacity.
- Test failover under load, not only with five or six sequential requests.
- Choose failure thresholds and retry policies using actual workload characteristics and SLOs.

#### 14. Architecture decision record (learning exercise)

**Decision:** For a future multi-instance Todo API deployment, use bounded gateway retries for eligible transient upstream failures, and avoid blindly retrying state-changing operations.

**Context:** A slow instance may fail to respond before the gateway timeout but continue processing. Another instance may successfully serve a retry. The client sees success, but latency and duplicate-work risk remain.

**Options considered:**

| Option | Advantage | Risk / limitation |
|---|---|---|
| No retries | Predictable attempt count; no proxy retry amplification | A single transient upstream failure becomes client-visible |
| Bounded retries for eligible failures | Better availability for recoverable failures | Adds latency and load; requires method-aware safety |
| Unlimited/aggressive retries | Can hide some transient failures | Retry storms, saturation, unpredictable latency |
| Application-level idempotency for writes | Safer recovery from uncertain outcomes | Requires durable state and careful key/expiry semantics |
| Active health checking via additional system | Detects some failures before client traffic | Operational complexity and potential new failure modes |

**Recommended learning-level position:** Keep retries bounded and observable; set realistic timeout budgets; ensure remaining backends can handle failover; use application-level idempotency where required; add more infrastructure only when justified by requirements.

**Security boundaries:** Keep test backends bound to loopback; avoid exposing internal upstream addresses and logs; treat health endpoints and monitoring credentials as protected operational interfaces.

**Operational failure scenarios to rehearse later:**

1. All backends refuse connections.
2. One backend is slow but still processing writes.
3. Backup backend saturates after failover.
4. A recovered backend becomes eligible but is still unhealthy.
5. Monitoring reports healthy while application readiness is broken.
6. Multiple retries at gateway and client amplify a partial outage.

#### 15. Knowledge checks and demonstrated reasoning

| Topic | Evidence / answer | Assessment |
|---|---|---|
| Client success vs upstream failure | Recognized that a request can succeed via backup despite an upstream error. | UNDERSTOOD |
| POST retry risk | Identified duplicate work and the need for idempotency. | UNDERSTOOD |
| Timeout impact | Recognized that a successful retry can still violate latency objectives. | UNDERSTOOD |
| `fail_timeout` and capacity | Explained why 20s is not suitable for all services and that surviving backends need capacity. | UNDERSTOOD, with refinement |
| Health endpoints and monitoring | Proposed application health endpoints and external alerting to detect backend problems. | UNDERSTOOD, with routing-integration distinction |
| Passive health recovery | Initially expected continued routing to backup; corrected that the excluded peer becomes eligible again. | UNDERSTOOD after feedback; future review recommended |
| Troubleshooting and cleanup | Provided actual curl, Nginx error log, syntax validation, listener, and round-robin outputs. | APPLIED in lab |

**Not yet proven:** Production-scale performance, active health-check integration, capacity/load testing, request-correlated upstream logging, and a full architecture design defense. These are **not prerequisites to recording this lab as applied**, but are relevant before an `ARCHITECT READY` assessment.

#### 16. Final evidence checklist

| Exercise | Verified result | State |
|---|---|---|
| Original Nginx baseline | Nginx load balancer on 8080 with A/B backends | LAB COMPLETED |
| Connection failure | Missing A listener, Nginx upstream connection error, client 200 via available backend | LAB COMPLETED |
| Slow backend | Direct response took ~5.007693s | LAB COMPLETED |
| Read timeout without retry | HTTP 504 in ~2.003889s | LAB COMPLETED |
| Retry to backup | HTTP 200 from B in ~2.005445s | LAB COMPLETED |
| Passive failure config | `max_fails=3 fail_timeout=20s`, `nginx -t` successful | LAB COMPLETED |
| Passive exclusion | First request ~2s, next four ~0–1ms, all HTTP 200 | LAB COMPLETED (behavior supported by timing) |
| Recovery eligibility | Later HTTP 200 from B in ~2.003567s | LAB COMPLETED (behavior supported by timing) |
| Python disconnect | `BrokenPipeError` at `self.wfile.write(body)` | LAB COMPLETED |
| Nginx logs | Connection refused and read-timeout entries inspected | LAB COMPLETED |
| Config restoration | Timeout file moved out of active include path; `nginx -t` passed | LAB COMPLETED |
| Final listener check | Port 8080 listening, 8084 absent | LAB COMPLETED |
| Final functional check | A=3, B=3 | LAB COMPLETED |
| Slow Python process stopped | No terminal evidence provided | NOT VERIFIED |

#### 17. Progress checkpoint and next session

- **Project:** 02 — Nginx Load Balancing & API Gateway.
- **Lesson:** 04 — Nginx Reliability, Timeouts, Retries & Failure Handling.
- **State:** **APPLIED** (verified hands-on exercises and troubleshooting).
- **Strengths demonstrated:** Interpreting timeouts and failover, identifying retry trade-offs, capacity reasoning, reading logs, and restoring service safely.
- **Topics to revisit:** Worker-local passive health state, recovery probing, active vs passive health checks, and correlating upstream attempts to individual client requests.
- **Next project activity:** Commit this retrospective on `feature/project02-nginx-reliability-timeouts-retries`, open/review the PR, merge when checks pass. In a **new session and new branch**, inspect the current repository roadmap and begin the next unfinished Project 02 topic (likely path/host-based API gateway routing) before declaring the project complete.
- **Do not assume:** That this PR is already open or merged, that Lesson 05 is complete, or that the Todo API has been deployed behind this lab gateway.

#### Commit the single canonical lesson file

The document is intentionally consolidated. Commit **only this lesson file**; the earlier separate retrospective is not needed in the PR.

```bash
cd ~/sre-devops-architecture-labs
git branch --show-current
git status --short
# Save/copy this downloaded file over the original Lesson 04 path in your checkout.
git add projects/02-nginx-load-balancing/lesson-04-nginx-reliability-timeouts-retries.md
git diff --cached --check
git diff --cached --stat
git commit -m "docs(project02): consolidate nginx reliability tutorial and lab evidence"
git push -u origin feature/project02-nginx-reliability-timeouts-retries
```

If your existing file is in a different directory, stage that exact existing path instead. Check the PR diff and CI before merging.

---

**Final takeaway:** Nginx can preserve availability during upstream failures, but failover does not guarantee low latency, prevent duplicate side effects, or replace application health checks and observability. Reliability requires coordinated choices across timeout budgets, retry safety, backend capacity, monitoring, and recovery behavior.
