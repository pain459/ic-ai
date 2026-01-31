# Known Failure Modes & Engineering Anti-Patterns

**Objective:** To document recurring architectural flaws identified in Post-Mortems (PMs).
**Reference Data:** Netflix Incident Metrics

## 1. The "Configuration Drift" Hazard
**Definition:** Small, seemingly innocuous configuration changes that cause disproportionate outages due to lack of validation in staging.

* **Case Study: Redis Connection Saturation**
    * **Incident:** 1014
    * **Trigger:** A change in `redis.max_connections` (from 335 to 670) interacted poorly with Zookeeper under load.
    * **Result:** Driven p95 latency spikes and 5xx errors from dependent services.
    * **Mitigation:** Mitigation required rolling back and patching the config.
    * **Reference:**

* **Case Study: Session Token TTL**
    * **Incident:** 1024
    * **Trigger:** Increasing `session.token.ttl` from 24765 to 74295.
    * **Result:** The change interacted poorly with CloudFront, causing WAF false positives and mass blocking of manifest requests.
    * **Reference:**

## 2. The "Thundering Herd" & Cache Synchronization
**Definition:** When cache items expire simultaneously across the fleet, or when a feature flag change forces a global refresh, causing a massive spike in traffic to the origin.

* **Case Study: Coordinated Cache Expiry**
    * **Incident:** 1001 (Billing Connector)
    * **Mechanism:** The `feature.hdr10.enabled` flag synchronized TTLs and bypass ratios. A small miss rate increase created global origin pressure on Zookeeper.
    * **Impact:** 12% of traffic affected for ~14 hours.
    * **Reference:**

* **Case Study: Global Revalidation Storms**
    * **Incident:** 1079 (Stream Authorizer)
    * **Mechanism:** Origin max concurrency settings collided with a global revalidation storm triggered by fleet synchronization drift.
    * **Reference:**

## 3. Deployment & Schema Compatibility
**Definition:** Failures caused by backward-incompatible changes in data schemas or binary protocols during rollouts.

* **Case Study: The "Poison Pill" Message**
    * **Incident:** 1013 (A/B Test Gateway)
    * **Mechanism:** A schema evolution rolled out without full compatibility checks. Producers wrote fields that consumers could not parse, leading to silent drops and reprocessing loops in Zookeeper.
    * **Impact:** 30% of traffic affected; mitigation took over 7 hours.
    * **Reference:**

* **Case Study: Missing Backfills**
    * **Incident:** 1011 (CDN Control Plane)
    * **Mechanism:** A metadata schema migration backfill job excluded "soft-deleted" records, resulting in partial title graphs being published.
    * **Reference:**