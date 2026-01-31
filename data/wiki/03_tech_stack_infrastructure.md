# Infrastructure & Technology Stack Deep Dive

**Overview:** This page details the specific behavior of our persistent stores and networking components under failure conditions.

## Data Persistence Layer

### **PostgreSQL**
* **Usage:** Primary relational store for `edge-proxy`, `playback-api`, and `device-registry`.
* **Failure Behavior:**
    * **Head-of-Line Blocking:** Under heavy network retries (e.g., caused by PMTUD blackholes), PostgreSQL connections exhibit severe head-of-line blocking. Connection reuse often hides the real error surface until the system collapses (Incident 1000).
    * **Capabilities Detection:** Updates to User Agent parsers in the DB layer have misclassified hardware (e.g., 4K TVs detected as SD-only), degrading streams (Incident 1056).

### **Cassandra**
* **Usage:** High-volume store for `manifest-service`, `player-config`, and `subtitle-compiler`.
* **Failure Behavior:**
    * **Compaction Stalls:** Mis-sized heaps starve compaction threads, leading to long GC pauses and read timeouts (Incident 1021).
    * **Drift:** Client library upgrades have historically flipped retry/backoff semantics, causing request amplification (Incident 1042).

### **Zookeeper**
* **Usage:** Coordination for `billing-connector`, `ab-test-gateway`, and `metadata-normalizer`.
* **Failure Behavior:**
    * **Retaliation:** Extremely sensitive to retry storms. When upstream services (like `ab-test-gateway`) trip fairness algorithms, Zookeeper backlogs grow rapidly (Incident 1015).

## Networking & Edge

### **Service Mesh (Istio/Envoy)**
* **Usage:** Traffic management for `license-issuer`, `profile-service`, and `audio-mixer`.
* **Failure Behavior:**
    * **Retry Semantics:** Upgrades to the mesh data plane (Envoy) or control plane (Istio) have inadvertently flipped retry/backoff logic, leading to self-DDoS (Incident 1002).
    * **Partition Skew:** Partition key changes in upstream services often lead to hot keys dominating single shards in the mesh (Incident 1012).

### **CDN (Akamai/CloudFront)**
* **Usage:** Content delivery and edge logic.
* **Failure Behavior:**
    * **Purge Storms:** Mis-scoped purge jobs can invalidate hot ABR segments worldwide, causing origins to thrash (Incident 1033).
    * **GeoIP Mismatches:** Updates to vendor GeoIP databases have mislabeled CGNAT blocks, causing wrong CDN selection and poor performance (Incident 1042).