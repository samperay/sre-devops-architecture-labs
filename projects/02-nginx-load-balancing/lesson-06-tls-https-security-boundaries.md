# Lesson 06 — TLS/HTTPS and Security Boundaries

> **Project:** 02 — Nginx and API Gateway  
> **Repository:** `samperay/sre-devops-architecture-labs`  
> **Date recorded:** 2026-11-05  
> **Learning method:** LEARN → INTEGRATE → OPERATE; BUILD → UNDERSTAND → BREAK → FIX → DESIGN  
> **Status:** HTTPS lab and monitoring exercises completed; production renewal/recovery not yet demonstrated.

## Scope and evidence

This is a **standalone Lesson 06 training page**, not the complete Project 02 journal. It consolidates the TLS concepts, lab commands, observed results, troubleshooting discussions, architecture questions and follow-up work from our guided sessions. Earlier lessons established the local gateway at `127.0.0.1:8085`, `/api/` → backend A `127.0.0.1:8081`, and `/users/` → backend B `127.0.0.1:8082`. Those services are lab fixtures, **not claims about the Todo application's current implementation**.

```text
Client --HTTPS/TLS--> Nginx :8443 --HTTP--> API Gateway :8085
                                                |-- /api/   --> Backend A :8081
                                                `-- /users/ --> Backend B :8082
```

**Learning objective:** Establish a working TLS boundary, verify identity and protocol negotiation, detect expiration and monitoring failures, and distinguish gateway health from application health. The lab uses localhost and a self-signed certificate, with no billable infrastructure.

## 1. LEARN — TLS/HTTPS and security boundaries

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

### INTEGRATE — Nginx HTTPS configuration (lab)

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

## 3. OPERATE — certificate expiration monitoring and failure injection

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

## 4. OPERATE — troubleshooting playbooks

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

## 5. Operational command reference

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

## 6. Architecture discussion — what we learned

### Certificate identity, trust and deployment are different checks

- A matching certificate/private-key public key proves the key pair corresponds; it does not establish client trust.
- A matching on-disk/live SHA-256 certificate fingerprint proves Nginx serves that same certificate; it does not prove that a client trusts it.
- Successful `curl --cacert` with hostname/IP validation proves that this lab client accepts the endpoint under the explicitly provided trust anchor.
- TLS 1.2 and TLS 1.3 are negotiated from the overlap of client and server capabilities; enabling TLS 1.3 does not require every client to support it.
- TLS negotiation failures occur before HTTP routing and must not be diagnosed as backend 502s.

### Health checks and status codes

- `GET /health` returning HTTP 200 only proves the gateway's own health endpoint responded; it does not prove both backends are healthy.
- If Backend A stops, `/api/` can return **502 Bad Gateway** while `/users/` and `/health` still return 200.
- **504 Gateway Timeout** is the usual gateway response for an upstream response timeout; 502 and 504 are not interchangeable.
- A direct request to a stopped Python backend commonly fails at the connection layer rather than returning HTTP 502. The lab backends bind to loopback, so direct testing must occur on the VM or another explicitly authorized network path.
- Certificate monitoring can report `OK` while a backend is down, or `UNKNOWN` while the live HTTPS endpoint remains available. Use both user-path probes and component diagnostics.

### Retry design and idempotency

- Do not blindly retry non-idempotent `POST /todos` operations. A backend may commit a task and lose its response; a retry could create a duplicate.
- The **client supplies an idempotency key before sending** the initial request, and the backend must enforce it atomically (for example, with a unique database constraint and stored result). A Todo ID returned only in a lost response cannot protect the retry.
- Retry only where request semantics, alternate healthy instances, timeouts, backoff/jitter and retry budgets justify it. The lab's `/api/` and `/users/` backends serve different routes and are not interchangeable failover targets.
- Two retries per original request can amplify 1,000 requests/s into 3,000 attempts/s in the worst case, increasing overload during an incident.

### Decisions and limitations

| Decision | Benefit | Limit / follow-up |
|---|---|---|
| TLS 1.2/1.3 only | Modern protocol baseline | Older clients cannot connect |
| Self-signed localhost certificate | Safe, inexpensive lab | Not trusted by default; production requires managed trust |
| TLS termination at Nginx | Clear boundary | Internal HTTP hop is not encrypted; assess production threat model |
| Loopback listener | Limits network exposure | External clients cannot connect directly |
| Seven-day CRITICAL before 30-day WARNING | Correct severity precedence | Missing/unreadable/malformed certs require separate error handling |
| Monitor disk certificate | Simple first check | Must also verify live endpoint and deployment mismatch |

### Security review questions

- Who owns and can read the private key? Is it backed up and rotated securely?
- Is the server identity validated by the client (SAN, trust, expiration)?
- Is HTTP between TLS terminator and gateway acceptable under the actual threat model?
- Are backend ports isolated from untrusted networks?
- Does `X-Forwarded-For` rely on trusted proxy boundaries, or can untrusted clients spoof it?
- Is Nginx itself redundant, and what happens if the VM fails?
- Are certificate expiry and renewal ownership documented?

---

## 7. Progress and outstanding operational work

| Topic | Evidence-based state |
|---|---|
| HTTPS listener and reverse proxy | APPLIED — Nginx validated and HTTPS paths returned 200 |
| TLS 1.2/1.3 and legacy rejection | UNDERSTOOD / LAB COMPLETED |
| Client certificate trust and SAN | APPLIED — verified with `curl --cacert` |
| Certificate and key relationship | LAB COMPLETED |
| Disk/live certificate fingerprint comparison | LAB COMPLETED |
| Expiry thresholds and severity ordering | LAB COMPLETED — Exercise 34 |
| Missing file and OpenSSL nonzero behavior | LAB COMPLETED — Exercise 35 |
| Bash `-f` missing-file detection | LAB COMPLETED — Exercise 36 |
| Monitoring vs application availability | UNDERSTOOD — architecture discussion |
| Renewal, rollback, live post-renewal verification | NOT YET DEMONSTRATED |
| Production-grade certificate monitor | NOT IMPLEMENTED |
| Overall lesson | APPLIED; not yet ARCHITECT READY |

**Recorded outcomes:** Nginx listener `127.0.0.1:8443`; `curl` default verification rejected the self-signed certificate (error 60); `curl --cacert` succeeded for `/health`, `/api/` and `/users/`; TLS 1.2 and 1.3 succeeded; TLS 1.0 and 1.1 were rejected; disk/live certificate fingerprints matched. The certificate expires **December 4, 2026 at 11:54:41 GMT**. Exercise 34 printed `WARNING: Certificate expires within 30 days`; Exercise 35 returned OpenSSL `Unable to load certificate`, exit 1; Exercise 36 printed `UNKNOWN: Certificate file does not exist: /home/ubuntu/tls-lab/nonexistent.crt`.

**Next recommended operational assessment:** Safely stage a replacement certificate/key, verify key match and SAN, validate `nginx -t`, gracefully reload, compare live and disk identities, test trusted HTTPS, and document rollback. This is **planned**, not recorded as completed. Do not overwrite current working key/certificate without backups and approval.

**Suggested PR:** `docs(project02): document lesson 06 TLS HTTPS security and operations`.
