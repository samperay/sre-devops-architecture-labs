# Project 02 — Nginx Load Balancing, API Gateway, Reliability, and TLS

> **Consolidated learning journal and lab runbook**  
> **Course:** SRE/DevOps Architect Journey — `sre-devops-architecture-labs`  
> **Updated:** 2026-11-05  
> **Learning model:** BUILD → UNDERSTAND → BREAK → FIX → DESIGN; LEARN → INTEGRATE → OPERATE  
> **Scope:** Lessons 01–06, configuration, exercises, troubleshooting, architecture decisions, interview questions, and remaining work.

## 0. Evidence, scope, and repository status

This is a **single, self-contained training document** reconstructed from our guided lab sessions and the terminal outputs shared during them. It records observed outcomes separately from illustrative examples and future recommendations. It does **not** imply that every command in this document was executed in the current session, nor that these configurations exist in the Todo application.

Repository: `https://github.com/samperay/sre-devops-architecture-labs` (default branch `master`). The repository's `ROADMAP.md` identifies Project 02 as **Nginx and API Gateway**, covering reverse proxy, multiple upstreams, balancing, path routing, timeouts, TLS termination, and gateway/application responsibilities. **Important repository discrepancy:** at the time of this document's preparation, `README.md` and `PROGRESS.md` still described only Project 01 and marked Project 02 `NOT STARTED`, despite separately recorded practical labs and reported merged PRs. The repository tracker should be reconciled using actual merged PR links before marking Project 02 complete in GitHub. This document is intended as the evidence and review artifact, not a substitute for verifying the branch.

**Lab evidence already discussed:** load balancing and failure exercises; API gateway PR #6 reported merged; TLS setup, protocol checks, fingerprints, expiry checks, Bash monitoring exercises 34–36; architecture Q&A. Earlier lab numbering beyond the explicitly documented exercises should not be interpreted as a verified complete inventory.

**No production claims:** localhost Python HTTP servers are test backends. The Todo app mappings are **design illustrations**, not verified Todo implementations.

---

## 1. Learning outcomes and architecture responsibilities

After studying this project, be able to:

1. Explain why an ingress/reverse proxy sits between clients and application processes.
2. Draw the request path and identify the TLS, HTTP, gateway, and backend boundaries.
3. Configure and test load balancing and path-based routing.
4. Distinguish upstream connection failure, timeout, TLS failure, and application error.
5. Assess retries against idempotency, capacity, and alternate-backend availability.
6. Generate, inspect, trust, and monitor a lab TLS certificate.
7. Distinguish **certificate on disk**, **certificate served by Nginx**, and **client trust**.
8. Investigate a partial outage without assuming `/health` proves end-to-end health.
9. Document security and reliability trade-offs, monitoring gaps, and safe recovery.

### Restaurant analogy

- **Customer** = client/browser/API consumer.
- **Front desk / host** = Nginx reverse proxy; one public entry point.
- **Seating coordinator** = load balancer selecting among equivalent service instances.
- **Different service counters** = API gateway routing `/api/` and `/users/` to different services.
- **Restaurant ID and secure entry check** = TLS server certificate and handshake.
- **Kitchen** = application backend.
- **Front-desk open sign** = gateway `/health`; does **not** guarantee kitchen availability.
- **Order number supplied before cooking** = idempotency key that allows safe recognition of repeated orders.

**Todo mapping:** client requests could enter through Nginx, then route to Todo API services; these are architecture patterns to evaluate, not claims about current Todo code.

---

## 2. Actual lab topology and request flows

```text
                     Lab client (same Ubuntu VM)
                               |
                +--------------+-----------------+
                |                                |
         HTTP :8080                       HTTPS 127.0.0.1:8443
                |                                |
      Nginx load balancer                  Nginx TLS terminator
                |                                |
      upstream project02_backends           HTTP 127.0.0.1:8085
         /             \                          |
    :8081 A           :8082 B              Nginx API gateway
                                            |      |       |
                                          /health /api/  /users/
                                            200     |       |
                                                   :8081   :8082
                                                Backend A Backend B
```

**Critical architectural distinction:** the `:8080` load-balancer experiment and the `:8443 → :8085` gateway experiment are separate request paths. Backend A and B are **equivalent targets** for the load-balancer experiment, but **different route destinations** in the gateway experiment. Do not assume `/api/` can fail over to the `/users/` service.

**Loopback binding:** the HTTPS listener and gateway bind `127.0.0.1`, so they are intentionally accessible only locally. Remote testing requires a deliberately authorized network path (for example, SSH port forwarding), not opening backend ports to the internet.

### Environment baseline

| Component | Recorded lab value |
|---|---|
| Host | Ubuntu Server VM, user `ubuntu` |
| Nginx | 1.18.0 (Ubuntu package) |
| OpenSSL | 3.0.2 |
| Backend A | Python HTTP test server at `127.0.0.1:8081` |
| Backend B | Python HTTP test server at `127.0.0.1:8082` |
| Load balancer | Nginx on port `8080` |
| API gateway | Nginx on `127.0.0.1:8085` |
| TLS termination | Nginx on `127.0.0.1:8443` |
| Certificate files | `/home/ubuntu/tls-lab/server.crt`, `server.key` |

---

## 3. Lesson 01 — Reverse proxy and load-balancing fundamentals

### LEARN

A **reverse proxy** receives client requests on behalf of backend services. The client sees the proxy as the endpoint; the proxy selects or forwards to upstreams. A **load balancer** distributes requests among equivalent backend instances. Benefits include one entry point, central access controls, simpler routing, and easier backend replacement. Costs include proxy operational responsibility and a potential shared failure domain if not made redundant.

**Round robin** cycles through eligible upstreams; it does not inherently measure application readiness, CPU utilization, or actual request cost. Two backends on one VM demonstrate routing but do **not** create host-level high availability.

### INTEGRATE (lab configuration pattern)

An illustrative Nginx configuration consistent with the verified topology (compare with your actual committed config before copying):

```nginx
upstream project02_backends {
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}

server {
    listen 8080;
    location / {
        proxy_pass http://project02_backends;
    }
}
```

**Safe test backends:** use separate terminal sessions, create distinct content under temporary directories, then start:

```bash
python3 -m http.server 8081 --bind 127.0.0.1 --directory /tmp/project02-backend-a
python3 -m http.server 8082 --bind 127.0.0.1 --directory /tmp/project02-backend-b
```

The paths above are **illustrative**; create directories and content before using them. The original sessions verified that each backend returned identifying content for its own port.

### OPERATE — evidence and observations

```bash
curl -i http://127.0.0.1:8081/
curl -i http://127.0.0.1:8082/
for i in 1 2 3 4 5 6; do curl -s http://127.0.0.1:8080/; done
sudo nginx -t
sudo ss -lntp | grep -E ':8080|:8081|:8082'
```

**Observed:** round-robin routing across Backend A and Backend B was verified. Stopping a backend produced a gateway failure scenario (HTTP 502 observed during exercises). The precise sequence and all previous command outputs should be sourced from the relevant PR if a forensic record is required.

**Discussion:** a 502 indicates a gateway/upstream communication problem, not necessarily a complete host outage. A 200 from one backend does not establish redundancy if both backends share the same host.

---

## 4. Lessons 02–04 — Routing, algorithms, reliability, timeouts, and retries

### Load-balancing choices

| Choice | Useful when | Trade-off |
|---|---|---|
| Round robin | Similar-capacity, similar-cost requests | Ignores variable request duration and load |
| Least connections | Long-lived/uneven connections | Connection count is an imperfect load signal |
| IP hash / affinity | Session affinity is required | Uneven distribution and dependence on instance identity |
| Weighted distribution | Backends have unequal capacity | Requires capacity estimates and ongoing tuning |

**Design question:** is session state local to a backend? If so, sticky routing may hide an architecture limitation; externalizing session state may be preferable depending on the application.

### Reliability and timeout vocabulary

- **Connection timeout:** time allowed to establish an upstream connection.
- **Read timeout:** maximum idle time between successive upstream reads; not necessarily total request duration.
- **Send timeout:** maximum idle time between successive writes to upstream.
- **502 Bad Gateway:** upstream response invalid or upstream connection unsuccessful (common for refused connection).
- **504 Gateway Timeout:** upstream did not respond within a relevant timeout.
- **503 Service Unavailable:** service currently cannot handle request; may arise from capacity, maintenance, or explicit application behavior.
- **Client connection refused:** TCP connection was not established; a direct backend call to a stopped process commonly gives a curl connection error rather than HTTP 502.

**Representative commands** (inspection only):

```bash
sudo nginx -t
sudo nginx -T | less
sudo ss -lntp | grep -E ':8080|:8085|:8443|:8081|:8082'
curl -i --max-time 5 http://127.0.0.1:8080/
sudo journalctl -u nginx --since '15 minutes ago' --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

`nginx -T` can include sensitive configuration values; do not paste secrets into PRs. Log paths may vary.

### Failure analysis workflow

1. Define impact: which endpoint, status, time window, and proportion of users?
2. Test the public/ingress endpoint and capture status, latency, and TLS result.
3. Test the gateway route separately, from an authorized location.
4. Test the corresponding backend directly on its reachable interface.
5. Check process/listener state, Nginx errors, and upstream logs.
6. Compare against recent configuration changes and backend restarts.
7. Restore service, then document cause, evidence, and prevention.

### Retry discussion — important corrections from the lesson

**User's initial reasoning:** retries may help, but backends must have capacity for bursts. **Architectural refinement:** capacity is necessary but not sufficient. Before retrying, verify that the operation is safe, an equivalent healthy upstream exists, and the retry policy does not amplify load.

Example: 1,000 incoming requests/s with up to two retries can become **3,000 attempts/s** during a failure. Use bounded attempts, backoff/jitter, retry budgets, and end-to-end deadlines. An upstream 502 does **not** automatically justify replaying a non-idempotent write.

**Todo example:**

```http
POST /todos
Idempotency-Key: 8d7f2a91-1234-4567-8901-abcdef123456
Content-Type: application/json

{"title":"Learn Kubernetes"}
```

The client should generate the idempotency key **before** the request, not learn it only from a response that may be lost. The backend must enforce the key atomically (for example, with a database uniqueness constraint and a stored result or operation record), validate request-key reuse, and define retention. This is a **design recommendation**, not a verified Todo feature. For a retry after a successful write but lost response, the same key should return the recorded outcome rather than create another Todo.

**Nginx-specific caution:** automatic retries for non-idempotent methods require deliberate configuration and are generally restricted; inspect `proxy_next_upstream` behavior and method semantics rather than assuming every 502 is retried. Never route `/api/` to `/users/` unless they truly implement the same contract.

---

## 5. Lesson 05 — API gateway routing

### LEARN

An **API gateway** provides a controlled entry point and routes requests to the right backend based on path or host. A reverse proxy is the underlying mechanism; a gateway adds application-oriented routing and policy responsibilities. Avoid placing business logic in Nginx merely because the gateway can intercept requests.

### Recorded gateway configuration

File: `/etc/nginx/sites-available/project02-api-gateway`.

```nginx
server {
    listen 127.0.0.1:8085;

    location /api/ {
        proxy_pass http://127.0.0.1:8081/;
    }

    location /users/ {
        proxy_pass http://127.0.0.1:8082/;
    }

    location = /health {
        default_type text/plain;
        return 200 'API Gateway is healthy';
    }
}
```

**Path rewriting:** with `location /api/` and `proxy_pass http://127.0.0.1:8081/;` (trailing slash), Nginx replaces the matching location prefix with `/`. Thus `/api/foo` becomes `/foo` upstream. Removing the trailing slash changes URI behavior; verify the expected application contract.

### Commands and observed results

```bash
sudo nginx -t
sudo systemctl reload nginx
curl -i http://127.0.0.1:8085/health
curl -i http://127.0.0.1:8085/api/
curl -i http://127.0.0.1:8085/users/
```

**Verified:** `/health` returned HTTP 200; `/api/` reached Backend A; `/users/` reached Backend B. Stopping Backend A produced **502 for `/api/`**, while `/health` remained successful; restarting A restored `/api/` to HTTP 200. Lesson 05 PR #6 was reported merged.

### Discussion: health checks are scoped

`/health` is a **gateway-process check**, not an end-to-end application check. It can return 200 when an essential backend is down. Prefer separate signals:

- **TLS/ingress:** handshake succeeds with valid trust and hostname, then HTTPS request succeeds.
- **Gateway:** gateway route is reachable and policy is functioning.
- **Backend A:** `/api/` functionality and direct authorized backend check.
- **Backend B:** `/users/` functionality and direct authorized backend check.
- **User journey:** representative end-to-end request, with safe synthetic data where needed.

A 200 from `/health` plus a 502 from `/api/` means partial service impairment, not “fully healthy.”

---

## 6. Lesson 06 — TLS/HTTPS and security boundaries

### LEARN — certificate and handshake concepts

- **TLS:** cryptographic protocol that authenticates the server and protects data in transit.
- **Private key:** secret held by the server; never commit or share it.
- **Certificate:** binds an identity (such as a DNS name) to a public key and is signed by an issuer.
- **Self-signed certificate:** certificate signed by its own key; suitable for a controlled lab but not trusted by ordinary clients unless explicitly trusted.
- **SAN (Subject Alternative Name):** identity names/IPs checked by clients; modern hostname verification relies on SAN.
- **Trust anchor:** certificate authority or explicitly trusted certificate used to validate the presented certificate.
- **TLS termination:** Nginx decrypts client HTTPS and forwards HTTP to the internal gateway in this lab.
- **Security boundary:** external encrypted leg ends at Nginx; the loopback HTTP leg is not encrypted. In production, decide whether backend encryption/mTLS is needed based on network and threat model.

**Restaurant analogy:** the host checks the restaurant's identity document at the entrance, but once inside, a message passed from reception to the kitchen is a separate internal communication path. Secure entry does not automatically secure every internal hop.

### Lab certificate creation and permissions

The original lab used a 3072-bit RSA key and a 30-day self-signed certificate with `CN=localhost`, SAN `DNS:localhost` and `IP:127.0.0.1`.

**Reproducible example — generates a new lab certificate, so do not run over existing assets without a backup:**

```bash
mkdir -p "$HOME/tls-lab"
chmod 700 "$HOME/tls-lab"

openssl req -x509 -newkey rsa:3072 -sha256 -nodes \
  -keyout "$HOME/tls-lab/server.key" \
  -out "$HOME/tls-lab/server.crt" \
  -days 30 \
  -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'

chmod 600 "$HOME/tls-lab/server.key"
chmod 644 "$HOME/tls-lab/server.crt"
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -subject -issuer -dates -ext subjectAltName
```

**Recorded actual assets:** `~/tls-lab` mode `700`, `server.key` mode `600`, `server.crt` mode `644`; certificate notBefore **Nov 4, 2026 11:54:41 GMT**, notAfter **Dec 4, 2026 11:54:41 GMT**. Keep the private key out of Git. Permissions and service-worker access must be tested; the working lab verified Nginx could load the assets.

### Nginx HTTPS configuration — recorded

File: `/etc/nginx/sites-available/project02-https`.

```nginx
server {
    listen 127.0.0.1:8443 ssl;
    server_name localhost;

    ssl_certificate     /home/ubuntu/tls-lab/server.crt;
    ssl_certificate_key /home/ubuntu/tls-lab/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Recorded validation:**

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo ss -lntp '( sport = :8443 )'
```

`nginx -t` succeeded; Nginx was listening at `127.0.0.1:8443`. Prefer **graceful reload** after validation rather than restarting and interrupting active requests. Note that replacing files on disk alone does not guarantee workers are serving the replacement certificate.

### Certificate trust and HTTPS routing tests

```bash
# Expected failure: certificate is self-signed and not in default trust store
curl -v https://127.0.0.1:8443/health

# Expected success: explicitly trust this lab certificate
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/health
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/api/
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/users/
```

**Observed:** default curl failed with `curl: (60) SSL certificate problem: self-signed certificate`. With `--cacert`, `/health` returned `API Gateway is healthy`, `/api/` returned HTTP 200 with `Response from Backend A - Port 8081`, and `/users/` returned HTTP 200 with `Response from Backend B - Port 8082`.

**Security discussion:** `curl -k` would bypass certificate verification; it may be useful to isolate a TLS trust problem in a disposable lab but is **not** evidence of trusted HTTPS and should not be a production fix.

### TLS protocol compatibility and negotiation

```bash
openssl s_client -connect 127.0.0.1:8443 -servername localhost \
  -CAfile "$HOME/tls-lab/server.crt" -tls1_3 </dev/null

openssl s_client -connect 127.0.0.1:8443 -servername localhost \
  -CAfile "$HOME/tls-lab/server.crt" -tls1_2 </dev/null
```

**Observed:** TLS 1.3 negotiated `TLS_AES_256_GCM_SHA384`, verification OK; TLS 1.2 negotiated `ECDHE-RSA-AES256-GCM-SHA384`, verification OK. A client supporting only TLS 1.2 can still connect when the server permits TLS 1.2 and 1.3: they negotiate a mutually supported version.

```bash
# Diagnostic only: relax client-side security policy so the handshake reaches server
openssl s_client -connect 127.0.0.1:8443 -servername localhost \
  -tls1 -cipher 'DEFAULT:@SECLEVEL=0' </dev/null

openssl s_client -connect 127.0.0.1:8443 -servername localhost \
  -tls1_1 -cipher 'DEFAULT:@SECLEVEL=0' </dev/null
```

**Observed:** TLS 1.0 and TLS 1.1 were rejected by Nginx with a `protocol version` alert. The initial TLS 1.0 attempt without relaxing the **client-side** OpenSSL policy failed locally with `no protocols available`, which alone does **not** prove server rejection. Also, `Verify return code: 0 (ok)` when no peer certificate was received does not prove trust.

**Architectural insight:** a TLS protocol mismatch fails **before HTTP routing**; a 502 after a successful TLS handshake is a different failure domain.

### Disk certificate, live certificate, and key relationship

```bash
# On-disk identity and validity
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -subject -issuer -dates
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -fingerprint -sha256

# What Nginx actually serves
echo | openssl s_client -connect 127.0.0.1:8443 -servername localhost 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

echo | openssl s_client -connect 127.0.0.1:8443 -servername localhost 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256

# Compare public keys derived from cert and private key
openssl x509 -in "$HOME/tls-lab/server.crt" -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in "$HOME/tls-lab/server.key" -pubout -outform DER \
  | openssl dgst -sha256
```

**Observed:** key-derived and certificate-derived public-key hashes matched. Live and on-disk certificate SHA-256 fingerprints matched:

```text
54:86:50:FD:07:21:76:05:04:04:6B:FA:32:90:A7:5A:08:86:32:E1:FF:1D:6E:4A:86:0B:C9:43:73:3C:A8:E7
```

**Three different questions:**

1. **Does the private key correspond to the certificate?** Compare public keys.
2. **Is Nginx serving the expected certificate?** Compare live/disk certificate fingerprints.
3. **Will a client trust it?** Validate chain/trust anchor, hostname/SAN, validity, and appropriate certificate usage.

A matching fingerprint is not proof of client trust. After a certificate is replaced on disk, the old certificate may remain served until Nginx is reloaded; verify the **live** certificate after reload.

---

## 7. Certificate expiration monitoring — exercises and findings

### Time-window tests

```bash
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -enddate
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -checkend 2592000
echo "Exit status: $?"
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -checkend 604800
echo "Exit status: $?"
```

`2592000` = 30 days in seconds; `604800` = 7 days. **Observed:** the 30-day check returned `Certificate will expire`, exit `1`; the seven-day check returned `Certificate will not expire`, exit `0`. Exit codes are interpreted for the specific command just run; run `echo $?` immediately afterward.

### Exercise 34 — classify expiration severity

```bash
CERT="$HOME/tls-lab/server.crt"
if ! openssl x509 -in "$CERT" -noout -checkend 604800 >/dev/null; then
    echo "CRITICAL: Certificate expires within 7 days"
elif ! openssl x509 -in "$CERT" -noout -checkend 2592000 >/dev/null; then
    echo "WARNING: Certificate expires within 30 days"
else
    echo "OK: Certificate valid for more than 30 days"
fi
```

**Actual user output:** `WARNING: Certificate expires within 30 days`.

**Knowledge check:** if 30-day threshold is tested before seven-day threshold, a certificate with five days remaining would be classified WARNING rather than CRITICAL. Bash executes the first matching branch and skips later `elif`s. **Lesson:** check most severe applicable conditions first.

### Exercise 35 — missing-file failure injection

```bash
openssl x509 -in "$HOME/tls-lab/nonexistent.crt" -noout -checkend 604800
echo "Exit status: $?"
```

**Actual output (abbreviated):**

```text
Could not open file or uri for loading certificate from /home/ubuntu/tls-lab/nonexistent.crt
No such file or directory
Unable to load certificate
Exit status: 1
```

**Finding:** exit `1` also occurs when the certificate cannot be loaded. A naive `if ! openssl ... -checkend` script can falsely report *certificate expires* when the real issue is *monitoring cannot read the certificate*. Do not conflate monitoring failure with expiration.

### Exercise 36 — missing-file detection

```bash
CERT="$HOME/tls-lab/nonexistent.crt"
if [[ ! -f "$CERT" ]]; then
    echo "UNKNOWN: Certificate file does not exist: $CERT"
else
    echo "Certificate file exists"
fi
```

**Actual user output:**

```text
UNKNOWN: Certificate file does not exist: /home/ubuntu/tls-lab/nonexistent.crt
```

**Finding:** Bash `-f` checks whether the path refers to an existing regular file. It does **not** establish readability, parseability, or certificate validity. A production monitor must also handle unreadable/malformed files and OpenSSL errors, and may need to check the **live endpoint** rather than only a disk path.

### Monitoring design: status semantics

| Status | Intended meaning | Suggested response |
|---|---|---|
| OK | Verified valid beyond warning threshold | Continue normal checks |
| WARNING | Approaching renewal window | Plan renewal and verify deployment procedure |
| CRITICAL | Expired or within urgent threshold | Urgent remediation, assess user impact |
| UNKNOWN | Cannot determine certificate status | Investigate monitor permissions, path, format, tooling |

**Important:** UNKNOWN may still merit paging depending on service criticality. Monitoring status and incident priority are separate policies.

**Potential production enhancement, not yet implemented:** validate file existence, readability, parseability, and certificate identity; distinguish command execution failure from expiration; inspect the live served certificate; alert on mismatch between disk and live; verify a trusted end-to-end HTTPS request; emit stable exit codes and actionable diagnostics. Avoid pretending that a file check alone makes the monitor production ready.

---

## 8. Operational troubleshooting playbooks

### Scenario A — client rejects self-signed certificate

**Symptoms:** curl exits 60, HTTPS fails before HTTP response. **Check:** `openssl s_client` certificate details, SAN, trust chain, client CA store, and clock. **Lab fix:** use `curl --cacert ~/tls-lab/server.crt` with the expected hostname/IP. **Do not:** permanently disable verification.

### Scenario B — TLS 1.0/1.1 client cannot connect

**Symptoms:** handshake alert before HTTP. **Check:** supported protocol overlap, OpenSSL client security policy, Nginx `ssl_protocols`, logs. **Decision:** do not re-enable obsolete TLS versions casually; upgrade client or provide a reviewed compatibility solution.

### Scenario C — gateway `/health` is 200 but `/api/` is 502

**Symptoms:** HTTPS certificate valid, gateway alive, Backend A route failing. **Check:** `curl -i --cacert ... https://127.0.0.1:8443/api/`, direct authorized `curl http://127.0.0.1:8081/`, `ss`, Nginx error log, backend process. **Lesson:** ingress health is not backend health. Backend B and `/users/` may still work.

### Scenario D — 504 on a slow upstream

**Symptoms:** TLS handshake succeeds, but gateway times out awaiting upstream. **Check:** upstream request latency, queueing, saturation, read timeout, connection pool, and application logs. **Decision:** increasing a timeout without addressing overload may worsen resource exhaustion.

### Scenario E — renewed file but old certificate still served

**Symptoms:** disk expiry is new, live expiry remains old. **Check:** compare live/disk SHA-256 fingerprints, correct Nginx file paths, `nginx -t`, reload status, and active workers. **Safe procedure:** stage new cert/key, validate matching keys and permissions, back up old assets, `nginx -t`, gracefully reload, validate live fingerprint and trusted HTTPS. **Not yet performed end-to-end in this lab.**

### Scenario F — monitor says UNKNOWN while HTTPS works

**Symptoms:** monitoring path missing, but users can still connect. **Check:** live HTTPS from the client perspective, live certificate, monitor configured path, file permissions, disk certificate. **Lesson:** a broken observer is not conclusive evidence that the observed service is down.

### Scenario G — repeated write after lost response

**Symptoms:** `POST /todos` succeeded in backend but response lost; retry risks duplicate records. **Decision:** no blind retry; use an end-to-end idempotency design with client-generated key and atomic server-side enforcement. Monitor retry rates, duplicates, and conflicts.

---

## 9. Safe operational command reference

```bash
# Syntax, process, listeners
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo ss -lntp | grep -E ':8080|:8081|:8082|:8085|:8443'

# HTTP routing
curl -i http://127.0.0.1:8085/health
curl -i http://127.0.0.1:8085/api/
curl -i http://127.0.0.1:8085/users/

# Verified HTTPS paths
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/health
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/api/
curl -i --cacert "$HOME/tls-lab/server.crt" https://127.0.0.1:8443/users/

# Disk cert inspection
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in "$HOME/tls-lab/server.crt" -noout -fingerprint -sha256

# Live cert inspection
echo | openssl s_client -connect 127.0.0.1:8443 -servername localhost 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -fingerprint -sha256

# Logs (may require sudo and paths may vary)
sudo journalctl -u nginx --since '15 minutes ago' --no-pager
sudo tail -n 100 /var/log/nginx/error.log
```

**Safe change protocol:** preserve original config, edit only the intended lab file, test with `sudo nginx -t`, reload gracefully only after successful test, verify live routes, and roll back if behavior differs. Do not commit private keys, secrets, or unredacted sensitive logs.

---

## 10. Architecture decisions and trade-offs (review draft)

| Decision | Reason | Trade-off / open risk |
|---|---|---|
| Nginx as single entry point | Central routing and consistent access path | Proxy availability and configuration become critical |
| Round robin for equivalent test backends | Simple to observe and explain | No awareness of per-request cost or actual health |
| Distinct `/api/` and `/users/` routes | Clear service routing | Cannot fail over between different contracts |
| TLS 1.2 and 1.3 only | Avoid obsolete protocol versions | Legacy clients must be upgraded |
| Self-signed localhost cert | No external CA or cost for safe lab | Not trusted by default; not suitable for general public production clients |
| TLS termination at Nginx | Clear security and routing boundary | Internal HTTP leg is unencrypted; review production threat model |
| Loopback binding for lab | Limits exposure | Not remotely reachable without deliberate secure access |
| Separate gateway and backend health | Detect partial outages | More monitoring signals and alert design work |
| 7-day critical / 30-day warning | Prioritize renewal lead time | Need reliable parsing, live check, alert ownership |
| Restrict automatic write retries | Prevent duplicate side effects | Some transient failures may require user/client recovery |

### Security review questions

- Who owns and can read the private key? Is it backed up and rotated securely?
- Is the server identity validated by the client (SAN, trust, expiration)?
- Is HTTP between TLS terminator and gateway acceptable under the actual threat model?
- Are backend ports isolated from untrusted networks?
- Does `X-Forwarded-For` rely on trusted proxy boundaries, or can untrusted clients spoof it?
- Is Nginx itself redundant, and what happens if the VM fails?
- Are certificate expiry and renewal ownership documented?

---

## 11. Interview and self-assessment questions

1. Draw the request path from client through TLS termination to Backend A. Where is traffic encrypted?
2. Why does a 200 from `/health` not prove that `/api/` is healthy?
3. How do you distinguish 502 from 504, and how does a direct TCP connection failure differ?
4. When is round robin insufficient, and what alternatives would you evaluate?
5. Why can a certificate fingerprint match without the client trusting the server?
6. Why must you compare **live** and **on-disk** certificates after renewal?
7. How do you prove TLS 1.0 is rejected by the server rather than merely disabled by your client?
8. Why is a missing certificate file not the same as an expiring certificate?
9. Would you retry a POST automatically? How does an idempotency key prevent duplicates under concurrency?
10. How would you detect retry amplification, backend overload, and partial availability?
11. What are the security consequences of TLS termination followed by internal HTTP?
12. What changes would you make before running this design in production across multiple hosts/zones?

**Expected architect-level response:** state assumptions, user impact, evidence, alternative designs, security boundary, failure modes, monitoring, operational cost, and decision rationale—not just the command to run.

---

## 12. Progress checkpoint and remaining work

| Area | Evidence | Learning state |
|---|---|---|
| Load balancing | Two backend responses, round-robin and failure behavior discussed | APPLIED (lab evidence recorded) |
| API gateway | `/health`, `/api/`, `/users/` verified; Backend A failure isolated | APPLIED |
| TLS termination | Nginx HTTPS endpoint configured and tested | APPLIED |
| TLS negotiation | TLS 1.2/1.3 accepted, 1.0/1.1 rejected | UNDERSTOOD / LAB COMPLETED |
| Trust and fingerprints | CA-file curl, key/cert match, live/disk fingerprint | APPLIED |
| Expiration checks | 30-day/7-day, severity ordering | LAB COMPLETED |
| Missing-file monitoring | Exercises 35 and 36 output verified | LAB COMPLETED |
| Retry/idempotency design | Q&A, corrected response-generated-ID misconception | UNDERSTOOD after feedback |
| Actual certificate replacement and recovery | Not performed end to end | NOT STARTED |
| Production HA / scale / observability | Design discussion only | NOT STARTED |
| Project 02 PR/merge verification | Earlier PRs reported; GitHub tracker currently stale | RECONCILIATION REQUIRED |

**Do not label this project `ARCHITECT READY` yet.** That requires demonstrated renewal/recovery, production-grade monitoring decisions, clear trade-off communication, and evidence-backed PR review. The hands-on **Lesson 06** portion has been closed; the broader production readiness assessment remains open.

### Recommended next steps

1. Commit this single Markdown document on a new feature branch and open a PR to `master`.
2. In the PR, link existing merged Project 02 PRs and confirm actual Nginx config paths against the repository.
3. Reconcile `PROGRESS.md` and any stale `README.md` statements **in a separate explicitly reviewed change** (or expand this PR only after verifying merge evidence).
4. Optionally complete one controlled certificate rotation/reload/recovery exercise before architect-readiness sign-off.
5. For the next learning phase, consider a brief Docker skills assessment and a Kubernetes-focused project; this would be a deliberate **reordering** of the current `ROADMAP.md`, where Redis and RabbitMQ appear before Kubernetes. Record the decision in the roadmap rather than silently changing scope.

### Suggested PR details

- **Branch:** `docs/project02-nginx-complete-learning-notes`
- **File:** `projects/02-nginx-api-gateway/project02-nginx-api-gateway-complete-learning-notes.md` (proposed path; verify against existing repository layout)
- **PR title:** `docs(project02): consolidate Nginx, API gateway, reliability and TLS labs`
- **PR description:** One evidence-based document covering architecture, commands, lab outcomes, failure investigations, TLS security, monitoring, retries, idempotency, trade-offs, and remaining readiness gaps. No application code or Nginx configuration changed.

---

## 13. References

- Lab repository: `https://github.com/samperay/sre-devops-architecture-labs`
- Project roadmap: `ROADMAP.md`
- Project progress tracker: `PROGRESS.md`
- Nginx reference manual: `https://nginx.org/en/docs/`
- Nginx proxy module: `https://nginx.org/en/docs/http/ngx_http_proxy_module.html`
- OpenSSL `x509` manual: `https://docs.openssl.org/3.0/man1/openssl-x509/`
- OpenSSL `s_client` manual: `https://docs.openssl.org/3.0/man1/openssl-s_client/`

**Document intent:** preserve what was actually learned, what was observed, where understanding was corrected, and what remains unproven. This is a lab runbook and architecture learning record, not a production deployment guide.
