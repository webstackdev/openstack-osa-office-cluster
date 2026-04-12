# Contributions

## Horizon Dashboard for Barbican

The barbican-ui package is essentially a scaffolding project — the panel group (_90) sets PANEL_GROUP_DASHBOARD = 'barbican', which refers to a top-level dashboard slug barbican that doesn't exist. Normal Horizon plugins register under PANEL_GROUP_DASHBOARD = 'project' to appear in the Project tab. Since there's no barbican dashboard defined, the panel silently goes nowhere.

This is consistent with the OSA defaults comment that said barbican-ui "does not provide any functionality at this time" and why horizon_enable_barbican_ui defaults to false. The project has only 13 commits and its README says "Features: TODO".

Bottom line: The barbican-ui package is not functional — it's an incomplete scaffolding. There is no working Barbican Horizon plugin at this point. The Barbican team hasn't built out the UI. You can manage secrets via the CLI (openstack secret store/list/get/delete), which is the standard approach.

## Bugs in Zun to fix upstream

### 1. Zun Docker driver KeyError on images without Entrypoint

- **Repo:** https://opendev.org/openstack/zun (`stable/2025.2` branch)

- **File:** `zun/container/docker/driver.py`, method `DockerDriver.create()`, lines 267-269

- **Bug:** When a container is created from an image that has no `Entrypoint` in its config (e.g., `cirros:latest`), the code does:

  ```python
  container.entrypoint = entrypoint or image_dict['Config']['Entrypoint']
  container.command = command or image_dict['Config']['Cmd']
  ```

  Direct dict access raises `KeyError` if the key is absent. Not all images have `Entrypoint` or `Cmd` in their Docker image config.
- **Fix:** Change to `.get()`:

  ```python
  container.entrypoint = entrypoint or image_dict['Config'].get('Entrypoint')
  container.command = command or image_dict['Config'].get('Cmd')
  ```

- **Hotfix applied:** All 3 compute nodes patched at `/openstack/venvs/zun-32.0.0.0b2.dev7/lib/python3.12/site-packages/zun/container/docker/driver.py`. Will be overwritten on next `os-zun-install.yml` run.

- **Upstream:** Submit via Gerrit to `openstack/zun` on the `stable/2025.2` branch (and `master`).

### 2. Kuryr-libnetwork MAC address update conflicts with OVN port binding

- **Repo:** https://opendev.org/openstack/kuryr-libnetwork (`stable/2025.2` branch)

- **File:** `kuryr_libnetwork/port_driver/driver.py`, method `Driver.update_port()`, lines 144-145

- **Bug:** During `CreateEndpoint`, Kuryr's `update_port()` builds a single Neutron `update_port` API call that includes both `binding:host_id` (to bind the port to the compute host) and `mac_address` (to change the Neutron port MAC to match Docker's generated MAC). With OVN as the ML2 plugin, the port binding is processed first, and then OVN rejects the MAC change on the now-bound port:

  ```bash
  Unable to complete operation on port <uuid>, port is already bound,
  port type: ovs, old_mac fa:16:3e:..., new_mac f6:b8:88:...
  ```

  The MAC update is unnecessary because `kuryr/lib/binding/drivers/veth.py:port_bind()` (line 65-68) already sets the container's veth interface MAC to the Neutron port's MAC address via `_configure_container_iface(hwaddr=port['mac_address'])`. Docker's generated MAC is never used — the veth binding overrides it.

- **Call chain:** `controllers.py:network_driver_create_endpoint()` → `controllers.py:_create_or_update_port()` → `driver.py:Driver.update_port()` → `app.neutron.update_port()` (Neutron API, rejected by OVN)

- **Fix:** Remove or guard the MAC update in `update_port()`. The simplest fix:

  ```python
  # Before (lines 144-145):
  if interface_mac and port['mac_address'] != interface_mac:
      updated_port['mac_address'] = interface_mac

  # After — skip MAC update; veth binding sets the correct MAC on the
  # container interface from the Neutron port's MAC address.
  # Updating the Neutron port MAC is both unnecessary and breaks OVN,
  # which rejects MAC changes on already-bound ports.
  ```

  A more conservative fix would split the update into two calls (MAC first, then binding), but skipping the MAC update entirely is correct since the veth driver doesn't use it.

- **Hotfix applied:** All 3 compute nodes patched at `/openstack/venvs/zun-32.0.0.0b2.dev7/lib/python3.12/site-packages/kuryr_libnetwork/port_driver/driver.py`. Kuryr-libnetwork restarted on all nodes. Will be overwritten on next `os-zun-install.yml` run.

- **Upstream:** Submit via Gerrit to `openstack/kuryr-libnetwork` on the `stable/2025.2` branch (and `master`). Note: kuryr-libnetwork is in maintenance mode with low activity — patch may need to be self-approved or find a core reviewer.

## OSA Role for Zaqar

OSA terminology: The correct term is "role", not "package." Each OpenStack service gets:

- An Ansible role — a standalone git repo like openstack-ansible-os_trove at opendev.org/openstack/openstack-ansible-os_trove. These are listed in ansible-role-requirements.yml and pulled in at deploy time.
- An install playbook — os-<service>-install.yml in the main openstack-ansible repo that orchestrates the role.
- Inventory/config integration — conf.d/, env.d/, group_vars files that define container groups and default variables.

There are currently 29 service roles. Zaqar is not one of them.

Why no Zaqar role? Likely a combination of:

1. Low adoption — Zaqar is a niche service. Most OpenStack clouds use external message brokers (RabbitMQ, Kafka) for app messaging, and Zaqar's SQS-like model has limited demand. The PTL (Hao Wang) appears to be essentially the sole maintainer.
2. Nobody built it — OSA roles are contributed by people who need them. The OSA team (PTL: Dmitriy Rabotyagov) maintains 29 roles already. No one with a Zaqar deployment has contributed the OSA role, and the OSA team hasn't prioritized it.
3. Zaqar itself is maintained but minimal — it still gets releases every cycle (21.0.0 for 2025.2), Python version bumps, and bug fixes. But the 2025.2 release notes show only 1 new feature, a few config cleanups, and 1 bug fix. The install docs haven't been updated since Ocata (~2017). It's alive but barely.
For comparison, services like Trove, Designate, Manila all have active multi-person contributor teams, regular feature work, and OSA roles. Zaqar is more like Adjutant or Masakari — officially governed, has a role, but low activity. Except Zaqar doesn't even have the OSA role.

Side project idea — writing openstack-ansible-os_zaqar: This is actually quite feasible and would be a genuine contribution. Here's why it's interesting:

- Good template to follow — every os_* role has the same structure. You could clone os_trove or os_designate as a starting point and adapt it.
- Bounded scope — Zaqar is a relatively simple service (API server + storage backend). No compute agents, no per-hypervisor components. The role would be: create LXC container, install from source, template zaqar.conf, create systemd service, register in Keystone, add HAProxy backend.
- Real gap — there's no alternative. Kolla (the container-based deployer) has Zaqar support but OSA doesn't.
MongoDB dependency is the hardest part — you'd need to either create a MongoDB role or support the Swift/Redis backends to avoid that dependency.
- Low risk of conflict — with essentially one maintainer (Hao Wang), getting reviews might be slow, but you're not stepping on anyone's toes.

The contribution process would go through OpenDev/Gerrit, and you'd want to coordinate on the #openstack-ansible IRC channel with the OSA PTL (noonedeadpunk).

AWS doesn't publicly disclose SQS's backing store, but from various re:Invent talks and engineering blog posts, SQS uses a custom-built distributed storage layer — not an off-the-shelf database. It's purpose-built for the access patterns of a message queue (write-heavy, TTL-based expiry, claim/visibility-timeout semantics). The original SQS was built on top of a distributed hash table; the later redesign (around 2020, "new SQS") uses a log-structured storage engine. It's all proprietary internal infra.

Your instinct about Redis is reasonable but the tradeoff is more nuanced:

Why MongoDB makes sense for Zaqar:

Durability by default — messages survive restarts without special config. Redis requires AOF/RDB persistence config and even then can lose the last second of writes.
Rich queries — Zaqar's management store needs indexing on queues, subscriptions, claims with TTL, metadata filtering. MongoDB handles this natively. Redis would need custom data structure design for each.
TTL/expiry — MongoDB has native TTL indexes (delete documents after N seconds). This maps directly to message TTL and claim grace periods.
Partitioning — Zaqar's MongoDB driver partitions message data across multiple databases to reduce write lock contention. This was designed specifically for MongoDB's concurrency model.
Where Redis would be better:

Latency — Redis is ~10x faster for simple get/put. For a high-throughput message queue, this matters.
Memory efficiency for small messages — no BSON overhead.
Simpler operations — no replication lag, no WiredTiger cache tuning.
The real answer is historical — Zaqar (originally called "Marconi") was designed around 2013-2014 when MongoDB was the trendy "web-scale" NoSQL choice. The team built the MongoDB driver first and most thoroughly. Redis and Swift drivers were added later as alternatives but never got the same level of testing or features. By the time Redis would have been the obvious choice, Zaqar's adoption was too low for anyone to invest in making Redis the primary path.

Zaqar 2025.2 actually supports Redis for both message_store and management_store, so you could skip MongoDB entirely and use Redis. The config is just:

```ini
[drivers]
message_store = redis
management_store = redis

[drivers:message_store:redis]
uri = redis://127.0.0.1:6379

[drivers:management_store:redis]
uri = redis://127.0.0.1:6379
```

This would eliminate the MongoDB dependency entirely and is arguably a better fit for a home lab (lighter weight, no /dev/sdc needed). The question is whether the Redis driver is as well-tested as MongoDB in practice — given Zaqar's low contributor count, "well-tested" is relative for any backend.

Considered Kafka architecture and message queue access patterns
Yes, almost perfectly. Kafka was literally designed around these exact patterns:

| Requirement | Kafka's approach |
| --- | --- |
| Append-heavy writes | Kafka's core abstraction is an append-only commit log. Writes are sequential disk appends — this is why Kafka gets near-memory throughput from spinning disks. |
| Sequential reads | Consumers read sequentially from a log offset. The OS page cache handles this beautifully since reads follow writes linearly. |
| TTL-based GC | Kafka uses log segment retention — old segments are deleted after a configurable time or size. Zero per-message overhead, just drop whole files. |
| High throughput + ordering within partition | Kafka guarantees ordering within a partition, and partitions are the unit of parallelism. This is the fundamental design. |

The one mismatch is claim/visibility semantics. Kafka doesn't natively support "claim a message, process it, then ACK or let it become visible again after a timeout" — which is SQS's core model. Kafka uses consumer group offsets: a consumer reads from position N, processes it, and commits offset N+1. If the consumer dies, another consumer in the group picks up from the last committed offset. This is simpler but different:

- SQS model: individual message-level claims with visibility timeout. Multiple consumers can each claim different messages from the same queue concurrently. Failed claims auto-retry.
- Kafka model: partition-level assignment. One consumer owns an entire partition. Rebalancing happens at the partition level, not per-message.

So Kafka is a better fit for streaming (ordered log consumption, high throughput) while SQS/Zaqar are a better fit for task queues (individual message claiming, competing consumers on single queues).

This is actually why the cloud providers all built custom systems — they wanted the durability and throughput model of Kafka (append-only log, sequential I/O, segment-based retention) combined with the consumption model of a traditional message queue (per-message visibility, claim semantics). Kafka gives you 90% of what you need but the last 10% (claim/visibility) is architecturally incompatible with its offset-based design.

Interestingly, this also explains why Zaqar picked MongoDB over Kafka-like storage — Zaqar needs per-message operations (claim this specific message, set TTL on this message, delete this message by ID), which map naturally to document operations but poorly to an append-only log.

### Options to Replace MongoDB in Zaqar

A few options that are arguably better fits than either Kafka or MongoDB for SQS/Zaqar-style task queue semantics:

Redis Streams (Redis ≥ 5.0) — the strongest candidate. Redis Streams are an append-only log (like Kafka) but with per-message ACK via consumer groups. The key primitives map almost exactly to SQS:

- `XADD` = publish message
- `XREADGROUP` = claim next messages (assigns to a consumer)
- `XACK` = mark message processed
- `CLAIM` = reclaim messages from stalled consumers (visibility timeout equivalent)
- `XAUTOCLAIM` = automatically reclaim messages pending longer than a threshold
- The pending entry list (PEL) is essentially a visibility timeout tracker

This is actually what Zaqar should be using if it were redesigned today. It has the per-message claim semantics that Kafka lacks, with the throughput that MongoDB can't match. The main weakness is durability — you need `appendonly yes` and `appendfsync everysec` (or `always` with a throughput penalty).

PostgreSQL with SKIP LOCKED — surprisingly effective for moderate scale. Since PostgreSQL 9.5:

```sql
-- Claim a message
UPDATE messages SET status='claimed', claimed_until=now()+interval '30s'
WHERE id = (SELECT id FROM messages WHERE queue='myqueue' AND status='pending'
            ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
RETURNING *;
```

`SKIP LOCKED` gives you non-blocking competing consumers on a single queue — exactly the SQS model. Combined with partitioned tables and `pg_cron` for TTL cleanup, PostgreSQL handles this well up to thousands of messages/sec. Zaqar already has a SQLAlchemy driver for the management store; extending it to the message store with `SKIP LOCKED` would give it a backend requiring zero new dependencies (OSA already deploys MariaDB/Galera, and MariaDB 10.6+ also supports `SKIP LOCKED`).

**RocksDB** (embedded LSM-tree) — this is what most purpose-built message systems actually use internally. RocksDB has native **TTL support via compaction filters** (expired keys are dropped during background compaction — zero-cost GC), sequential writes to an append-only WAL, and excellent read performance for sequential scans. If you were building a Zaqar storage driver from scratch, embedding RocksDB would give you near-optimal performance without any external service dependency. But it's a C++ library, not a standalone service — you'd need to wrap it in Python (via `python-rocksdb`).

**Cassandra / ScyllaDB** — wide-column stores with **native per-row TTL**. Model: partition key = queue_id, clustering key = timeuuid. Writes are fast (append-only memtable → SSTable), reads within a partition are ordered, and TTL expiry happens automatically during compaction. Claim semantics via lightweight transactions (`IF status = 'pending'`). ScyllaDB is the C++ rewrite of Cassandra with much lower latency. Overkill for a home lab, but it's what you'd pick for a hyperscaler SQS clone.

**NATS JetStream** — a purpose-built messaging server with persistence. Has `AckWait` (visibility timeout), `MaxDeliver` (dead letter after N failures), and per-message ack/nak/in-progress semantics. Essentially SQS-in-a-box. But it's a Go binary, not a storage library — you'd be replacing Zaqar entirely rather than backing it.

**The ranking for "best Zaqar backend if you could choose anything":**

1. **Redis Streams** — best balance of performance, simplicity, and semantic fit
2. **PostgreSQL/MariaDB with SKIP LOCKED** — zero new dependencies in an OSA deployment
3. **ScyllaDB** — excellent write throughput, native per-row TTL (automatic cleanup via compaction), partition-ordered reads map perfectly to per-queue message ordering
4. **RocksDB** — best raw performance but requires embedding
5. **MongoDB** — what Zaqar uses now; works, but not optimal
6. **Kafka** — wrong consumption model for task queues

The MariaDB/`SKIP LOCKED` option is particularly interesting for the OSA role side project — an `os_zaqar` role that uses the existing Galera cluster as the backing store would need zero new infrastructure and would be far more deployable than requiring MongoDB.

ScyllaDB's main weakness for this use case is claim semantics. Claiming a message requires a compare-and-swap (UPDATE ... IF status = 'pending'), which in Scylla/Cassandra is a lightweight transaction (LWT) involving a Paxos consensus round. LWTs are ~10x slower than regular writes. In a high-contention scenario with many consumers racing to claim messages from the same queue, this becomes a bottleneck.

Redis Streams and SQL SKIP LOCKED both handle the claiming hot path much more efficiently — Redis via its native XREADGROUP (single-threaded, no contention by design) and SQL via row-level locking with SKIP LOCKED (pessimistic lock that competing consumers skip past rather than block on).

Where ScyllaDB would jump to #1 is if you were building at hyperscale — millions of queues, multi-region, petabytes of message data. At that scale, Redis runs out of memory and PostgreSQL runs out of single-node capacity. That's the Cassandra/Scylla sweet spot. But for Zaqar (which nobody runs at hyperscale), it's over-provisioned complexity.

### Zaqar at Hyper-Scale

How I reached that conclusion about Zaqar — it's an inference from circumstantial evidence, not a proven fact. The signals:

- Single maintainer (Hao Wang) for years. A service running at scale at any major organization would have that org contributing engineers.
- Release notes are trivially small — 2025.2 had 1 new feature (request ID header), a few config cleanups, and 1 bug fix. If anyone was running this under real load, there'd be bug reports, performance patches, feature requests.
- Install docs frozen since 2017 (Ocata, Ubuntu 14.04, Python 2.7). Nobody deploying this in production would tolerate that.
- No OSA role, no Kolla Kubernetes support — the two main deployment tools. If a large operator needed Zaqar, they'd have contributed these.
- OpenStack User Surveys historically showed Zaqar adoption in single-digit percentages. The large OpenStack operators (telcos like AT&T/China Mobile, hosting companies like Rackspace/OVH) have never publicly mentioned running Zaqar.
- That said — I could be wrong. A large Chinese telco or enterprise could be running Zaqar internally without public visibility. The PTL being China-based (Hao Wang, sxmatch1986@gmail.com) suggests there may be Chinese adoption that isn't visible in English-language OpenStack community channels. But even so, "hyperscale" (millions of queues, billions of messages/day) seems unlikely given the codebase velocity.

For the hyperscaler equivalents — absolutely yes, they run at massive scale:

- AWS SQS — AWS has publicly stated SQS processes "hundreds of billions of messages per day." It's one of the oldest AWS services (launched 2004) and is deeply embedded in AWS's own internal architecture (Lambda event sources, S3 event notifications, CloudFormation workflows all use SQS internally).

- Google Cloud Pub/Sub — Google has shared it handles "hundreds of millions of messages per second" internally (it underpins many Google services). The external Cloud Pub/Sub product is the same infrastructure.

- Azure Service Bus / Azure Queue Storage — Microsoft hasn't published specific numbers as openly, but Azure Queue Storage is part of the Azure Storage platform which processes "exabytes" of data. Service Bus is used internally by Azure services (Event Grid, Logic Apps).

The fundamental difference is that these are core platform primitives at their respective clouds — they're load-bearing infrastructure that other services depend on. Zaqar is an optional add-on service in OpenStack that no other OpenStack service depends on. Nobody needs Zaqar to make Nova, Neutron, or Cinder work, so there's no forcing function for adoption. RabbitMQ is already deployed for OpenStack's internal RPC, and operators who need tenant-facing messaging typically just expose RabbitMQ directly or tell tenants to run their own.

### How do RabbitMQ deployed directly by tenants compare to AWS SQS?

They serve overlapping use cases but are architecturally very different:

**Fundamental model difference:**

- **SQS** = pull-based message queue as a service. No broker to manage. HTTP API. Messages sit in a queue until a consumer polls for them.
- **RabbitMQ** = push-based message broker. Runs as a stateful server process. AMQP protocol (persistent TCP connections). The broker actively routes and pushes messages to consumers.

**Practical comparison:**

| Dimension              | AWS SQS                                                      | RabbitMQ (self-deployed)                                     |
| ---------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **Operations**         | Zero — fully managed, no servers                             | You own it: install, patch, monitor, scale, handle failover  |
| **Protocol**           | HTTP REST API (stateless)                                    | AMQP 0-9-1 (stateful TCP connections), also supports MQTT, STOMP |
| **Routing**            | Simple: one queue, consumers poll                            | Rich: exchanges, bindings, routing keys, topic patterns, headers matching |
| **Ordering**           | Best-effort (standard) or strict FIFO (FIFO queues)          | Strict ordering per-queue by default                         |
| **Delivery model**     | Pull only (long polling)                                     | Push (broker delivers to consumers), also supports pull      |
| **Latency**            | ~10-50ms typical (HTTP overhead)                             | ~1ms or less (persistent TCP, binary protocol)               |
| **Throughput**         | Nearly unlimited (scales horizontally behind the scenes)     | Limited by broker instance (tens of thousands msg/sec per node, more with clustering) |
| **Dead letter**        | Built-in (redrive policy)                                    | Built-in (dead letter exchanges)                             |
| **Visibility timeout** | Native (core feature)                                        | Not native — uses manual ack with prefetch + nack/reject for redelivery |
| **Message size**       | 256 KB max (or pointer to S3)                                | No hard limit, but performance degrades above ~128 KB        |
| **Durability**         | Always durable (replicated across AZs)                       | Configurable: durable queues + persistent messages = survives restart; transient = lost on crash |
| **Multi-tenancy**      | Native (IAM-based isolation)                                 | Manual: vhosts provide namespace isolation, but you manage auth yourself |
| **Cost at rest**       | Pay per request (~$0.40/million)                             | Pay for the VM/container whether messages flow or not        |
| **Cost at scale**      | Scales linearly with usage (can get expensive at billions of messages) | Fixed infra cost regardless of message volume                |

**Where RabbitMQ wins:**

- **Latency** — sub-millisecond vs SQS's HTTP overhead
- **Routing flexibility** — topic exchanges, fanout, header-based routing are far more expressive than SQS's single-queue model (you'd need SQS + SNS to approximate what RabbitMQ exchanges do natively)
- **Protocol support** — AMQP, MQTT (IoT), STOMP (web). SQS is HTTP-only
- **Cost at steady high throughput** — one RabbitMQ VM handling 50k msg/sec is far cheaper than SQS billing per-request

**Where SQS wins:**

- **Zero operations** — nothing to patch, scale, or monitor. For a tenant on OpenStack, running RabbitMQ means managing a clustered stateful service, which is significant operational burden
- **Infinite scalability** — no capacity planning. SQS scales transparently from 1 message/day to billions
- **Durability guarantees** — SQS replicates across AZs by design. RabbitMQ clustering + mirrored queues (now quorum queues) can achieve similar durability but require careful setup
- **Integration** — SQS is wired into the entire AWS ecosystem (Lambda triggers, S3 events, CloudWatch alarms). RabbitMQ is standalone

**For an OpenStack tenant specifically**, RabbitMQ is the pragmatic choice because SQS doesn't exist in their environment. They'd typically launch a VM (or a Trove instance, if someone added RabbitMQ as a datastore), install RabbitMQ, and use it. This is exactly the gap Zaqar was meant to fill — give OpenStack tenants an SQS-like managed experience so they don't have to run their own RabbitMQ. But since Zaqar never gained traction, tenants just run RabbitMQ (or Redis, or NATS) themselves.

The irony is that **OpenStack itself** already runs RabbitMQ for its internal oslo.messaging RPC. So the infrastructure is already there — it's just not exposed as a tenant-facing service. Amazon did effectively the same thing in reverse: SQS (2004) came first as an external service, and AWS's internal service communication evolved around it.

### Zaqar API vs AWS SQS API:

The core operations map almost 1:1:

Operation	SQS	Zaqar
Create queue	CreateQueue	PUT /v2/queues/{name}
Delete queue	DeleteQueue	DELETE /v2/queues/{name}
List queues	ListQueues	GET /v2/queues
Send message	SendMessage / SendMessageBatch	POST /v2/queues/{name}/messages (batch by default, array of messages)
Receive message	ReceiveMessage	POST /v2/queues/{name}/claims (claim = receive)
Delete message	DeleteMessage / DeleteMessageBatch	DELETE /v2/queues/{name}/messages/{id}?claim_id=X
Change visibility	ChangeMessageVisibility	PATCH /v2/queues/{name}/claims/{claim_id} (update claim TTL)
Release claim	(let visibility timeout expire)	DELETE /v2/queues/{name}/claims/{claim_id} (explicit release)
Queue metadata	GetQueueAttributes / SetQueueAttributes	GET / PATCH /v2/queues/{name}

Key differences:

Claims are first-class objects in Zaqar. In SQS, you ReceiveMessage and get a ReceiptHandle (an opaque token) that you use to delete or extend visibility. In Zaqar, claims are explicit resources with their own CRUD — you create a claim (getting a claim_id), can query it, update its TTL, or release it. This is more RESTful but more verbose.

SQS has features Zaqar lacks:

FIFO queues with deduplication — SQS has MessageGroupId and MessageDeduplicationId. Zaqar has no deduplication, and ordering is only guaranteed for a single producer.
Dead letter queues — SQS has native RedrivePolicy to move failed messages to a DLQ after N receive attempts. Zaqar has no equivalent.
Delay queues / message timers — SQS supports DelaySeconds per-queue or per-message. Zaqar added default_message_delay in the config but it's limited.
Long polling — SQS supports WaitTimeSeconds to block up to 20s for new messages. Zaqar's WSGI transport doesn't support this (WebSocket transport could, in theory).
Zaqar has features SQS lacks:

Subscriptions/notifications — push to HTTP/HTTPS/email/trust endpoints when messages arrive. SQS requires pairing with SNS for this. Zaqar combines both SQS and SNS functionality.
Pre-signed URLs — time-limited access without Keystone tokens, configurable per-operation. SQS has pre-signed URLs too, but they work differently (IAM-based).
WebSocket transport — persistent bidirectional connection. SQS is HTTP-only.
Pools/flavors — admin can define multiple storage backends and let users choose. No SQS equivalent (SQS is opaque).
Client-ID is unusual — Zaqar requires a Client-ID UUID header on every request to avoid echoing messages back to the poster. SQS doesn't have this concept.

Overall, Zaqar's API is clearly SQS-inspired but more RESTful and more explicit about the claim lifecycle. SQS is more battle-hardened with features born from real-world usage (DLQ, FIFO dedup, long polling) that Zaqar never developed because the user base wasn't there to demand them.

Why Redis isn't separately listed in the ranking:

Good catch — there's an important distinction I conflated. The ranking lists Redis Streams at #1, but that's a hypothetical new driver using the Streams API (XADD/XREADGROUP/XACK). Zaqar's existing Redis driver does NOT use Redis Streams — it was written before Streams existed (Redis Streams shipped in 5.0, 2018) and uses basic Redis data structures (sorted sets for message ordering, hashes for message bodies, key expiry for TTL).

The existing Zaqar Redis driver should be on the list separately:

Redis Streams — hypothetical new driver; best semantic fit (doesn't exist in Zaqar today)
PostgreSQL/MariaDB with SKIP LOCKED — zero new dependencies (doesn't exist in Zaqar today)
Redis (existing Zaqar driver) — works today, already tested, lightweight, no new dependencies if you install Redis; uses sorted sets + hashes rather than Streams so it's less elegant but functional
ScyllaDB — excellent at scale, weak on claim semantics
RocksDB — best raw performance, embedding complexity
MongoDB (existing Zaqar driver) — works today, heaviest dependency
Kafka — wrong consumption model

The existing Redis driver would slot at #3 — it's the pragmatic "works right now, no new code" choice. Its main downside vs a Redis Streams driver is that the sorted-set approach requires more round trips for claim operations and doesn't have the native consumer-group/PEL semantics that Streams provides.

### Why RabbitMQ isn't in the list of alternatives

RabbitMQ wasn't included because it occupies an awkward middle ground for this use case — it's a message broker, not a storage backend.

The items on the list (MongoDB, Redis, ScyllaDB, RocksDB, PostgreSQL) are all data stores — you write data in, and the application layer (Zaqar) implements the queue semantics (claim, TTL, expiry) on top of stored data. Zaqar is the broker; these are the persistence layer.

RabbitMQ is itself a broker with its own queue semantics, claim model, TTL, routing, consumer groups, etc. Using RabbitMQ as a Zaqar backend would mean building a broker on top of a broker — Zaqar would receive an HTTP request, translate it into an AMQP operation against RabbitMQ, and return the result. You'd have two layers of queue semantics fighting each other:

Claim TTL: Zaqar has explicit claim TTL + grace period. RabbitMQ has consumer prefetch + ack timeout. These models don't compose cleanly.
Message TTL: Zaqar sets per-message TTL. RabbitMQ has per-message and per-queue TTL, but expired messages are only dropped from the head of the queue (they can block behind non-expired messages).
Random access: Zaqar supports GET /messages/{id} — fetching a specific message by ID. RabbitMQ queues are FIFO — you can't read a message by ID without consuming everything before it.
Listing: Zaqar supports GET /queues/{name}/messages to browse without claiming. RabbitMQ doesn't support non-destructive browsing natively (you'd need the management API, which is a polling HTTP endpoint, not a data store).
That said, it's not impossible. You could model it as:

Zaqar queue → RabbitMQ queue
Post message → basic_publish
Claim → basic_get with manual ack (prefetch=N for batch claims)
Delete message → basic_ack
Release claim → basic_nack with requeue=true
But you'd lose the features that depend on random access and browsing, and you'd gain nothing that RabbitMQ adds over Redis or PostgreSQL — since Zaqar is already implementing the queue abstraction.

The deeper irony: if you already have RabbitMQ and want tenant-facing queuing, you'd be better off just exposing RabbitMQ directly (with per-tenant vhosts) rather than putting Zaqar in front of it. That's what most OpenStack operators actually do, which is another reason Zaqar never caught on.

So it's not that RabbitMQ is bad — it's that using a broker as a backend for another broker is architecturally redundant. The list only includes storage engines because that's the role Zaqar needs filled.
