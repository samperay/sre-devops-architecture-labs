# Project 02 — Lesson 03: Nginx Load-Balancing Algorithms

> **Track:** SRE & DevOps Architect Journey  
> **Branch:** `feature/project02-load-balancing-algorithms`  
> **Repository path:** `projects/02-nginx-load-balancing/tutorials/lesson-03-load-balancing-algorithms.md`  
> **Status:** IN PROGRESS — tutorial prepared; only environment baseline verified.  
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

**Verified at the start of this lesson:** `ss -lntp` showed both Python backends and Nginx listening on their expected ports. **Not yet verified for this lesson:** HTTP responses, current configuration, weighted distribution, least-connections, or IP hash. Previous Lesson 02 demonstrated round-robin, partial-backend failure, and recovery.

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

# Part IV — Evidence log (update after each checkpoint)

> Do **not** replace expected results with invented outputs. Record terminal evidence and feedback only after review.

| Checkpoint | Status | Actual evidence | Reviewer feedback |
|---|---|---|---|
| 01 — Port baseline | LAB COMPLETED | `ss` showed `127.0.0.1:8081`, `127.0.0.1:8082`, and `0.0.0.0:8080` listening | Socket state verified; HTTP health still to test |
| A — Config and HTTP baseline | PENDING | — | — |
| B — Weighted round-robin | PENDING | — | — |
| C — Least connections | PENDING | — | — |
| D — IP hash | PENDING | — | — |
| E — Restore baseline | PENDING | — | — |
| Architecture decision | PENDING | — | — |

## Progress checkpoint

- **Project:** 02 — Nginx Load Balancing & API Gateway
- **Lesson:** 03 — Load-Balancing Algorithms
- **Branch:** `feature/project02-load-balancing-algorithms`
- **Current checkpoint:** A — Configuration and HTTP baseline
- **Verified exercises:** Port-listener baseline only
- **Next activity:** Run Section A and share output before modifying Nginx
- **Overall lesson state:** IN PROGRESS

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
