# On-Call Runbook: Standard Mitigation Procedures

**Purpose:** Standard Operating Procedures (SOPs) for mitigating common incidents identified in our history.
**Mandate:** All mitigations must be followed by a post-mortem entry.

## 1. Dealing with "Partition Key Skew"
**Symptoms:** One shard or node running at 100% CPU while others are idle. High latency in `billing-connector` or `device-registry`.
**Reference Incidents:** 1001, 1012, 1020.
**Action Plan:**
1.  **Identify the Key:** Look for changes in partition strategy. Did a deployment change the hashing algorithm?
2.  **Mitigation:**
    * Initiate rollback of the component (e.g., `billing-connector`).
    * Patch `redis.max_connections` if Redis is the bottleneck (Incident 1012).
    * **Long Term:** Rebalance partitions and add lag-aware scaling (Follow-up Action from Incident 1020).

## 2. Dealing with "Clock Skew / NTP Drift"
**Symptoms:** `Mass 401s`, `Auth failures`, or invalid signature errors.
**Reference Incidents:** 1025, 1032.
**Action Plan:**
1.  **Diagnosis:** Check `ttfs` (Time to First Signal) against NTP drift alarms.
2.  **Mitigation:**
    * Increase token skew allowances immediately to stop the bleeding.
    * Patch `cache_ttl_seconds` if necessary to force a refresh (Incident 1025).
    * **Long Term:** Tighten NTP drift alarms and increase default token skew allowances in the `telemetry-ingest` service.

## 3. Dealing with "Deployment / Rollout Failures"
**Symptoms:** Error rates spike immediately following a canary or production deployment.
**Reference Incidents:** 1000, 1003, 1013.
**Action Plan:**
1.  **Immediate Rollback:** Do not attempt to fix forward. Roll back to the last known good commit.
2.  **Drain Queues:** If backlogs formed in PostgreSQL, RabbitMQ, or Zookeeper, drain them *gradually* to prevent a secondary overload (Incident 1000).
3.  **Feature Flag Kill-Switch:**
    * Disable new features via flags like `feature.hdr10.enabled` (Incident 1000).
    * Disable A/B tests via `abr.aggressiveness` (Incident 1013).

## 4. Post-Incident Requirements
For every high-severity incident, the following follow-up actions are **mandatory** as per our engineering standards:
* **Dashboards:** Add SLO dashboards for the failing component with multi-signal alerting (User + System + Synthetic).
* **Linting:** Enforce config/schema linting in CI with **hard fails** on violations.
* **Chaos Testing:** Introduce chaos/negative tests that specifically mirror the peak traffic shape observed during the incident.
* **Game Days:** Schedule quarterly game-days to rehearse the specific failure scenario (e.g., Failover, Latency Injection).
* *(Derived from "followup_actions" across all incidents in uploaded:netflix_incident_metrics.json)*