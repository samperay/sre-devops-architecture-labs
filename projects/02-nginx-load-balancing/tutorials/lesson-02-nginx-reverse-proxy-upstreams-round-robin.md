# Project 02 — Lesson 02: Nginx Reverse Proxy, Upstream Groups, and Round-Robin

> **Track:** SRE & DevOps Architect Journey
> **Project:** 02 — Nginx Load Balancing & API Gateway
> **Lesson:** 02 — Reverse Proxy, Upstream Groups, and Round-Robin
> **Learning stages:** LEARN → INTEGRATE → OPERATE
> **Environment:** Ubuntu Server VM, Nginx 1.18.0, Python 3.10.12
> **Lab status:** Completed and demonstrated in the learning session.
> **Scope:** Single VM, one Nginx instance, two Python HTTP backends. No cloud resources.

## 1. Learning objectives

By the end of this lesson, you should be able to:

1. Explain what a reverse proxy does and how it differs from a backend application.
2. Define an Nginx `upstream` group and explain round-robin scheduling.
3. Explain why equal request counts do not imply equal computational work.
4. Configure a dedicated Nginx site without modifying the existing port-80 site.
5. Validate a configuration before applying it.
6. Verify the full client → proxy → backend request path.
7. Simulate a backend outage, investigate logs, and verify recovery.
8. Explain why backend redundancy does **not** prove end-to-end high availability.

## 2. Starting state and boundaries

This lesson assumes:

- Ubuntu VM with Nginx installed and running.
- Existing Nginx default site listening on **port 80**; preserve it.
- Two temporary Python HTTP servers to be created on loopback addresses.
- Ubuntu shell access with `sudo`.
- Ports `8080`, `8081`, and `8082` are available.

**Safety boundaries**

- Do not overwrite `/etc/nginx/sites-available/default`.
- Do not reload Nginx unless `sudo nginx -t` succeeds.
- Bind Python backends to `127.0.0.1`, not `0.0.0.0`.
- This is a learning setup, **not** a production-ready service.
- Use a separate terminal for each long-running Python backend.
- If you are repeating the lab, inspect existing files, processes, and ports before creating anything.

### Port allocation

| Component | Address | Purpose |
| --- | --- | --- |
| Existing Nginx site | `:80` | Existing configuration; leave unchanged |
| New Nginx load balancer | `0.0.0.0:8080` | Entry point for this lab |
| Backend A | `127.0.0.1:8081` | First Python HTTP server |
| Backend B | `127.0.0.1:8082` | Second Python HTTP server |

## 3. LEARN — Theory and architecture

### 3.1 Reverse proxy

A **reverse proxy** is a server that receives client requests and forwards them to one or more backend servers. The client communicates with the proxy rather than addressing each backend directly.

```text
Client
   |
   | HTTP request
   v
Nginx reverse proxy :8080
   |
   | Forward request
   v
Python backend :8081 or :8082
   |
   | HTTP response
   v
Nginx -> Client
```

A reverse proxy can provide routing, load balancing, TLS termination, request limits, and centralized access logging. Those capabilities must be configured; their existence is not implied merely by installing Nginx.

**Restaurant analogy:** Nginx is the receptionist, customers are clients, and kitchen stations are backend services. Customers place orders at the reception desk; the receptionist selects a kitchen and returns the prepared order.

**Todo mapping:** Nginx could sit in front of multiple instances of the Todo API. The user sends an API request to one stable endpoint, while Nginx selects an API instance. This is an **architectural illustration**, not a claim that the Todo application currently runs this topology.

### 3.2 Upstream groups

An Nginx `upstream` block defines a named pool of destinations:

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

The proxy can then reference the group by name:

```nginx
proxy_pass http://project02_backends;
```

This separates **where requests arrive** from **which servers handle them**. Adding a third backend generally changes the `upstream` block, not every `proxy_pass`.

### 3.3 Round-robin scheduling

Nginx uses **weighted round-robin** by default when no other upstream selection algorithm is specified. With two equally weighted available backends, successive independent requests will commonly alternate:

```text
Request 1 -> A
Request 2 -> B
Request 3 -> A
Request 4 -> B
```

This is **request selection**, not a guarantee that both machines receive equal CPU work, execution time, or memory pressure.

**Example:** Backend A processes a cheap read in 20 ms while Backend B handles a computationally expensive request in 2 seconds. One request each is equal *count*, not equal *work*.

**Correction to a common misconception:** Round-robin does **not** wait for a slow backend to finish before choosing it again. Nginx may assign additional requests to that backend while it remains busy.

**Least connections**, by contrast, prefers servers with fewer active connections, accounting for weights. It still does not directly measure CPU load or business-logic complexity.

### 3.4 Network binding and security boundary

- `127.0.0.1:8081` accepts connections only through the VM's loopback interface.
- `0.0.0.0:8081` accepts connections on all IPv4 interfaces.

Binding to `0.0.0.0` does **not** automatically make a service reachable from the internet; routing, firewalls, NAT, and network policy still matter. But loopback binding reduces unnecessary exposure for an internal backend on a single VM.

Our architecture deliberately exposes Nginx on `:8080` while keeping Python backends on loopback.

### 3.5 High availability, redundancy, and failover

- **Redundancy:** More than one backend exists.
- **Failover:** Requests can be served by another backend after a failure.
- **Availability:** Clients can successfully use the service.
- **High availability (HA):** A system design and operational capability intended to sustain availability despite defined failures.

Two backends behind **one** Nginx instance still leave Nginx as a **single point of failure (SPOF)**. Six successful requests after one backend stops demonstrate a specific failover behavior; they do not establish end-to-end HA or a production availability target.

### 3.6 HTTP failure signals

| Signal | Common interpretation | Important nuance |
| --- | --- | --- |
| `200` | Request succeeded | Does not prove every component is healthy |
| `502 Bad Gateway` | Gateway could not obtain a valid upstream response | Can follow a refused connection or an invalid response |
| `504 Gateway Timeout` | Gateway waited too long for an upstream response | Timeout behavior depends on configuration |
| `curl` connection failure | Cannot connect to the target listener | Check service, binding, routing, firewall, and NAT |

A slow backend does **not** automatically cause HTTP 502. High latency may instead lead to a timeout and HTTP 504.

---

## 4. INTEGRATE — Lab design and specification

### 4.1 Requirements

- **R1:** Preserve the existing Nginx site on port 80.
- **R2:** Serve a test entry point through Nginx on port 8080.
- **R3:** Use two independently identifiable backend responses.
- **R4:** Keep backend ports 8081 and 8082 bound to loopback.
- **R5:** Use a named upstream group and default round-robin.
- **R6:** Validate before applying Nginx configuration.
- **R7:** Verify routing, partial failure, logs, and recovery.
- **R8:** Avoid changing Todo application code.

### 4.2 Proposed configuration and request path

```text
                    Ubuntu VM
 Client
    |
    | HTTP :8080
    v
 +---------------------+
 | Nginx               |
 | project02_backends  |
 +----------+----------+
            |
       Round-robin
            |
      +-----+-----+
      |           |
      v           v
 Backend A     Backend B
 127.0.0.1     127.0.0.1
   :8081         :8082
```

**Spec-driven flow:** Requirements → Configuration specification → Safe change plan → Tasks → Implementation → Validation/testing → Version-control review/PR.

This lesson demonstrates the configuration and tests locally. It does **not** claim that the Nginx configuration was committed to the learning repository or reviewed in a PR.

### 4.3 Change plan

1. Create and verify two backend response files.
2. Start both backend servers on loopback.
3. Verify each backend directly.
4. Inspect destination Nginx file paths.
5. Create a dedicated site in `sites-available`.
6. Validate existing config, then enable the new site with a symlink.
7. Validate **again**, now including the enabled site.
8. Reload Nginx and verify the listener.
9. Test round-robin.
10. Simulate failure, inspect logs, restore service, and retest.

---

## 5. Guided hands-on exercises

> Commands below are for **reproducing** the completed lesson. Follow them in order on a lab VM. Keep Backend A and Backend B running in separate terminals.

### Exercise 1 — Inspect ports before starting

**Objective:** Avoid conflicting with existing processes.

```bash
sudo ss -lntp | grep -E ':80 |:8080 |:8081 |:8082 ' || true
```

**Expected:** Existing Nginx on `:80`; lab ports should be free before starting the exercise.

**Observe:** Which process owns each port? If a port is occupied, investigate instead of killing processes blindly.

### Exercise 2 — Create two independent backend directories

**Objective:** Ensure each backend has its own document root.

```bash
mkdir -p /tmp/project02/backend-a /tmp/project02/backend-b

printf 'Response from Backend A - Port 8081\n' > /tmp/project02/backend-a/index.html
printf 'Response from Backend B - Port 8082\n' > /tmp/project02/backend-b/index.html

cat /tmp/project02/backend-a/index.html
cat /tmp/project02/backend-b/index.html
```

**Expected:**

```text
Response from Backend A - Port 8081
Response from Backend B - Port 8082
```

**Observe:** Distinct contents let us identify which backend handled a request.

### Exercise 3 — Start Backend A

**Objective:** Start an HTTP server on loopback port 8081.

**Terminal A:**

```bash
python3 -m http.server 8081 --bind 127.0.0.1 --directory /tmp/project02/backend-a
```

**Expected:**

```text
Serving HTTP on 127.0.0.1 port 8081 (http://127.0.0.1:8081/) ...
```

Leave this terminal running.

**Observe:** The `--directory` argument matters. In the actual session, a server initially served an unintended working directory; the correction was to specify the document root explicitly.

### Exercise 4 — Start Backend B

**Objective:** Start a second independent server on loopback port 8082.

**Terminal B:**

```bash
python3 -m http.server 8082 --bind 127.0.0.1 --directory /tmp/project02/backend-b
```

**Expected:**

```text
Serving HTTP on 127.0.0.1 port 8082 (http://127.0.0.1:8082/) ...
```

**Troubleshooting note:** In the actual lab, an incorrectly split multiline shell command caused the server to bind to `0.0.0.0`. Restarting it with this **single-line command** corrected the binding.

### Exercise 5 — Verify each backend directly

**Objective:** Establish an application baseline before introducing the proxy.

**Terminal C:**

```bash
curl -s http://127.0.0.1:8081/
curl -s http://127.0.0.1:8082/
```

**Expected:**

```text
Response from Backend A - Port 8081
Response from Backend B - Port 8082
```

**Observe:** A `200` alone is not sufficient: verify the actual response body.

**Knowledge check:** If both backends work directly but Nginx fails, which layer should you investigate next?

### Exercise 6 — Inspect target Nginx paths

**Objective:** Avoid overwriting existing configuration.

```bash
sudo ls -l /etc/nginx/sites-available/project02-loadbalancer \
           /etc/nginx/sites-enabled/project02-loadbalancer
```

**Expected on a clean lab:** Both paths report `No such file or directory`.

**Observe:** If either exists, stop and inspect it rather than overwriting.

### Exercise 7 — Create the dedicated Nginx site

**Objective:** Define the upstream group and proxy listener without changing the existing site.

```bash
sudo nano /etc/nginx/sites-available/project02-loadbalancer
```

Insert:

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

Save and inspect:

```bash
sudo cat /etc/nginx/sites-available/project02-loadbalancer
```

**Expected:** The exact configuration above.

**Observe:** `upstream` defines the pool; `proxy_pass` refers to the pool name. `server_name _` is a conventional placeholder, not a universal catch-all by itself; the listener's default-server selection rules still apply.

### Exercise 8 — Validate current configuration

**Objective:** Verify the existing configuration is valid before including the new site.

```bash
sudo nginx -t
```

**Expected:**

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

**Observe:** At this stage, the new file in `sites-available` is not necessarily included. Passing here **does not yet validate the new site**.

### Exercise 9 — Enable the new site

**Objective:** Include the site without applying a runtime reload yet.

```bash
sudo ln -s /etc/nginx/sites-available/project02-loadbalancer \
           /etc/nginx/sites-enabled/project02-loadbalancer

ls -l /etc/nginx/sites-enabled/project02-loadbalancer
```

**Expected:** A symlink pointing to `/etc/nginx/sites-available/project02-loadbalancer`.

**Observe:** The symlink makes the file eligible for inclusion by Nginx's existing `sites-enabled` configuration.

### Exercise 10 — Validate the enabled site and reload

**Objective:** Safely apply the new configuration.

```bash
sudo nginx -t
```

**Proceed only if validation succeeds.** Then:

```bash
sudo systemctl reload nginx
sudo systemctl status nginx --no-pager
```

**Expected:** Syntax test successful; Nginx remains `active (running)`; journal/status indicates a successful reload.

**Observe:** A **reload** applies configuration while aiming to preserve ongoing service; a **restart** stops and starts the service. Neither operation proves that backend routing works.

### Exercise 11 — Verify Nginx is listening

**Objective:** Check the operating-system socket state.

```bash
sudo ss -lntp | grep ':8080'
```

**Expected:** `LISTEN ... 0.0.0.0:8080 ... nginx`.

**Observe:** The proxy is the network entry point; the Python servers remain on loopback.

### Exercise 12 — Verify round-robin

**Objective:** Observe both backends serving traffic through Nginx.

```bash
for i in {1..6}; do
    curl -s http://127.0.0.1:8080/
done
```

**Typical output:**

```text
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
```

**Observe:** Both backends appear. The exact starting order is not guaranteed.

**Actual session evidence:** Six requests alternated A/B, three per backend.

### Exercise 13 — Simulate partial backend failure

**Objective:** Observe how the proxy behaves when one backend is unavailable.

In **Terminal A**, press **Ctrl+C** to stop Backend A. Leave Backend B and Nginx running.

Then:

```bash
sudo ss -lntp | grep -E ':8080|:8081|:8082'
```

**Expected:** Nginx on `:8080`, Python on `127.0.0.1:8082`, **no** listener on `:8081`.

**Observe:** One backend is down; the gateway and the other backend remain up.

### Exercise 14 — Test client-visible behavior during failure

**Objective:** Measure request success through the proxy.

```bash
for i in {1..6}; do
    curl -s -o /dev/null -w "Request $i: HTTP %{http_code}\n" \
        http://127.0.0.1:8080/
done
```

**Observed in the actual session:** All six requests returned `HTTP 200`.

**Interpretation:** This demonstrates successful client requests under **this specific failure condition**. It does not guarantee success for every method, request body, timeout, or failure mode. Nginx upstream retry behavior depends on configuration and failure timing.

### Exercise 15 — Inspect Nginx error evidence

**Objective:** Find the failing hop rather than relying only on HTTP 200 responses.

```bash
sudo tail -n 20 /var/log/nginx/error.log
```

**Observed in the actual session (excerpt):**

```text
connect() failed (111: Unknown error) while connecting to upstream
upstream: "http://127.0.0.1:8081/"
```

**Interpretation:** Nginx attempted to connect to the stopped Backend A and encountered a connection error. Combined with successful client responses, this is consistent with successful failover/retry to the remaining backend.

**SRE lesson:** The service can be available but **degraded**. Client HTTP 200 responses do not mean every upstream is healthy.

### Exercise 16 — Restore Backend A

**Objective:** Recover the failed component without modifying Nginx.

**Terminal A:**

```bash
python3 -m http.server 8081 --bind 127.0.0.1 --directory /tmp/project02/backend-a
```

**Terminal C:**

```bash
curl -s http://127.0.0.1:8081/
```

**Expected:**

```text
Response from Backend A - Port 8081
```

**Observe:** The backend is independently healthy again. No Nginx reload is needed simply because a configured backend process restarted.

### Exercise 17 — Verify traffic recovery

**Objective:** Confirm Nginx resumes sending requests to both backends.

```bash
for i in {1..6}; do
    curl -s http://127.0.0.1:8080/
done
```

**Actual session evidence:**

```text
Response from Backend B - Port 8082
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
Response from Backend A - Port 8081
Response from Backend B - Port 8082
```

**Interpretation:** Both backends participated after recovery (A: 2; B: 4). The initial two B responses are **consistent with** passive failure handling, but six responses alone do not prove the precise cause or timing.

---

## 6. OPERATE — Troubleshooting runbook

### Symptom: `curl :8080` cannot connect

1. Check listener: `sudo ss -lntp | grep ':8080'`.
2. Check service: `sudo systemctl status nginx --no-pager`.
3. Validate configuration: `sudo nginx -t`.
4. If connecting from the Mac host, inspect VM routing, VirtualBox network mode, NAT/host-only settings, and firewall rules.

### Symptom: Nginx responds with 502

1. Test each backend directly with `curl`.
2. Check listeners on `:8081` and `:8082`.
3. Read `/var/log/nginx/error.log`.
4. Check `proxy_pass` upstream name and backend address/port.
5. Confirm backend document roots and responses.

### Symptom: Nginx returns unexpected content

1. Test each backend response body directly.
2. Confirm Python was started with the correct `--directory`.
3. Check URI forwarding behavior; `proxy_pass` with and without a URI component can behave differently.
4. Inspect effective Nginx configuration with `sudo nginx -T` if needed.

### Symptom: One backend is down, but requests still succeed

1. Treat the system as **degraded**, not fully healthy.
2. Confirm which backend failed.
3. Inspect upstream connection errors.
4. Consider remaining capacity, latency, and error rate.
5. Restore backend, verify direct response, then verify proxy traffic.
6. Investigate root cause separately from immediate service restoration.

### Symptom: Nginx config test fails

1. Do **not** reload.
2. Read the exact error and line number from `sudo nginx -t`.
3. Correct the issue.
4. Retest before reload.

---

## 7. Architectural trade-offs and production considerations

| Decision | Benefit | Limitation |
| --- | --- | --- |
| One Nginx instance | Simple and low-cost | Nginx is a SPOF |
| Two backend instances | Tolerates some backend failures | Capacity drops when one fails |
| Round-robin | Simple, predictable request selection | Does not account for processing cost |
| Least connections | Responds to active-connection imbalance | Not a direct CPU/latency metric |
| Loopback backend binding | Reduces direct network exposure | Only works for same-host proxy-to-backend communication |
| Passive upstream failure detection | Can avoid recently failing backends | Detection depends on actual traffic and settings |
| Nginx config reload | Applies validated config without a full restart | Still requires operational verification |

**Production topics not implemented in this lesson:** TLS, authentication, request limits, structured access logs, centralized metrics, active health checks, redundant proxies, autoscaling, deployment automation, persistent backend services, and capacity/load testing.

**Todo integration idea (future, approval required):** Run multiple Todo API instances and route requests through Nginx. Before implementing, specify session/authentication behavior, database concurrency, observability, failure handling, and deployment strategy. This lab does not modify the Todo application.

---

## 8. Knowledge checks and suggested answers

**Q1. Why use `upstream project02_backends` instead of proxying to one IP?**
To name and manage a pool of backends independently from the frontend listener, enabling request distribution and simpler membership changes.

**Q2. Where would you add a third backend on port 8083?**
Inside the `upstream` block: `server 127.0.0.1:8083;`. The `proxy_pass` name remains unchanged.

**Q3. Does equal request count prove equal CPU work?**
No. Request complexity, processing duration, concurrency, and hardware capacity may differ.

**Q4. Does round-robin wait for a slow backend to finish?**
No. It chooses by rotation/weight among eligible peers, not by request completion time.

**Q5. If a backend stops, will every client request always succeed?**
No. Retry eligibility, request method, timing, backend capacity, and gateway health affect outcomes.

**Q6. Why validate before reloading?**
To detect configuration problems before asking the running server to apply changes. A syntax check is necessary but insufficient for functional validation.

**Q7. Why can a site in `sites-available` be absent from `nginx -t`?**
Because Nginx generally includes enabled sites through `sites-enabled`; a file not included in the active configuration is not checked.

**Q8. Why did we not reload Nginx when Backend A restarted?**
Backend process availability changed, but the upstream configuration did not.

**Q9. Do six HTTP 200 responses prove HA?**
No. They demonstrate successful requests under a specific backend-failure experiment; Nginx itself remains a SPOF.

**Q10. Can a service be available but unhealthy?**
Yes. A failed backend may be masked by retries while reducing redundancy and capacity.

**Q11. Does `0.0.0.0` mean internet-accessible?**
Not necessarily. It means listening on all IPv4 interfaces; external reachability depends on networking and security controls.

**Q12. What must be verified before closing a production incident?**
Restored user-facing service, healthy routing, acceptable latency/errors/resource utilization, and sufficient stability. Root-cause analysis may continue after restoration.

---

## 9. Actual session evidence and progress

The following items were **observed in the guided session**, not inferred from a repository commit:

| Capability | Evidence | Assessment |
| --- | --- | --- |
| Backend A direct response | `Response from Backend A - Port 8081` | Verified |
| Backend B direct response | `Response from Backend B - Port 8082` | Verified |
| Loopback binding | Backend B startup reported `127.0.0.1:8082` | Verified |
| Nginx configuration | `project02_backends` contains both destinations | Verified |
| Safe activation | `nginx -t` passed; systemd reload succeeded | Verified |
| Listener | `ss` showed Nginx listening on `0.0.0.0:8080` | Verified |
| Round-robin | Initial six requests alternated A/B | Verified |
| Partial failure | Backend A listener absent; B and Nginx present | Verified |
| Failover behavior | Six requests returned HTTP 200 with A stopped | Verified for this scenario |
| Failure evidence | Nginx error log referenced connection failure to `:8081` | Verified |
| Recovery | Direct A response returned; both A and B later served traffic | Verified |
| End-to-end HA | No redundant Nginx or HA test | **Not demonstrated** |
| Repo commit / PR | Not evidenced in this session | **Not verified** |

**Lesson status: APPLIED.** The practical implementation, diagnosis, and recovery were demonstrated. **ARCHITECT READY is not yet awarded**; additional work is needed on performance, failure boundaries, security, observability, and trade-off justification.

### Progress checkpoint

- **Module/project:** 02 — Nginx Load Balancing & API Gateway
- **Lesson:** 02 — Reverse Proxy, Upstream Groups, Round-Robin
- **Current lab:** Completed
- **Completed exercises:** Backend setup, verification, site configuration, validation, reload, balancing, failure injection, log diagnosis, recovery
- **Knowledge-check strengths:** Upstream groups, network boundaries, fault isolation, reload vs. backend state
- **Topics to revisit:** Round-robin vs. least-connections, HA vs. failover, request count vs. workload, HTTP 502 vs. 504
- **Next recommended lesson:** 03 — Load-Balancing Algorithms (round-robin, least connections, weighted round-robin, IP hash)

---

## 10. Optional lab cleanup (only when you are finished)

**Do not run cleanup if you want to continue with Lesson 03 using the same environment.**

To stop the Python servers, press **Ctrl+C** in their respective terminals.

To remove **only** this lab's Nginx site, inspect the paths first and ensure they match the lab:

```bash
ls -l /etc/nginx/sites-enabled/project02-loadbalancer
sudo cat /etc/nginx/sites-available/project02-loadbalancer
```

If confirmed and you deliberately want to remove the lab configuration:

```bash
sudo rm /etc/nginx/sites-enabled/project02-loadbalancer
sudo nginx -t && sudo systemctl reload nginx
```

This removes the enabled symlink, not the source file. Retain the source for documentation or remove it separately only after confirming it is no longer needed. The `/tmp/project02` files are temporary and may be removed by normal system cleanup.

---

## 11. References for further study

- [HTTP load balancing](https://nginx.org/en/docs/http/load_balancing.html)
- [Reverse proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
- [HTTP upstream module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html) 
- [HTTP proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)

> **Repository placement suggestion:** `projects/02-nginx-load-balancing/tutorials/lesson-02-reverse-proxy-upstreams-round-robin.md`
> Adjust this path to your repository's actual directory conventions; this lesson was generated from the verified interactive session, not from an inspection of the current repository tree.
