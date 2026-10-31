# Project 02 — Lesson 03: Nginx Load-Balancing Algorithms

> **Track:** SRE & DevOps Architect Journey  
> **Branch:** `feature/project02-load-balancing-algorithms`  
> **Repository path:** `projects/02-nginx-load-balancing/tutorials/lesson-03-load-balancing-algorithms.md`  
> **Status:** APPLIED — labs completed, environment restored; documentation ready for review.  
> **Approach:** LEARN → INTEGRATE → OPERATE → Review → Document → PR

## Learning outcomes

By the end of this lesson, explain and demonstrate: default round-robin, weighted round-robin, least-connections, IP-hash client affinity, trade-offs, security boundaries, operational signals, and how to select an algorithm based on workload evidence.

## Starting architecture and verified evidence

The existing lab has one Nginx reverse proxy and two Python HTTP servers on one Ubuntu VM:

```text
Client -> Nginx 0.0.0.0:8080
                    |
                    +--> Backend A 127.0.0.1:8081
                    +--> Backend B 127.0.0.1:8082
```

**Verified at the start of this lesson:** `ss -lntp` showed both Python backends and Nginx listening on their expected ports. **Now verified:** HTTP responses, current configuration, weighted distribution, least-connections, and IP hash. Previous Lesson 02 demonstrated round-robin, partial-backend failure, and recovery.

This is a **single-VM learning environment**, not a highly available deployment. Do not modify the existing port-80 site. No Todo application code changes are needed.

---

# Part I — LEARN

## 1. The restaurant analogy

Imagine a restaurant with two kitchens. Customers give orders to the receptionist (**Nginx**), who chooses a kitchen (**backend**) for each order.

- **Round-robin:** Give the next order to the next kitchen in rotation.
- **Weighted round-robin:** Give Kitchen B more orders if its tested capacity is greater.
- **Least connections:** Prefer the kitchen with fewer *currently active orders* (connections), subject to weights.
- **IP hash:** Routinely send customers from the same source address to the same kitchen, while the upstream membership remains stable.

**Todo mapping:** In a possible future architecture, Nginx could distribute requests between two Todo API instances. That is a design illustration, **not a claim that Todo currently runs multiple API replicas**. API authentication, persistence, and session handling would need review before deploying such a design.

## 2. Architecture and algorithms

### 2.1 Default round-robin

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

Without an alternative method, Nginx uses weighted round-robin with default server weights of 1. For equal weights and healthy peers, requests commonly alternate. Distribution is not a promise about equal CPU usage, latency, or application work.

### 2.2 Weighted round-robin

```nginx
upstream project02_backends {
    server 127.0.0.1:8081 weight=1;
    server 127.0.0.1:8082 weight=3;
}
```

With both servers healthy, this aims for roughly **25% A / 75% B** over enough requests. The weight is an operator-chosen relative share, not an automatic CPU measurement. More CPU cores do not necessarily mean proportionally greater application throughput.

### 2.3 Least connections

```nginx
upstream project02_backends {
    least_conn;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

`least_conn` prefers the peer with fewer active connections, accounting for weights. It does **not** measure request cost, queue depth inside the application, or CPU utilization. A series of short sequential requests may look much like round-robin; concurrency is needed for a meaningful demonstration.

### 2.4 IP hash

```nginx
upstream project02_backends {
    ip_hash;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

`ip_hash` chooses a backend based on client IP. Requests from the same apparent client IP typically select the same peer while the pool is stable and healthy. In this lab, `curl` originates from **127.0.0.1**, so repeatedly hitting one backend is expected. This does not demonstrate behavior across distinct real clients. Proxies and NAT may cause many clients to share an apparent source IP. Affinity is not a substitute for shared session storage or stateless design.

### 2.5 Selection trade-offs

| Algorithm | Strength | Limitation | Consider when |
|---|---|---|---|
| Round-robin | Simple baseline | Ignores work duration | Similar instances and requests |
| Weighted round-robin | Supports unequal tested capacity | Manual weights can become stale | Different backend capacity |
| Least connections | Responds to concurrent connection imbalance | Connections ≠ CPU or workload | Long-lived or variable-duration connections |
| IP hash | Approximate client affinity | NAT/proxy skew, uneven traffic, failover breaks affinity | Legacy affinity requirement; evaluate alternatives |

**Architect question:** Why might an equal-weight policy be preferable even when one machine has more CPU? Think about latency, dependencies, database bottlenecks, and measured throughput.

---

# Part II — INTEGRATE: Lab specification

## 3. Requirements

- **R1:** Preserve the default Nginx site and existing backends.
- **R2:** Make one algorithm change at a time.
- **R3:** Validate configuration **before** reload.
- **R4:** Capture direct backend responses and proxy responses.
- **R5:** Restore the original round-robin configuration after experiments.
- **R6:** Record **actual** evidence only after running commands.
- **R7:** Do not install infrastructure or modify Todo.

## 4. Safe execution plan

> **Run each lab section, then stop for review before the next section.** All commands are provided upfront for self-study. A passing syntax test is not proof of correct traffic distribution.

### Section A — Baseline (exercise 01 verified, exercise 02 pending)

**Objective:** Verify HTTP functionality and capture the current Nginx site before changes.

```bash
cd ~/sre-devops-architecture-labs
git branch --show-current
sudo cat /etc/nginx/sites-available/project02-loadbalancer
curl -sS http://127.0.0.1:8081/
curl -sS http://127.0.0.1:8082/
curl -sS http://127.0.0.1:8080/
```

**Expected:** The correct lesson branch, an upstream with two peers, and responses identifying Backend A or Backend B. If the configuration differs, **do not overwrite it**; share it for review.

**Observe:** Which address is the client entry point? Are the backends accessible only via loopback? Does `proxy_pass` point to the upstream group?

**Checkpoint A:** Share configuration and responses. **Status: PENDING.**

### Section B — Weighted round-robin

**Objective:** Change request allocation to approximately 1:3 without changing backend processes.

**Safety first:** Make a backup before editing:

```bash
sudo cp -p /etc/nginx/sites-available/project02-loadbalancer \
  /etc/nginx/sites-available/project02-loadbalancer.lesson03.bak
sudo nano /etc/nginx/sites-available/project02-loadbalancer
```

In the existing `upstream project02_backends` block, set:

```nginx
upstream project02_backends {
    server 127.0.0.1:8081 weight=1;
    server 127.0.0.1:8082 weight=3;
}
```

**Keep the existing `server { ... }` block unchanged.** Then:

```bash
sudo nginx -t
# Run the next command ONLY if the syntax test succeeds:
sudo systemctl reload nginx
```

Measure a small sample:

```bash
for i in $(seq 1 40); do
    curl -fsS http://127.0.0.1:8080/
done | sort | uniq -c
```

**Expected:** Approximately 10 responses from A and 30 from B, potentially with variation due to runtime behavior and upstream state. `curl -f` makes HTTP errors visible via exit status, but the pipeline alone may not reliably surface every failed request; inspect errors if output totals are below 40.

**Observe:** Did all 40 requests succeed? Is the ratio close to 1:3? Why should this be measured over more than four requests?

**Checkpoint B:** Share `nginx -t`, reload result, and counts. **Status: PENDING.**

### Section C — Least connections (controlled concurrency)

**Objective:** Understand why active connections, not historical request counts, affect selection.

**First, restore equal peer weights** and add `least_conn;` at the beginning of the upstream block:

```nginx
upstream project02_backends {
    least_conn;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

Apply safely:

```bash
sudo nginx -t
# Only after success:
sudo systemctl reload nginx
```

Run a concurrent request sample (uses `xargs`, already standard on Ubuntu):

```bash
seq 1 40 | xargs -P 8 -I '{}' sh -c 'curl -fsS http://127.0.0.1:8080/' \
  | sort | uniq -c
```

**Expected:** Both backends respond, but the exact distribution is **not guaranteed**. The built-in Python HTTP server can respond too quickly to create sustained concurrent connections, so this exercise demonstrates the limits of the measurement rather than proving a least-connections advantage.

**Observe:** Are there long-lived active connections? Why might least-connections look similar to round-robin with fast requests? What additional test server behavior would create a convincing comparison?

**Checkpoint C:** Share config validation and counts. **Status: PENDING.**

### Section D — IP hash and affinity

**Objective:** Observe repeated selection from one source IP.

Replace the upstream block with:

```nginx
upstream project02_backends {
    ip_hash;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

Then:

```bash
sudo nginx -t
# Only after success:
sudo systemctl reload nginx
for i in $(seq 1 12); do
    curl -fsS http://127.0.0.1:8080/
done | sort | uniq -c
```

**Expected:** All or nearly all successful requests from `127.0.0.1` typically reach one backend, provided peer membership and availability remain stable. This lab uses one apparent client IP and cannot prove multi-client distribution.

**Observe:** Why is IP-based affinity risky behind a NAT gateway? What happens to affinity if the chosen backend fails?

**Checkpoint D:** Share output and answers. **Status: PENDING.**

### Section E — Restore original configuration

**Objective:** Return the VM to the previously demonstrated default algorithm.

**Before restoring, inspect the backup and current file:**

```bash
sudo diff -u /etc/nginx/sites-available/project02-loadbalancer.lesson03.bak \
  /etc/nginx/sites-available/project02-loadbalancer || true
sudo cat /etc/nginx/sites-available/project02-loadbalancer.lesson03.bak
```

**Only if the backup is confirmed to contain the intended original configuration**, restore it:

```bash
sudo cp -p /etc/nginx/sites-available/project02-loadbalancer.lesson03.bak \
  /etc/nginx/sites-available/project02-loadbalancer
sudo nginx -t
# Only after success:
sudo systemctl reload nginx
for i in $(seq 1 6); do curl -fsS http://127.0.0.1:8080/; done
```

**Expected:** Both backends participate again. If the backup is incorrect, do not restore it; ask for review.

**Checkpoint E:** Share final configuration and responses. **Status: PENDING.**

---

# Part III — OPERATE

## 5. Troubleshooting decision tree

**No listener on port 8080**

```bash
sudo ss -lntp | grep ':8080' || true
sudo systemctl status nginx --no-pager
sudo nginx -t
```

**HTTP 502 / connection refused**

```bash
curl -v --max-time 5 http://127.0.0.1:8081/
curl -v --max-time 5 http://127.0.0.1:8082/
sudo tail -n 30 /var/log/nginx/error.log
```

**Unexpected distribution**

1. Verify the algorithm actually appears in the **active** Nginx configuration.
2. Check both backends are responding directly.
3. Ensure enough requests were sampled.
4. Check for failed peers and temporary exclusion.
5. For least-connections, verify there is sustained concurrency.
6. For IP hash, confirm whether clients share a source IP due to proxying/NAT.

**Safe rollback:** Validate the known-good backup before restoring it, then run `nginx -t` before reload. Avoid stopping or restarting Nginx unnecessarily.

## 6. Reliability and security review

- **Single point of failure:** One Nginx process group on one VM is still a SPOF.
- **Backend failure:** The other backend may serve traffic, but capacity is reduced.
- **Passive health behavior:** Nginx can mark a peer temporarily unavailable after failures; details depend on `max_fails`, `fail_timeout`, and proxy retry settings.
- **Monitoring:** Track request rate, error rate, p95/p99 latency, upstream failures, backend saturation, and capacity headroom.
- **Security boundary:** Backend services listen on loopback; Nginx is the externally reachable entry point on port 8080. This lab does not configure TLS, authentication, or rate limits.
- **Algorithm is not autoscaling:** Weights and connection-based selection do not create new capacity.

## 7. Architecture decision exercise

**Scenario:** Two Todo API instances sit behind Nginx. Instance A has 2 vCPUs; B has 6 vCPUs. Most requests are short, but a small percentage take several seconds. Users authenticate with bearer tokens. Both instances share the same database.

Write a short architecture decision record (ADR):

1. Which algorithm would you start with and why?
2. Which metrics would justify switching algorithms or weights?
3. How would you prevent database saturation?
4. Would you use IP hash? Why or why not?
5. What happens if Nginx itself fails?
6. How would you safely test and roll back the decision?

**Assessment rule:** Completing commands earns **LAB COMPLETED**. Demonstrating correct interpretation earns **UNDERSTOOD**. Justifying and operating a design in context supports **APPLIED**. **ARCHITECT READY** requires convincing security, reliability, performance, failure, and trade-off reasoning.

---

# Part IV — Actual Lab Commands, Outputs, and Learning Evidence

> **Evidence provenance:** Outputs below were supplied from the Ubuntu VM during Lesson 03. Do not confuse an example or expected result with measured evidence. This was a single-VM learning lab, not a production high-availability deployment.

## Section A — Baseline (LAB COMPLETED)

**Objective:** Confirm branch, backend health, and default round-robin configuration before changing routing.

```bash
git branch --show-current
sudo cat /etc/nginx/sites-available/project02-loadbalancer
curl -sS http://127.0.0.1:8081/
curl -sS http://127.0.0.1:8082/
curl -sS http://127.0.0.1:8080/
```

**Observed branch:** `feature/project02-load-balancing-algorithms`.

**Observed upstream:**

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
server {
    listen 8080;
    server_name _;
    location / { proxy_pass http://project02_backends; }
}
```

**Actual responses:**

```text
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
```

**Learning:** With no algorithm directive, Nginx uses round-robin. Both backends bind loopback; Nginx listens on port 8080. Two processes on one VM are not host-level HA.

## Section B — Weighted Round Robin (UNDERSTOOD)

**Objective:** Observe a 1:3 request allocation. Configuration used weights A=1 and B=3 according to the exercise; the exact weighted config text was not supplied in terminal evidence, so the observed counts alone cannot independently verify the configuration.

```bash
sudo nginx -t
sudo systemctl reload nginx
for i in $(seq 1 40); do curl -fsS http://127.0.0.1:8080/; done | sort | uniq -c
```

**Actual output:**

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
     10 Response from Backend A - Port 8081
     30 Response from Backend B - Port 8082
```

**Learning:** 10/40 = 25% A; 30/40 = 75% B, consistent with 1:3. Weights are static operator choices; they do not measure CPU, latency, or health automatically. Select them using measured throughput, CPU, memory, p95/p99 latency, and errors.

**Restaurant analogy:** A kitchen proven to have three times the capacity can be assigned three times as many orders. **Todo mapping:** Consider weights only if actual API replica capacity differs; this lab does not establish that Todo has multiple deployed replicas.

## Section C — Least Connections (UNDERSTOOD)

**Objective:** Distinguish *fewest active connections* from *fastest backend* and *lowest CPU*.

**Verified Nginx configuration:**

```bash
sudo nginx -T 2>&1 | grep -A 5 'upstream project02_backends'
```

```nginx
upstream project02_backends {
    least_conn;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

**Fast-backend control:**

```bash
seq 1 40 | xargs -P 8 -I '{}' sh -c 'curl -fsS http://127.0.0.1:8080/' | sort | uniq -c
```

```text
     20 Response from Backend A - Port 8081
     20 Response from Backend B - Port 8082
```

This 20/20 result is **inconclusive** for proving least-connections: fast requests may finish before concurrent upstream connections accumulate.

**Controlled slow-backend preparation:** Stop the original Backend A process using Ctrl+C, then verify:

```bash
sudo ss -lntp | grep ':8081' || echo 'Backend A stopped'
# Actual: Backend A stopped
```

Create `/tmp/project02/slow_backend.py` with a temporary threaded HTTP server:

```python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time

class SlowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(3)
        body = b"Response from Backend A - Slow (3 seconds)\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server = ThreadingHTTPServer(("127.0.0.1", 8081), SlowHandler)
print("Slow Backend A listening on 127.0.0.1:8081", flush=True)
server.serve_forever()
```

```bash
python3 /tmp/project02/slow_backend.py  # keep running in its own terminal
# in another terminal:
time curl -sS http://127.0.0.1:8081/
```

**Measured direct response:**

```text
Response from Backend A - Slow (3 seconds)
real    0m3.016s
user    0m0.005s
sys     0m0.005s
```

**Concurrent test:**

```bash
time (
    seq 1 40 | xargs -P 8 -I '{}' sh -c \
      'curl -fsS http://127.0.0.1:8080/' \
      | sort | uniq -c
)
```

**Actual output:**

```text
      3 Response from Backend A - Slow (3 seconds)
     37 Response from Backend B - Port 8082
real    0m3.054s
user    0m0.060s
sys     0m0.056s
```

**Learning:** A handled 7.5%, B handled 92.5%. A's slow requests held connections open, so the less-occupied B received most requests. `ThreadingHTTPServer` permitted overlapping A requests, explaining the ~3-second wall-clock time. This strongly supports least-connections behavior; deeper proof would instrument active upstream connections.

**Knowledge-check history:** The learner initially chose B when A had 2 active connections and B had 5; corrected understanding after explanation. With equal weights, A is selected (2 < 5), **even if A has 95% CPU**. Later correctly chose B when A had 10 connections and B had 3. **Least connections ≠ least CPU.**

**Restaurant analogy:** The receptionist selects the kitchen with fewer outstanding orders, not necessarily the kitchen with the most available CPU. **Todo mapping:** Requests of different duration may benefit from least-connections, subject to measurement.

## Section D — IP Hash (UNDERSTOOD)

**Objective:** Observe source-IP-based affinity and understand NAT concentration risk.

```nginx
upstream project02_backends {
    ip_hash;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx.service
for i in $(seq 1 10); do curl -fsS http://127.0.0.1:8080/; done | sort | uniq -c
```

**Actual output:**

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
     10 Response from Backend B - Port 8082
```

**Learning:** Ten requests from localhost consistently reached B. This establishes observed affinity for one source address, not balanced routing across multiple IPs. One corporate NAT IP may cause many employees to land on the same backend, regardless of CPU. IP affinity cannot restore process-local session data after a crash. Stateless bearer tokens or a shared session store can reduce dependency on stickiness, subject to application design.

## Section E — Failure Handling and Recovery (LAB COMPLETED)

**Objective:** Test request continuity after the IP-hash-selected backend fails, inspect logs, and verify restoration.

**E1 — Stop B, test through Nginx:**

```bash
# Ctrl+C in Backend B's terminal
sudo ss -lntp | grep ':8082' || echo 'Backend B stopped'
time curl -i --max-time 10 http://127.0.0.1:8080/
```

**Actual output:**

```text
Backend B stopped
HTTP/1.1 200 OK
Server: nginx/1.18.0 (Ubuntu)
Content-Type: text/plain
Content-Length: 43
Connection: keep-alive

Response from Backend A - Slow (3 seconds)
real    0m3.017s
```

**Learning:** The client received HTTP 200 through A while B was stopped. This proves service continuity for that request, not the exact upstream retry sequence. Nginx does not restart backend processes.

**E2 — Inspect error log:**

```bash
sudo tail -n 20 /var/log/nginx/error.log
```

**Relevant actual lines:**

```text
2026/10/31 11:54:53 [emerg] ... invalid number of arguments in "least_conn" directive in /etc/nginx/sites-enabled/project02-loadbalancer:3
2026/10/31 12:49:57 [error] ... connect() failed (111: Unknown error) while connecting to upstream, upstream: "http://127.0.0.1:8081/"
```

**Learning:** The first entry was a historical configuration error; later syntax tests passed. The connection error concerned **A:8081**, not B:8082, and occurred before the successful 12:56:17 response. Do not use an unrelated timestamp/backend as proof of the latest failure. The precise retry path remains unverified.

**E3 — Restart B and check recovery:**

```bash
python3 -m http.server 8082 --bind 127.0.0.1 --directory /tmp/project02/backend-b
# from another terminal:
curl -fsS http://127.0.0.1:8082/
# Actual: Response from Backend B - Port 8082
```

**Proxy remained on A:**

```bash
for i in $(seq 1 5); do curl -fsS http://127.0.0.1:8080/; done | sort | uniq -c
# Actual: 5 Response from Backend A - Slow (3 seconds)
```

A subsequent 15-second wait did not restore the initial B assignment. `nginx -T` still showed `ip_hash` with both upstreams. Worker inspection:

```bash
ps -eo pid,ppid,cmd | grep '[n]ginx'
```

```text
77833       1 nginx: master process /usr/sbin/nginx -g daemon on; master_process on;
152410  77833 nginx: worker process
```

After successful `nginx -t` and `systemctl reload nginx`, five further requests still reached A. Final direct/proxy checks:

```bash
curl -fsS --max-time 6 http://127.0.0.1:8081/
# Response from Backend A - Slow (3 seconds)
curl -fsS --max-time 6 http://127.0.0.1:8082/
# Response from Backend B - Port 8082
curl -fsS --max-time 6 http://127.0.0.1:8080/
# Response from Backend A - Slow (3 seconds)
```

**Unresolved, not a proven defect:** Initial localhost IP-hash requests went to B; after B failed and recovered, proxy requests continued reaching A even after a wait and reload. We did **not** establish the cause. Avoid attributing it to worker state, hash mapping, or failure timers without further evidence.

**Architecture checks:** Learner correctly explained that restart does not recover in-memory sessions and chose **B — Available but poorly balanced** for 100 NAT-shared clients mapped to one backend. Nginx itself remains a single point of failure.

## Environment Restoration — VERIFIED

**Objective:** Restore original static Backend A and default Nginx round-robin; do not alter Todo code or port-80 default site.

```bash
# Stop slow_backend.py with Ctrl+C; verify 8081 is free:
sudo ss -lntp | grep ':8081' || echo 'Slow Backend A stopped'
# Actual: Slow Backend A stopped

# Start original A in its own terminal:
python3 -m http.server 8081 --bind 127.0.0.1 --directory /tmp/project02/backend-a
# Verify from another terminal:
curl -fsS http://127.0.0.1:8081/
# Actual: Response from Backend A - Port 8081
```

Remove only `ip_hash;` from `/etc/nginx/sites-available/project02-loadbalancer`. The learner restarted Nginx; `systemctl status nginx` reported `active (running)` and successful startup configuration check.

```bash
sudo nginx -T 2>&1 | grep -A 5 'upstream project02_backends'
for i in $(seq 1 6); do curl -fsS http://127.0.0.1:8080/; done | sort | uniq -c
```

**Actual final output:**

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

```text
3 Response from Backend A - Port 8081
3 Response from Backend B - Port 8082
```

**Restoration conclusion:** Round-robin behavior verified. Temporary slow-backend script may remain in `/tmp/project02/`, but is no longer running.

## Final Progress Checkpoint

| Topic | Evidence | Status |
|---|---|---|
| Baseline | Both backends healthy | LAB COMPLETED |
| Weighted round-robin | A=10, B=30 | UNDERSTOOD |
| Least connections | A=3, B=37 with slow A | UNDERSTOOD |
| IP hash | 10/10 requests to B | UNDERSTOOD |
| Failure handling | B stopped; A returned HTTP 200 | APPLIED |
| Recovery investigation | B healthy; A still selected; root cause unknown | LAB COMPLETED |
| Restoration | Default round-robin 3/3 | VERIFIED |
| Architecture decision record (Part III §7) | Not yet submitted | NOT STARTED |
| Pull request | Not yet verified | NOT STARTED |

**Overall Lesson 03:** APPLIED for observed lab scenarios; **not ARCHITECT READY** until broader architecture justification, security/reliability evaluation, and production-level failure scenarios are demonstrated. Next: review this Markdown file on branch `feature/project02-load-balancing-algorithms`, then prepare PR to `master`.

---

## Git workflow (after review, not before)

Place this tutorial in the repo:

```bash
mkdir -p projects/02-nginx-load-balancing/tutorials
# Copy the downloaded Markdown file into that directory, keeping the filename above.
git status --short
git add projects/02-nginx-load-balancing/tutorials/lesson-03-load-balancing-algorithms.md
git commit -m "docs(project02): add load-balancing algorithms tutorial"
git push
```

As each checkpoint is reviewed, update **this same file**, commit, and push. At the end, prepare a PR to `master` with requirements, tested commands, actual evidence, failure scenarios, operational/security notes, and learning outcomes. **Do not merge until the final evidence review.**

## References

- Nginx HTTP load balancing: https://nginx.org/en/docs/http/load_balancing.html
- Nginx upstream module (`least_conn`, `ip_hash`, `weight`): https://nginx.org/en/docs/http/ngx_http_upstream_module.html
- Nginx proxy module: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
