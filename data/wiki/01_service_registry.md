# Service Registry & Dependency Graph

**Status:** Live | **Maintainer:** SRE / Platform Engineering
**Source:** Incident Metrics Database

This document maps the active microservices in our ecosystem to their critical dependencies and known failure modes, as observed in production incidents.

## 1. Edge & Traffic Ingress

### **edge-proxy**
* **Role:** Primary ingress gateway for all user traffic.
* **Critical Dependencies:** * **PostgreSQL:** Stores session state. Note that under retry storms, Postgres frequently exhibits head-of-line blocking (See Incident 1000).
    * **Envoy:** Handles traffic meshing. Susceptible to timeout configuration drift (See Incident 1022).
    * **RabbitMQ:** Used for async event publishing (See Incident 1049).
* **Known Risks:** * **IPv6 Misrouting:** Asymmetric routing via peering partners has caused PMTUD blackholes, leading to elevated RTT (Incident 1000).
    * **WAF False Positives:** Legacy smart TV querystrings have triggered WAF blocks during rule updates (Incident 1022).

### **cdn-control-plane**
* **Role:** Manages traffic routing across multi-CDN providers (Akamai, CloudFront).
* **Critical Dependencies:**
    * **Kinesis:** Ingests real-time traffic data. High risk of timeout during partition key skew events (Incident 1007).
    * **Bigtable:** Stores routing tables. Clients have flipped retry semantics after library upgrades (Incident 1047).
* **Known Risks:**
    * **BGP Flapping:** Upstream provider route dampening can cause oscillation and retransmits (Incident 1047).

---

## 2. Core Platform & Identity

### **stream-authorizer**
* **Role:** Validates playback tokens and enforces geo-restrictions.
* **Critical Dependencies:**
    * **Spanner:** Global consistency store for token state (Incident 1040).
    * **CloudFront:** Caches authorization policies (Incident 1026).
* **Known Risks:**
    * **TLS Ticket Rotation:** Desynchronization of ticket keys between edge providers has caused resume failures (Incident 1040).
    * **Thundering Herds:** Global cache expiry events frequently cause massive origin pressure (Incident 1050).

### **telemetry-ingest**
* **Role:** Ingests client logs and heartbeat metrics.
* **Critical Dependencies:**
    * **Kinesis:** Primary data stream. Vulnerable to mTLS handshake failures during cipher suite upgrades (Incident 1018).
    * **GCS:** Long-term storage. Susceptible to NTP drift issues (Incident 1025).

---

## 3. Media & Content Engineering

### **manifest-service**
* **Role:** Generates dynamic HLS/DASH manifests for streaming clients.
* **Critical Dependencies:**
    * **RabbitMQ:** Message bus for job queues (Incident 1003).
    * **Cassandra:** Stores manifest segments. Prone to timeouts if `gc.pause_target_ms` is misconfigured (Incident 1006).
* **Known Risks:**
    * **Locale Swapping:** BCP 47 tag normalization errors have historically served wrong language tracks (Incident 1003).