# Home Cloud

9 OpenStack services registered (Keystone, Glance, Nova, Neutron, Cinder, Swift, Heat, Horizon, Placement)
3 compute nodes (cloud-6core, cloud-celeron, cloud-eugene) — all enabled / up
6 OVN agents (3 Controller Gateway + 3 Metadata) — all `:-)` / UP

Node roles (adapted for 4-node home lab)

| OSA Role | Host | Notes |
|---|---|---|
| Deployment host | This workstation | Runs `openstack-ansible` commands; only needs mgmt network access |
| Infrastructure (shared_infra) | cloud-4core | galera, rabbitmq, memcached, utility (single node, no HA) |
| Identity (keystone) | cloud-4core | |
| Dashboard (horizon) | cloud-4core | |
| Image (glance) | cloud-4core | Image store on `/dev/sda` (128G SSD), accessed via storage network |
| Network API (neutron) | cloud-4core | |
| Network northd (OVN) | cloud-4core | |
| Compute API (nova api/conductor/scheduler) | cloud-4core | |
| Placement | cloud-4core | |
| Block Storage API (cinder) | cloud-4core | |
| Load balancer (haproxy) | cloud-4core | Single node — no keepalived needed |
| Repo server | cloud-4core | |
| Coordination (zookeeper) | cloud-4core | |
| Compute (hypervisor) | cloud-6core, cloud-celeron, cloud-eugene | |
| Network gateway (OVN) | cloud-6core, cloud-celeron, cloud-eugene | DVR — compute nodes are OVN gateways |
| Block Storage volume (cinder LVM) | cloud-eugene | 476.9G SSD (`sde`) |
| Object Storage (swift) | cloud-eugene | 2x 1.8T HDD (`sdc`, `sdd`) |

## Repo Structure (proposed additions)

```bash
home-cloud/
├── ansible.cfg                              # (existing, keep)
├── ansible-navigator.yml                    # (existing, keep)
├── INVENTORY.md                             # (existing, keep)
├── PLANNING.md                              # (this file)
├── playbooks/
│   ├── inventory/
│   │   ├── hosts.yml                        # (existing — extend with new groups)
│   │   ├── group_vars/
│   │   │   ├── all.yml                      # (existing — extend with shared vars)
│   │   │   ├── compute.yml                  # (extend with compute-specific vars)
│   │   │   ├── controllers.yml              # (extend with controller-specific vars)
│   │   │   └── ...
│   │   └── host_vars/
│   │       ├── mgmt.cloud-4core.local.yml   # (extend with network interface mapping)
│   │       ├── mgmt.cloud-6core.local.yml
│   │       ├── mgmt.cloud-celeron.local.yml
│   │       └── mgmt.cloud-eugene.local.yml
│   ├── group_vars/all/vault.yml             # (existing — extend with OSA secrets)
│   ├── roles/
│   │   ├── ansible-hardening/               # (existing — OBSOLETE, RHEL7 only, needs replacement)
│   │   ├── prepare_target_host/             # NEW — packages, kernel, sysctl, hosts file
│   │   ├── configure_networking/            # NEW — netplan bridge configuration
│   │   ├── configure_storage/               # NEW — LVM for Cinder
│   │   ├── prepare_deployment_host/         # NEW — clone OSA, bootstrap (on this workstation)
│   │   └── deploy_osa_config/               # NEW — template and deploy OSA configs
│   ├── templates/
│   │   └── openstack_deploy/
│   │       ├── openstack_user_config.yml.j2
│   │       ├── user_variables.yml.j2
│   │       └── env.d/
│   │           └── cinder.yml.j2
│   ├── prepare_target_hosts.yml             # NEW — Phase 1
│   ├── prepare_deployment_host.yml          # NEW — Phase 2
│   ├── deploy_osa_config.yml                # NEW — Phase 3
│   ├── run_osa_deploy.yml                   # NEW — Phase 4
│   ├── verify_openstack.yml                 # NEW — Phase 5
│   ├── harden_host.yml                      # (existing, keep)
│   ├── setup_node_playbook.yml              # (existing, can retire or keep for reference)
│   └── README.md                            # (update)
└── collections/                             # (existing, keep)
```

## Networking architecture

The environment uses **Neutron Option 2 (Self-service networks)** with the ML2/OVN plugin. This provides full L2/L3 virtual networking — tenants can create their own virtual networks, routers, and subnets without knowledge of the underlying physical infrastructure. Overlay networks use **Geneve** tunnels.

**Key design principle:** The physical provider network has NO IP addresses assigned to the cloud nodes. It is a layer-2-only bridge (`br-vlan`) that OVN uses for north-south traffic (floating IPs, SNAT). Tenants create self-service networks on Geneve overlays. OVN routers handle NAT between tenant networks and the external (provider) network.

## Installation Plan

### Phase 0: Pre-requisites (manual / one-time)

- [ ] Verify all four nodes have Ubuntu 24.04, are reachable via SSH from this workstation over management network
- [ ] Verify all nodes have connectivity on all four networks (`ping` tests on mgmt, overlay, storage; link-up check on provider)
- [ ] Verify RT-AC57U router DHCP range is 192.168.2.2 - 50 (confirmed), leaving 192.168.2.51 - 254 available for OpenStack floating IPs
- [ ] Ensure this workstation has `ansible` and `ansible-playbook` installed

### Phase 1: Prepare target hosts (from this workstation)

Playbook: `playbooks/prepare_target_hosts.yml`
Runs against: all hosts

Tasks:

1. **Update and upgrade** all packages, install `linux-modules-extra`
2. **Install required packages:** `bridge-utils`, `debootstrap`, `openssh-server`, `tcpdump`, `vlan`, `python3`, `chrony`, `lvm2`
3. **Configure NTP** (chrony) on all hosts
4. **Load kernel modules:** `br_netfilter`, `8021q`, `bonding`, `openvswitch` (persisted via `/etc/modules-load.d/`)
5. **Configure sysctl:** `net.ipv4.ip_forward=1`, bridge nf_call settings
6. **Configure networking bridges** using netplan (Ubuntu 24.04 default):
   - `br-mgmt` bridging the management interface (preserve existing IP)
   - `br-vxlan` bridging the overlay interface (preserve existing IP)
   - `br-storage` bridging the storage interface (preserve existing IP)
   - `br-vlan` bridging the provider interface (**no IP** — layer 2 only, used by OVN for external traffic)
7. **Remove 127.0.1.1 entries** from `/etc/hosts` (OSA requirement)
8. **Set short hostnames** (e.g., `cloud-4core` not FQDN)
9. **Configure LVM for Cinder** (cloud-eugene only): create PV and VG `cinder-volumes` on `/dev/sde`
10. **Configure Nova ephemeral storage** on compute nodes:
    - cloud-6core: `/dev/sdb` (931.5G HDD) — format and mount as Nova instances local disk
    - cloud-eugene: `/dev/sda` (931.5G HDD) — format and mount as Nova instances local disk
    - cloud-celeron: `/dev/sda` (465.8G HDD) — format and mount as Nova instances local disk
    - Mount point: `/var/lib/nova/instances` (where Nova stores instance ephemeral disks)
11. **Reboot** if kernel was upgraded or new modules loaded

### Phase 2: Prepare the deployment host (this workstation)

Playbook: `playbooks/prepare_deployment_host.yml`
Runs against: localhost

Tasks:

1. **Install deployment packages:** `build-essential`, `git`, `python3-dev`, `sudo`
2. **Clone OSA:** `git clone -b stable/2025.2 https://opendev.org/openstack/openstack-ansible /opt/openstack-ansible`
3. **Run OSA bootstrap:** `/opt/openstack-ansible/scripts/bootstrap-ansible.sh`
4. **Copy OSA example configs:** `cp -a /opt/openstack-ansible/etc/openstack_deploy /etc/openstack_deploy`

### Phase 3: Deploy OSA configuration (on this workstation)

Playbook: `playbooks/deploy_osa_config.yml`
Runs against: localhost
Templates stored in: `playbooks/templates/openstack_deploy/`

Tasks:

1. **Deploy `openstack_user_config.yml`** — defines the environment layout:
   - `cidr_networks` for management (192.168.50.0/24), tunnel (192.168.60.0/24), storage (192.168.70.0/24)
   - `used_ips` to reserve gateway/workstation IPs
   - `provider_networks`: br-mgmt (raw), br-vxlan (geneve, range 1:1000), br-vlan (flat, physnet1), br-storage (raw)
   - Host assignments for all OSA groups (`shared_infra_hosts`, `repo_infra_hosts`, `identity_hosts`, `dashboard_hosts`, `compute_hosts`, `network_infra_hosts`, `network_northd_hosts`, `network_gateway_hosts`, `storage_hosts`, etc.)
2. **Deploy `user_variables.yml`** — global overrides:
   - `neutron_plugin_type: ml2.ovn`
   - `neutron_ml2_drivers_type: "geneve,flat"`
   - Self-service networking: `neutron_provider_networks` with geneve overlay and flat external
   - `haproxy_keepalived_external_vip_cidr` and internal VIP both set to 192.168.50.168 (cloud-4core mgmt IP)
   - Glance storage backend (local disk on cloud-4core, `/dev/sda` 128G SSD, accessed via storage network)
   - Cinder LVM backend pointing at `cinder-volumes` VG on cloud-eugene
   - Nova CPU allocation ratio (overcommit settings — useful for home lab)
   - Swift configuration (cloud-eugene rings on `/dev/sdc`, `/dev/sdd`)
   - SSL: self-signed certificates (OSA's built-in PKI — HAProxy generates a self-signed CA and issues certs)
   - `install_method: source` (default, more flexible)
3. **Generate secrets:** Run `pw-token-gen.py` to populate `/etc/openstack_deploy/user_secrets.yml`
4. **Deploy `env.d/` overrides** if needed (e.g., cinder-volume on metal for LVM)
5. **Deploy Swift ring configuration** (`conf.d/swift.yml`)
6. **Validate config:** Run `openstack-ansible openstack.osa.setup_infrastructure --syntax-check`

### Phase 4: Run OSA deployment (from this workstation)

Playbook: `playbooks/run_osa_deploy.yml`
Runs against: localhost (calls OSA playbooks which target the cloud nodes)

OSA playbooks run in sequence from the deployment host (this workstation):

1. **`openstack-ansible openstack.osa.setup_hosts`** — prepares target hosts, creates LXC containers
2. **`openstack-ansible openstack.osa.setup_infrastructure`** — installs galera, rabbitmq, memcached, repo server
3. **Verify galera cluster** — `ansible galera_container -m shell -a "mariadb -h localhost -e 'show status like \"%wsrep_cluster_%\";'"`
4. **`openstack-ansible openstack.osa.setup_openstack`** — installs keystone, glance, cinder, nova, neutron, horizon, swift

**Expected duration:** Several hours for the full deployment.

### Phase 5: Post-deployment verification

Playbook: `playbooks/verify_openstack.yml`

1. Access the utility container on cloud-4core and source `openrc`
2. Run `openstack service list` — verify all services registered
3. Run `openstack compute service list` — verify nova-compute on all three compute nodes
4. Run `openstack network agent list` — verify OVN agents
5. Create test resources: network, subnet, router, security group, flavor, image (cirros), instance
6. Verify instance boots, gets IP, is reachable

### Phase 6 — Observability (Loki + Prometheus + Grafana)

**Goal:** Centralized logging and metrics for all cluster nodes and LXC containers, queryable from a single Grafana instance on cloud-4core.

**Current state:** Logs are scattered across cloud-4core's 16 LXC containers (`/var/log/nova/`, `/var/log/neutron/`, etc.), plus HAProxy / host syslog on each node, and nova-compute / OVN / OVS logs on the three compute nodes.

#### Observability Architecture

All components run on **cloud-4core** (infrastructure node). Promtail and node_exporter run on every node.

```bash
┌─────────────────────────────────────────────────────────┐
│  cloud-4core (infrastructure)                           │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────────┐  │
│  │ Grafana  │  │ Loki       │  │ Prometheus          │  │
│  │ :3000    │  │ :3100      │  │ :9090               │  │
│  └──────────┘  └────────────┘  └─────────────────────┘  │
│  ┌──────────┐                   ┌─────────────────────┐ │
│  │ Promtail │                   │ node_exporter :9100 │ │
│  └──────────┘                   └─────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│  cloud-6core, cloud-celeron, cloud-eugene (compute)     │
│  ┌──────────┐                   ┌─────────────────────┐ │
│  │ Promtail │                   │ node_exporter :9100 │ │
│  └──────────┘                   └─────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- **Promtail** → tails log files, ships to Loki over mgmt network (192.168.50.x)
- **node_exporter** → exposes host metrics, scraped by Prometheus over mgmt network
- **Grafana** → single pane of glass, queries both Loki and Prometheus as data sources
- All traffic stays on the management network; no provider/overlay exposure needed

#### Tier 1: Centralized Logging — Loki + Promtail + Grafana

**Loki** (cloud-4core):

- Install via APT or official binary (single-binary mode, filesystem storage)
- Data dir: `/var/lib/loki/` — stored on cloud-4core's 128G SSD
- Listen: `192.168.50.168:3100` (mgmt network)
- Retention: 30 days (sufficient for home lab)

**Promtail** (all 4 nodes):

- Install via official binary, run as systemd service
- Scrape targets per node:
  - cloud-4core host: `/var/log/syslog`, `/var/log/haproxy.log`
  - cloud-4core LXC containers: `/var/lib/lxc/*/rootfs/var/log/**/*.log` (bind-mount or glob from host)
  - Compute nodes: `/var/log/syslog`, `/var/log/nova/`, `/var/log/openvswitch/`, `/var/log/ovn/`
- Labels: `{host="cloud-4core", service="nova-api", container="cloud-4core-nova-api-container-xxx"}`
- Push to: `http://192.168.50.168:3100/loki/api/v1/push`

**Grafana** (cloud-4core):

- Install via APT (official Grafana repo)
- Listen: `192.168.50.168:3000`
- Add Loki as data source (URL: `http://localhost:3100`)
- Import community dashboards for OpenStack log exploration

#### Tier 2: Metrics & Monitoring — Prometheus + Grafana

**node_exporter** (all 4 nodes):

- Install via official binary, run as systemd service
- Listen: `<mgmt-ip>:9100`
- Exposes: CPU, RAM, disk, network, filesystem metrics

**Prometheus** (cloud-4core):

- Install via official binary, run as systemd service
- Data dir: `/var/lib/prometheus/` — on cloud-4core SSD
- Listen: `192.168.50.168:9090`
- Retention: 30 days
- Scrape config (`prometheus.yml`):

```yaml
scrape_configs:
  - job_name: node
    static_configs:
      - targets:
          - 192.168.50.168:9100  # cloud-4core
          - 192.168.50.161:9100  # cloud-6core
          - 192.168.50.162:9100  # cloud-celeron
          - 192.168.50.163:9100  # cloud-eugene
  - job_name: haproxy
    static_configs:
      - targets:
          - 192.168.50.168:8404  # HAProxy stats
```

- Future: add OpenStack API exporters, OVN/OVS exporters as needed

**Grafana** (same instance as Tier 1):

- Add Prometheus as data source (URL: `http://localhost:9090`)
- Import Node Exporter Full dashboard (Grafana ID 1860)
- Import HAProxy dashboard if stats endpoint is enabled

#### Observability Implementation Plan

| Step | Task | Target |
|------|------|--------|
| 1 | Create `playbooks/roles/deploy_monitoring/` role | Repo |
| 2 | Install Loki (binary) + systemd unit on cloud-4core | cloud-4core |
| 3 | Install Promtail (binary) + systemd unit + config on all nodes | All nodes |
| 4 | Verify logs flowing: `curl -s http://192.168.50.168:3100/ready` | cloud-4core |
| 5 | Install Prometheus (binary) + systemd unit + scrape config on cloud-4core | cloud-4core |
| 6 | Install node_exporter (binary) + systemd unit on all nodes | All nodes |
| 7 | Verify metrics: `curl -s http://192.168.50.168:9090/api/v1/targets` | cloud-4core |
| 8 | Install Grafana (APT) on cloud-4core | cloud-4core |
| 9 | Provision Loki + Prometheus data sources via Grafana provisioning YAML | cloud-4core |
| 10 | Import dashboards (Node Exporter Full, log explorer) | cloud-4core |
| 11 | Smoke test: query logs in Grafana, check node metrics graphs | Grafana UI |

#### Observability Versions (pinned)

- Loki: 3.4.x (latest stable)
- Promtail: 3.4.x (matches Loki)
- Prometheus: 3.x (latest stable)
- node_exporter: 1.9.x
- Grafana: 11.x (OSS, APT repo)

All components are open source (AGPLv3 for Loki/Grafana, Apache 2.0 for Prometheus/node_exporter).

| File                    | Purpose                                                      |
| ----------------------- | ------------------------------------------------------------ |
| defaults/main.yml       | Pinned versions (node_exporter 1.9.0, Promtail/Loki 3.4.2, Prometheus 3.2.1), ports, paths, retention |
| tasks/main.yml          | Entrypoint — includes per-component tasks, gates Loki/Prometheus/Grafana on `is_controller` |
| tasks/node_exporter.yml | Downloads binary, creates user, installs systemd unit — all nodes |
| tasks/promtail.yml      | Downloads binary, deploys config with per-role scrape targets — all nodes |
| tasks/loki.yml          | Downloads binary, TSDB+filesystem storage, 30-day retention — controller only |
| tasks/prometheus.yml    | Downloads binary, scrapes all 4 node_exporters — controller only |
| tasks/grafana.yml       | APT install from official repo, auto-provisions Loki+Prometheus datasources — controller only |
| handlers/main.yml       | Restart handlers for all 5 services                          |
| templates/              | systemd units, Loki/Prometheus/Promtail configs, Grafana datasource provisioning |

Playbook — deploy_monitoring.yml: Runs the role against all hosts, then verifies each service is healthy.

Promtail scrape targets are role-aware:

- Controller (cloud-4core): syslog, journal, HAProxy log, LXC container logs (`/var/lib/lxc/*/rootfs/var/log/**/*.log`)
- Compute nodes: syslog, journal, nova-compute, OVN, and OVS logs

To deploy:

```bash
ansible-playbook playbooks/deploy_monitoring.yml
```

### Phase 7 — Install Barbican Key Manager

**Goal:** Deploy the OpenStack Key Manager service (Barbican) for secret storage — encryption keys, certificates, passphrases. This is a prerequisite for Nova volume encryption, Cinder encrypted volumes, and Magnum (which stores cluster TLS certs in Barbican).

**Current state:** Barbican secrets already generated in `/etc/openstack_deploy/user_secrets.yml` (from `pw-token-gen.py`). The `barbican.yml` env.d mapping and HAProxy service definition ship with OSA. No `key-manager_hosts` entry exists in `openstack_user_config.yml` yet.

#### Barbican Architecture

Barbican runs in an LXC container on cloud-4core (same as all other API services). It uses the **simple crypto** plugin — a symmetric key stored in `barbican.conf` that encrypts secrets at rest in the Galera database. This is appropriate for a home lab; production would use an HSM backend (PKCS#11 or Vault).

```bash
┌─────────────────────────────────────────────┐
│  cloud-4core                                │
│  ┌──────────────────────────────────────┐   │
│  │ barbican-api container               │   │
│  │  barbican-api (WSGI) :9311           │   │
│  │  barbican-keystone-listener          │   │
│  │  barbican-worker                     │   │
│  │  secret store: simple_crypto         │   │
│  └──────────────────────────────────────┘   │
│  HAProxy :9311 → barbican container :9311   │
└─────────────────────────────────────────────┘
```

- **API** listens on port 9311, fronted by HAProxy with SSL termination
- **simple_crypto KEK** already generated in `user_secrets.yml` as `barbican_simple_crypto_key`
- Keystone endpoint registered automatically by the OSA role

#### Implementation Steps

**Step 1 — Add `key-manager_hosts` to `openstack_user_config.yml.j2`**

Add alongside the other host group definitions (after `coordination_hosts`):

```yaml
key-manager_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

This tells OSA to create a `barbican_container` LXC container on cloud-4core and assign it to the `barbican_api` / `barbican_all` groups (via the built-in `env.d/barbican.yml` mapping).

**Step 2 — Deploy updated config**

```bash
ansible-playbook playbooks/deploy_osa_config.yml --diff
```

Pushes the updated `openstack_user_config.yml` to `/etc/openstack_deploy/`.

**Step 3 — Run the Barbican install playbook**

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-barbican-install.yml
```

This will:

1. Create the `barbican_container` LXC on cloud-4core
2. Install Barbican from source (stable/2025.2)
3. Create the `barbican` Galera database and user
4. Register the `key-manager` service and endpoint in Keystone
5. Configure the simple_crypto secret store plugin
6. Deploy the HAProxy backend for port 9311
7. Start `barbican-api`, `barbican-worker`, and `barbican-keystone-listener`

**Step 4 — Verify**

```bash
# Check service is registered
openstack --os-cloud home-cloud service list | grep key-manager

# Check endpoint
openstack --os-cloud home-cloud endpoint list | grep barbican

# Store and retrieve a test secret
openstack --os-cloud home-cloud secret store \
  --name test-secret --payload "s3cret" \
  --payload-content-type text/plain

openstack --os-cloud home-cloud secret list
openstack --os-cloud home-cloud secret get <secret-href> --payload

# Clean up
openstack --os-cloud home-cloud secret delete <secret-href>
```

**Step 5 — Enable Nova/Cinder Barbican integration**

To allow encrypted volumes, add to `user_variables.yml.j2`:

```yaml
# Cinder — use Barbican for volume encryption keys
cinder_service_key_manager: barbican

# Nova — use Barbican for ephemeral disk encryption keys (if desired)
nova_service_key_manager: barbican
```

Then re-run the Cinder and Nova playbooks with config tags:

```bash
openstack-ansible playbooks/os-cinder-install.yml --tags cinder-config
openstack-ansible playbooks/os-nova-install.yml --tags nova-config
```

#### Manila What OSA handles automatically

- LXC container creation and networking
- Galera database and user
- RabbitMQ vhost and user
- Keystone service catalog registration (service type `key-manager`, port 9311)
- HAProxy frontend/backend on VIP port 9311 (SSL-terminated)
- `barbican.conf` with simple_crypto plugin and KEK from `user_secrets.yml`
- Systemd services for API, worker, and Keystone listener

#### No custom env.d or conf.d needed

Unlike Cinder (which needed a `env.d/cinder.yml` override for bare-metal LVM), Barbican runs entirely inside its LXC container with no host-level dependencies. The built-in `env.d/barbican.yml` mapping is sufficient.

### Phase 8 — Playbook for Openstack CLI on this workstation

- Install Openstack CLI on this workstation (it's already installed, just need to scaffold it IaC)
- Install python-heatclient (already installed, again just IaC)
- Install python-barbicanclient

### Phase 9 — Updates to Horizon

Need to make sure we install plugins to Horizon for all of the services we add that aren't default:

- openstack-dashboard-heat-partition
- barbican-ui

### Phase 10 — Manila Shared File Systems service

**Goal:** Deploy the OpenStack Shared File Systems service (Manila) so tenants can create and manage NFS shares. Uses an LVM backend on cloud-4core with NFS exports — similar in spirit to how Cinder uses LVM+iSCSI for block storage.

**Current state:** `/dev/sdb` (931.5G HDD) on cloud-4core is unused, already formatted with XFS, not mounted, not an LVM PV. Manila secrets already generated in `user_secrets.yml`. The `manila.yml` env.d mapping ships with OSA.

#### Manila Architecture

Manila has a split architecture in OSA:

- **manila-infra** (LXC container on cloud-4core): runs `manila-api` and `manila-scheduler`
- **manila-data** (bare metal on cloud-4core): runs `manila-share` and `manila-data` — needs direct access to the LVM VG and NFS exports

The LVM share driver creates logical volumes on `manila-shares` VG and exports them as NFS shares. `driver_handles_share_servers: False` means Manila doesn't spin up share server VMs — the NFS server runs directly on cloud-4core.

```bash
┌─────────────────────────────────────────────────────┐
│  cloud-4core                                        │
│  ┌──────────────────────────────────────────────┐   │
│  │ manila-api container (LXC)                   │   │
│  │  manila-api (WSGI) :8786                     │   │
│  │  manila-scheduler                            │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  manila-share (bare metal)                          │
│  manila-data (bare metal)                           │
│  ┌──────────────────────────────────────────────┐   │
│  │ /dev/sdb → PV → VG "manila-shares"           │   │
│  │ LVM driver creates LVs → formats XFS         │   │
│  │ NFS server exports each LV as a share        │   │
│  └──────────────────────────────────────────────┘   │
│  HAProxy :8786 → manila-api container :8786         │
└─────────────────────────────────────────────────────┘
```

- **API** on port 8786, fronted by HAProxy with SSL termination
- **Storage**: LVM logical volumes on the `manila-shares` VG, formatted and exported via NFS
- **Export IP**: `192.168.50.168` (cloud-4core management IP) — tenants mount shares from this IP
- Keystone endpoint registered automatically by the OSA role

#### Manila Implementation Steps

**Step 1 — Prepare /dev/sdb for LVM**

The disk is currently formatted with XFS as a whole-disk filesystem. We need to wipe it and create an LVM PV and VG:

```bash
ssh cloud-4core
sudo wipefs -a /dev/sdb        # Remove existing XFS signature
sudo pvcreate /dev/sdb
sudo vgcreate manila-shares /dev/sdb
sudo vgs manila-shares          # Verify: ~931G free
```

**Step 2 — Add Manila hosts to `openstack_user_config.yml.j2`**

Add after `key-manager_hosts`:

```yaml
# Manila Shared File Systems — API/scheduler in LXC, share/data on bare metal
manila-infra_hosts:
  cloud-4core:
    ip: 192.168.50.168

manila-data_hosts:
  cloud-4core:
    ip: 192.168.50.168
    container_vars:
      manila_default_share_type: nfs-share1
      manila_enabled_share_protocols: NFS
      manila_backends:
        nfs-share1:
          share_backend_name: NFS_SHARE1
          share_driver: manila.share.drivers.lvm.LVMShareDriver
          driver_handles_share_servers: False
          lvm_share_volume_group: manila-shares
          lvm_share_export_ips: 192.168.50.168
```

**Step 3 — Deploy updated config**

```bash
ansible-playbook playbooks/deploy_osa_config.yml --diff
```

**Step 4 — Create the Manila container and run the install playbook**

```bash
cd /opt/openstack-ansible
# Create the Manila LXC container first
openstack-ansible playbooks/lxc-containers-create.yml --limit manila_all
# Install Manila
openstack-ansible playbooks/os-manila-install.yml
```

This will:

1. Create the `manila_container` LXC on cloud-4core (API + scheduler)
2. Install manila-share and manila-data on cloud-4core bare metal
3. Install NFS server packages on cloud-4core
4. Create the `manila` Galera database and user
5. Register the `shared-file-system` service and endpoint in Keystone
6. Configure the LVM NFS backend
7. Deploy the HAProxy backend for port 8786
8. Start all services

**Step 5 — Re-run Horizon install (for manila-ui)**

Horizon auto-enables `manila-ui` when `manila_all` group exists — no variable needed:

```bash
openstack-ansible playbooks/os-horizon-install.yml
```

**Step 6 — Add python-manilaclient to CLI playbook**

Add `python-manilaclient` to `openstack_cli_packages` in `playbooks/setup_openstack_cli.yml`, then run:

```bash
ansible-playbook playbooks/setup_openstack_cli.yml
```

**Step 7 — Verify**

```bash
# Check service is registered
openstack --os-cloud home-cloud service list | grep shared-file-system

# Check endpoint
openstack --os-cloud home-cloud endpoint list | grep manila

# Create a share type (admin)
openstack --os-cloud home-cloud share type create nfs-share1 False \
  --extra-specs share_backend_name=NFS_SHARE1

# Create a test share
openstack --os-cloud home-cloud share create NFS 1 --name test-share

# Wait for status "available"
openstack --os-cloud home-cloud share show test-share

# Grant access (allow an IP to mount)
openstack --os-cloud home-cloud share access create test-share ip 192.168.50.0/24

# Get export path
openstack --os-cloud home-cloud share export location list test-share

# Test mount from a node (e.g. cloud-6core):
#   sudo mount -t nfs 192.168.50.168:/path/to/export /mnt/test
#   echo "hello" | sudo tee /mnt/test/hello.txt
#   sudo umount /mnt/test

# Clean up
openstack --os-cloud home-cloud share access delete test-share <access-id>
openstack --os-cloud home-cloud share delete test-share
```

#### What OSA handles automatically for Manila

- LXC container creation and networking for API/scheduler
- Bare-metal service installation for share/data
- NFS server installation (`nfs-kernel-server`) on the data host
- Galera database and user
- RabbitMQ vhost and user
- Keystone service catalog registration (service type `shared-file-system`, port 8786)
- HAProxy frontend/backend on VIP port 8786 (SSL-terminated)
- Horizon plugin auto-enablement when `manila_all` group exists

#### No custom env.d needed

The built-in `env.d/manila.yml` mapping handles the split architecture: API/scheduler in LXC (`manila_container`), share/data on bare metal (`manila_data_container` with `is_metal: true`). No override needed.

#### Key differences from Cinder LVM

| | Cinder LVM | Manila LVM |
|---|---|---|
| **Protocol** | iSCSI (block) | NFS (file) |
| **Host** | cloud-eugene | cloud-4core |
| **Disk** | `/dev/sde` (476G SSD) | `/dev/sdb` (931G HDD) |
| **VG name** | `cinder-volumes` | `manila-shares` |
| **Container** | Bare metal (env.d override) | Bare metal (built-in env.d) |
| **Client mounts** | Nova attaches via iSCSI | Tenant mounts via NFS |

### Phase 11 — Designate DNS Service

**Goal:** Deploy the OpenStack DNS-as-a-Service (Designate) so tenants can create and manage DNS zones and records via the API, and optionally auto-create DNS records when Nova instances or Neutron ports are created. Uses BIND9 as the backend nameserver inside the Designate LXC container on cloud-4core.

**Current state:** Designate secrets already generated in `/etc/openstack_deploy/user_secrets.yml` (`designate_galera_password`, `designate_oslomsg_rpc_password`, `designate_service_password`, `designate_pool_uuid`). The `env.d/designate.yml` mapping and HAProxy service definitions ship with OSA. No `dnsaas_hosts` entry exists in `openstack_user_config.yml` yet.

**References:** [install guide](https://docs.openstack.org/designate/2025.1/install/) · [user guide](https://docs.openstack.org/designate/2025.1/user/) · [dashboard](https://opendev.org/openstack/designate-dashboard)

#### Designate Architecture

All Designate services run in a single LXC container on cloud-4core. BIND9 also runs inside that container as the DNS backend, managed by Designate via `rndc`.

```bash
┌──────────────────────────────────────────────────────────┐
│  cloud-4core                                             │
│  ┌────────────────────────────────────────────────────┐  │
│  │ designate_container (LXC)                          │  │
│  │                                                    │  │
│  │  designate-api       :9001  (REST API)             │  │
│  │  designate-central          (zone/record logic)    │  │
│  │  designate-worker           (async tasks)          │  │
│  │  designate-producer         (periodic tasks)       │  │
│  │  designate-mdns      :5354  (zone transfers)       │  │
│  │  designate-sink             (notification listener)│  │
│  │                                                    │  │
│  │  BIND9 (named)       :53   (authoritative DNS)     │  │
│  │  rndc                :953  (BIND9 control channel) │  │
│  └────────────────────────────────────────────────────┘  │
│  HAProxy :9001 → designate container :9001               │
└──────────────────────────────────────────────────────────┘
```

- **designate-api** listens on port 9001, fronted by HAProxy with SSL termination
- **designate-mdns** (mini-DNS) handles AXFR zone transfers to BIND9 on port 5354
- **designate-worker** sends rndc commands to BIND9 to create/delete zones
- **designate-sink** listens for Nova/Neutron notifications to auto-create DNS records
- **BIND9** is the authoritative nameserver — Designate manages its zones via rndc
- Keystone endpoint registered as service type `dns`
- Coordination via Zookeeper (already deployed for other services)

#### How it works

1. Tenant creates a zone via API: `openstack zone create --email admin@home.cloud home.cloud.`
2. Designate stores the zone in Galera and tells designate-worker to provision it
3. Worker sends an rndc command to BIND9 to create the zone, then designate-mdns does an AXFR transfer of records
4. Tenant creates records: `openstack recordset create home.cloud. --type A --records 192.168.2.100 myvm`
5. BIND9 serves the records authoritatively on port 53

#### DNS Backend: BIND9

BIND9 is the simplest backend for a single-node deployment. It runs inside the Designate container, so no additional hosts or network access are needed. The OSA role:

- Installs `bind9utils` (for the `rndc` CLI) when `designate_rndc_keys` is defined
- Creates the rndc key file from the secret we provide
- Configures `pools.yaml` with the BIND9 target

**We must install BIND9 (`bind9` package) ourselves** inside the container — the OSA role only installs `bind9utils`, not the server. This is a one-time step after container creation.

#### Designate Implementation Steps

**Step 1 — Add `dnsaas_hosts` to `openstack_user_config.yml.j2`**

Add after `manila-data_hosts`:

```yaml
# Designate DNS-as-a-Service — all services in LXC
dnsaas_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

This tells OSA to create a `designate_container` LXC on cloud-4core and assign it to all `designate_*` groups (via the built-in `env.d/designate.yml` mapping).

**Step 2 — Add Designate pool and rndc configuration to `user_variables.yml.j2`**

```yaml
# ============================================================================
# Designate (DNS)
# ============================================================================
# BIND9 pool configuration — single nameserver in the Designate container
designate_pools_yaml:
  - name: "default"
    description: "Default BIND9 Pool"
    attributes: {}
    ns_records:
      - hostname: "ns1.home.cloud."
        priority: 1
    nameservers:
      - host: 127.0.0.1
        port: 53
    targets:
      - type: bind9
        description: "BIND9 on cloud-4core"
        masters:
          - host: 127.0.0.1
            port: 5354
        options:
          host: 127.0.0.1
          port: 53
          rndc_host: 127.0.0.1
          rndc_port: 953
          rndc_key_file: /etc/designate/rndc.key

# rndc key for BIND9 authentication — generated once, stored here
# Generate with: rndc-confgen -a -A hmac-sha256 | grep secret
designate_rndc_keys:
  - name: "rndc-key"
    file: /etc/designate/rndc.key
    algorithm: "hmac-sha256"
    secret: "<generate-and-paste-here>"

# Neutron DNS integration — auto-create records for instances/ports
neutron_plugin_base:
  - router
  - dns
neutron_dns_domain: "home.cloud."
```

**Note on `neutron_plugin_base`:** OSA's default for OVN is `[router]`. Adding `dns` enables the ML2 DNS extension driver, which adds `dns_name` and `dns_domain` attributes to ports/networks. Combined with `neutron_designate_enabled` (auto-set when `designate_all` group exists), Neutron will call Designate to create A records when instances are created on networks with a `dns_domain` set.

**Step 3 — Deploy updated config**

```bash
ansible-playbook playbooks/deploy_osa_config.yml --diff
```

**Step 4 — Create the Designate container**

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/lxc-containers-create.yml --limit designate_all
```

**Step 5 — Install BIND9 inside the Designate container**

The OSA role only installs `bind9utils` (the rndc CLI), not the BIND9 server. Install it manually after container creation:

```bash
# Find the container name
ssh cloud-4core "sudo lxc-ls | grep designate"

# Install and configure BIND9
ssh cloud-4core "sudo lxc-attach -n <designate-container> -- bash -c '
  apt-get update && apt-get install -y bind9
  # Enable dynamic zones (required by Designate worker)
  cat >> /etc/bind/named.conf.options <<EOF

  // Allow Designate to manage zones via rndc
  allow-new-zones yes;
EOF
  systemctl enable named
  systemctl restart named
'"
```

Alternatively, this could be codified in `run_osa_deploy.yml` as a post-deploy task (similar to the lxc-net fix).

**Step 6 — Generate the rndc key**

```bash
# Generate an rndc key
ssh cloud-4core "sudo lxc-attach -n <designate-container> -- bash -c '
  rndc-confgen -a -A hmac-sha256 -k rndc-key
  cat /etc/bind/rndc.key
'"
```

Copy the `secret` value from the output into `designate_rndc_keys[0].secret` in `user_variables.yml.j2`, then re-deploy config:

```bash
ansible-playbook playbooks/deploy_osa_config.yml --diff
```

**Step 7 — Run the Designate install playbook**

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-designate-install.yml
```

This will:

1. Create the `designate` Galera database and user
2. Create the RabbitMQ vhost and user
3. Install Designate from source (stable/2025.2) in a venv
4. Deploy `designate.conf` with BIND9 backend config
5. Create the rndc key file at `/etc/designate/rndc.key`
6. Deploy `pools.yaml` and run `designate-manage pool update`
7. Register the `dns` service and endpoints in Keystone
8. Configure HAProxy backend for port 9001
9. Start all 6 Designate services (api, central, worker, mdns, producer, sink)

**Step 8 — Configure BIND9 to accept rndc commands from Designate**

After the OSA playbook creates the rndc key file, configure BIND9 to use it:

```bash
ssh cloud-4core "sudo lxc-attach -n <designate-container> -- bash -c '
  # Copy the Designate-managed rndc key to BIND
  cp /etc/designate/rndc.key /etc/bind/rndc.key
  chown bind:bind /etc/bind/rndc.key

  # Add rndc controls to named.conf if not present
  if ! grep -q \"controls\" /etc/bind/named.conf.local; then
    cat >> /etc/bind/named.conf.local <<EOF

include \"/etc/bind/rndc.key\";
controls {
  inet 127.0.0.1 port 953 allow { localhost; } keys { \"rndc-key\"; };
};
EOF
  fi

  systemctl restart named

  # Verify rndc works
  rndc -k /etc/designate/rndc.key status
'"
```

**Step 9 — Re-run Horizon install (for designate-dashboard)**

Horizon auto-enables `designate-dashboard` when `designate_all` group exists (via `horizon_enable_designate_ui` default). No explicit variable needed:

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-horizon-install.yml
```

**Step 10 — Re-run Neutron install (for DNS integration)**

If Neutron DNS integration is desired (auto-creating records for instances), re-run Neutron to pick up the `dns` extension driver and `[designate]` config section:

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-neutron-install.yml
```

**Step 11 — Add python-designateclient to CLI playbook**

Add `python-designateclient` to the packages list in `playbooks/setup_openstack_cli.yml`, then run:

```bash
ansible-playbook playbooks/setup_openstack_cli.yml
```

**Step 12 — Verify**

```bash
# Check service is registered
openstack --os-cloud home-cloud service list | grep dns

# Check endpoint
openstack --os-cloud home-cloud endpoint list | grep designate

# Create a test zone
openstack --os-cloud home-cloud zone create --email admin@home.cloud home.cloud.

# Wait for zone to become ACTIVE
openstack --os-cloud home-cloud zone show home.cloud.

# Create an A record
openstack --os-cloud home-cloud recordset create home.cloud. \
  --type A --records 192.168.2.100 testvm

# Verify record exists
openstack --os-cloud home-cloud recordset list home.cloud.

# Test DNS resolution from the Designate container
ssh cloud-4core "sudo lxc-attach -n <designate-container> -- \
  dig @127.0.0.1 testvm.home.cloud. A +short"
# Expected: 192.168.2.100

# Test Neutron integration (if enabled):
# Create a network with dns_domain
openstack --os-cloud home-cloud network set test-net --dns-domain home.cloud.

# Launch an instance — should auto-create an A record
# openstack --os-cloud home-cloud server create --nic net-id=test-net ...

# Clean up
openstack --os-cloud home-cloud recordset delete home.cloud. testvm.home.cloud.
openstack --os-cloud home-cloud zone delete home.cloud.
```

#### Designate What OSA handles automatically

- LXC container creation and networking
- Galera database and user
- RabbitMQ vhost and user
- Keystone service catalog registration (service type `dns`, port 9001)
- HAProxy frontend/backend on VIP port 9001 (SSL-terminated)
- `designate.conf` with pool config, rndc key path, Zookeeper coordination
- `pools.yaml` deployment and `designate-manage pool update`
- Systemd services for all 6 Designate processes
- Horizon plugin auto-enablement (`designate-dashboard`)
- Neutron `[designate]` config section and `external_dns_driver = designate` (when `designate_all` group exists)

#### Designate What we must handle manually

- **BIND9 server installation** inside the container (`apt-get install bind9`) — OSA only installs `bind9utils`
- **BIND9 `named.conf` configuration** — `allow-new-zones yes`, rndc controls, key include
- **rndc key generation** — `rndc-confgen -a -A hmac-sha256` → paste secret into `user_variables.yml.j2`
- **Neutron re-run** if DNS integration is desired (to pick up `dns` extension driver)

#### Designate No custom env.d needed

The built-in `env.d/designate.yml` mapping handles everything: all 6 services run inside a single `designate_container` LXC. No bare-metal components needed (unlike Manila or Cinder LVM).

#### Choosing a DNS domain

The zone name (`home.cloud.` in the examples above) is arbitrary. Options:

- **`home.cloud.`** — short, memorable, private-use. Not a real TLD, so no conflict risk.
- **`openstack.local.`** — explicit about scope, but `.local` is reserved for mDNS (may cause resolution issues on some clients).
- **A subdomain of a real domain you own** — e.g., `cloud.example.com.` — best practice if you want external resolution later.

The zone only needs to exist inside Designate's BIND9 — it doesn't need to be delegated from any parent zone for internal use. Clients that want to resolve these names just need to point at the Designate BIND9 (cloud-4core container IP) as their DNS server, or use a forwarding rule on the lab router.

```bash
export LC_ALL=en_US.UTF-8
export OS_ENDPOINT_TYPE=internalURL
export OS_INTERFACE=internalURL
export OS_USERNAME=admin
export OS_PASSWORD='8319c588aabc24268829e560427a0f33b08f3acb451'
export OS_PROJECT_NAME=admin
export OS_TENANT_NAME=admin
export OS_AUTH_TYPE=password
export OS_AUTH_URL=https://192.168.50.168:5000/v3
export OS_NO_CACHE=1
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_REGION_NAME=RegionOne
export OS_IDENTITY_API_VERSION=3
export OS_AUTH_VERSION=3
openstack zone list
```

### Phase 12 — (Trove) Database service

#### How Trove works

Trove is DBaaS — it doesn't share the infrastructure MariaDB (Galera) or install databases on the host. Instead, when a tenant creates a database instance, Trove:

1. Launches a **Nova VM** from a pre-built guest image (stored in Glance)
2. Attaches a **Cinder volume** for persistent data (if `volume_support=True`, which is the default)
3. Attaches two NICs: one on the **tenant network** (for database client access) and one on a **management network** (for guest agent ↔ RabbitMQ communication)
4. The guest agent inside the VM pulls a **Docker container image** for the requested database engine (MySQL, MariaDB, PostgreSQL, etc.) from Docker Hub or a private registry
5. The guest agent manages the database lifecycle (create/delete databases and users, backups, restores, configuration changes) via RPC over RabbitMQ

```bash
                          ┌──────────────────── cloud-4core (LXC) ────────────────────┐
                          │                                                            │
  Tenant / CLI ──HTTPS──▶│  HAProxy :8779 ──▶ trove-api                               │
                          │                      │                                     │
                          │                      ▼ (RPC)                               │
                          │               trove-conductor  ◄──status── ┐               │
                          │               trove-taskmanager ──launch──▶│               │
                          │                      │                     │               │
                          └──────────────────────┼─────────────────────┼───────────────┘
                                                 │                     │
                                 ┌───────────────┘                     │
                                 ▼                                     │
                    Nova creates VM on compute node                    │
                    ┌────────────────────────────────┐                 │
                    │  Trove Guest VM                 │                 │
                    │  ┌──────────────────────────┐  │                 │
                    │  │ trove-guestagent          │──┘ (RabbitMQ      │
                    │  │   └─▶ Docker: mysql:8.4   │     over mgmt     │
                    │  └──────────────────────────┘     network)       │
                    │  NIC1: tenant-net (DB clients)                   │
                    │  NIC2: mgmt-net (guest agent)                    │
                    │  Cinder volume: /var/lib/mysql                   │
                    └────────────────────────────────┘
```

#### Datastore support (2025.2 Flamingo)

The official Trove support matrix for 2025.2:

| Database   | Supported versions |
|------------|--------------------|
| MySQL      | 8.0, 8.4           |
| MariaDB    | 11.4, 11.8         |
| PostgreSQL | 16, 17             |

**Redis and MongoDB are NOT in the official 2025.2 support matrix.** Since Victoria, Trove runs databases as Docker containers inside guest VMs. The tested datastore managers are `mysql`, `mariadb`, and `postgresql`. Redis and MongoDB managers exist in the codebase but are unmaintained and untested in CI. Attempting them would require custom work and may break.

**Recommendation:** Deploy MySQL 8.4 and MariaDB 11.4 (or 11.8) as the initial datastores. PostgreSQL 16/17 can be added easily. Redis and MongoDB should be deferred unless you're willing to do significant manual work with no upstream support.

**Decision:** MariaDB and PostgreSQL only. Skip MySQL (MariaDB covers the same use cases). Deploy MariaDB 11.4 and PostgreSQL 17 as the initial datastores.

#### /dev/sdc usage — dedicated Cinder SSD backend (optional)

Since Trove stores database data on Cinder volumes, `/dev/sdc` (128 GB SSD on cloud-4core) can be configured as a **dedicated Cinder LVM backend** for fast database storage. This requires:

- Creating a VG (`trove-volumes`) on `/dev/sdc` on cloud-4core
- Adding cloud-4core as a second `storage_hosts` entry in `openstack_user_config.yml.j2`
- Defining a new Cinder volume type (e.g., `ssd-db`) and configuring Trove to use it via `cinder_volume_type`
- iSCSI traffic flows over `br-storage` from cloud-4core to compute nodes

**Alternative:** Skip /dev/sdc entirely and use the existing Cinder LVM backend on cloud-eugene (`/dev/sde`, HDD). Simpler, but slower storage. /dev/sdc can be reserved for future Zaqar or other uses.

**Decision:** Skip /dev/sdc — reserve it for Zaqar in a future phase. Use the existing Cinder LVM backend on cloud-eugene (`/dev/sde`) as the sole Cinder volume host for Trove database instances.

#### Management network design

Trove guest VMs need a Neutron network for management traffic (guest agent ↔ RabbitMQ). Options:

1. **Overlay network + router** (recommended for home lab): Create a Geneve-backed Neutron network (`dbaas_mgmt_net`, e.g., 172.29.252.0/24) and a router connecting it to a network that can reach the RabbitMQ hosts (192.168.50.x). The router provides NAT/routing between the management subnet and the control plane. This isolates Trove VMs from the control plane.

2. **Provider flat network on br-mgmt**: Map a new physnet to `br-mgmt` and create a provider network directly on the management subnet. Simplest, but puts guest VMs on the control plane network. Acceptable for a home lab with no untrusted tenants.

The OSA role uses `trove_provider_net_name: dbaas-mgmt` to resolve RabbitMQ addresses for the guest agent config. A matching `provider_networks` entry with `net_name: dbaas-mgmt` must exist in `openstack_user_config.yml.j2`. For the overlay approach, this entry can reuse `br-mgmt` (the RabbitMQ containers are on that bridge), and the actual Neutron `management_networks` UUID is set separately.

**Decision:** Use the overlay network + OVN router approach. Create a Geneve-backed `dbaas-mgmt-net` (172.29.252.0/24) with an OVN logical router providing NAT/routing to the control plane (192.168.50.x) for guest-agent ↔ RabbitMQ traffic. This keeps Trove VMs isolated from the control plane network.

#### Implementation steps

**Step 1 — Add dbaas-mgmt provider network entry to openstack_user_config.yml.j2**

Add a provider network entry so OSA can resolve RabbitMQ addresses for the Trove guest agent config. This goes in `global_overrides.provider_networks`:

```yaml
    - network:
        container_bridge: "br-mgmt"
        container_type: "veth"
        container_interface: "eth13"
        ip_from_q: "management"
        type: "flat"
        net_name: "dbaas-mgmt"
        group_binds:
          - trove_api
```

**Step 2 — Add trove-infra_hosts to openstack_user_config.yml.j2**

```yaml
# Trove Database-as-a-Service — all services in LXC
trove-infra_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

**Step 3 — Skipped** (no dedicated SSD backend — /dev/sdc reserved for Zaqar)

Trove instances will use the existing Cinder LVM backend on cloud-eugene (`/dev/sde`).

**Step 4 — Add Trove variables to user_variables.yml.j2**

```yaml
# ============================================================================
# Trove (Database as a Service)
# ============================================================================
# Datastore definitions — MySQL 8.4 and MariaDB 11.4
trove_datastores:
  mariadb:
    - name: MariaDB
      versions:
        - name: "11.4"
          enabled: true
          version-number: "11.4"
          default: true
  postgresql:
    - name: PostgreSQL
      versions:
        - name: "17"
          enabled: true
          version-number: "17"
          default: true

# Horizon auto-enables trove-dashboard when trove_all group exists
```

**Step 5 — Deploy the updated OSA config**

```bash
ansible-playbook playbooks/deploy_osa_config.yml --diff
```

**Step 6 — Build the Trove guest image**

Build a single guest image (works for all datastores since Victoria). On the deployment host or cloud-4core:

```bash
git clone --branch stable/2025.2 https://opendev.org/openstack/trove /tmp/trove-build
cd /tmp/trove-build/integration/scripts

# Build for Ubuntu Jammy (officially supported), production mode
./trovestack build-image ubuntu jammy false ubuntu ~/images/trove-guest-ubuntu-jammy.qcow2
```

Register in Glance:

```bash
openstack --os-cloud home-cloud image create trove-guest-ubuntu-jammy \
  --private \
  --disk-format qcow2 --container-format bare \
  --property hw_rng_model='virtio' \
  --tag trove --tag mariadb --tag postgresql \
  --file ~/images/trove-guest-ubuntu-jammy.qcow2
```

> **Note:** Pre-built images may be available at `http://tarballs.openstack.org/trove/images/` for testing, but production deployments should use custom-built images.

**Step 7 — Run the Trove install playbook**

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-trove-install.yml
```

This will:

1. Create an LXC container on cloud-4core for Trove services
2. Create the `trove` Galera database and user
3. Create the RabbitMQ vhost and user (with secure RPC encryption keys)
4. Install Trove from source (stable/2025.2) in a venv
5. Deploy `trove.conf` and `trove-guestagent.conf`
6. Register the `database` service and endpoints in Keystone (port 8779)
7. Configure HAProxy backend for port 8779
8. Register datastores and versions (from `trove_datastores`)
9. Upload guest image to Glance (from `trove_guestagent_images` if configured)
10. Start trove-api (uWSGI), trove-conductor, trove-taskmanager

**Step 8 — Create the Trove management network**

Create a Neutron network for Trove management traffic. This is the network whose UUID goes into `management_networks` in trove.conf.

Option A — Overlay with router (recommended):

```bash
# Create management network (admin-only, not shared)
openstack --os-cloud home-cloud network create dbaas-mgmt-net \
  --provider-network-type geneve \
  --no-share

openstack --os-cloud home-cloud subnet create dbaas-mgmt-subnet \
  --network dbaas-mgmt-net \
  --subnet-range 172.29.252.0/24 \
  --no-dhcp  # Trove manages port creation directly

# Create a router to provide connectivity to RabbitMQ (on management network)
openstack --os-cloud home-cloud router create dbaas-router
openstack --os-cloud home-cloud router add subnet dbaas-router dbaas-mgmt-subnet
# Connect router to provider-net or external gateway so traffic can reach 192.168.50.x
openstack --os-cloud home-cloud router set dbaas-router --external-gateway provider-net
```

Then configure Trove to use this network:

```bash
MGMT_NET_ID=$(openstack --os-cloud home-cloud network show dbaas-mgmt-net -f value -c id)
# Update trove.conf: management_networks = $MGMT_NET_ID
# This can be done via trove_config_overrides in user_variables.yml.j2:
```

Add to `user_variables.yml.j2`:

```yaml
trove_config_overrides:
  DEFAULT:
    management_networks: "<MGMT_NET_UUID>"
```

Then re-run `os-trove-install.yml` to apply.

**Step 9 — Create management security group**

```bash
openstack --os-cloud home-cloud security group create trove-mgmt-sg \
  --project service \
  --description "Trove management port - allow egress only"

# Allow SSH from control plane (for troubleshooting, optional)
openstack --os-cloud home-cloud security group rule create trove-mgmt-sg \
  --protocol tcp --dst-port 22 --remote-ip 192.168.50.0/24

MGMT_SG_ID=$(openstack --os-cloud home-cloud security group show trove-mgmt-sg -f value -c id)
```

Add to `trove_config_overrides`:

```yaml
trove_config_overrides:
  DEFAULT:
    management_networks: "<MGMT_NET_UUID>"
    management_security_groups: "<MGMT_SG_UUID>"
```

**Step 10 — Re-run Horizon install (for trove-dashboard)**

Horizon auto-enables `trove-dashboard` when the `trove_all` group exists:

```bash
cd /opt/openstack-ansible
openstack-ansible playbooks/os-horizon-install.yml
```

**Step 11 — Add python-troveclient to CLI playbook**

Add `python-troveclient` to the packages list in `playbooks/setup_openstack_cli.yml`, then run:

```bash
ansible-playbook playbooks/setup_openstack_cli.yml
```

**Step 12 — Set Trove quotas for the service project**

Trove creates Nova VMs, Cinder volumes, and Neutron ports in the `service` project. Ensure it has sufficient quota:

```bash
openstack --os-cloud home-cloud quota set service \
  --instances 20 \
  --server-groups 20 \
  --volumes 20 \
  --secgroups 20 \
  --ports 40
```

**Step 13 — Verify**

```bash
# Check service is registered
openstack --os-cloud home-cloud service list | grep database

# Check endpoint
openstack --os-cloud home-cloud endpoint list | grep trove

# List datastores
openstack --os-cloud home-cloud datastore list
openstack --os-cloud home-cloud datastore version list MariaDB
openstack --os-cloud home-cloud datastore version list PostgreSQL

# Check guest image
openstack --os-cloud home-cloud image list --tag trove

# Create a test MariaDB instance
openstack --os-cloud home-cloud database instance create test-mariadb \
  --flavor m1.small \
  --size 5 \
  --datastore MariaDB --datastore-version 11.4 \
  --nic net-id=<tenant-network-id> \
  --databases testdb \
  --users testuser:password123

# Wait for ACTIVE status
openstack --os-cloud home-cloud database instance list
openstack --os-cloud home-cloud database instance show test-mariadb

# Verify database connectivity
openstack --os-cloud home-cloud database instance show test-mariadb -c ip
mariadb -h <instance-ip> -u testuser -p testdb

# Create a test PostgreSQL instance
openstack --os-cloud home-cloud database instance create test-pg \
  --flavor m1.small \
  --size 5 \
  --datastore PostgreSQL --datastore-version 17 \
  --nic net-id=<tenant-network-id> \
  --databases testdb \
  --users testuser:password123

# Verify PostgreSQL connectivity
openstack --os-cloud home-cloud database instance show test-pg -c ip
psql -h <instance-ip> -U testuser testdb

# List databases
openstack --os-cloud home-cloud database db list test-mariadb
openstack --os-cloud home-cloud database db list test-pg

# Clean up
openstack --os-cloud home-cloud database instance delete test-mariadb
openstack --os-cloud home-cloud database instance delete test-pg
```

#### Trove - What OSA handles automatically

- LXC container creation and networking
- Galera database (`trove`) and user
- RabbitMQ vhost and user (with per-service encryption keys)
- Keystone service catalog registration (service type `database`, port 8779)
- HAProxy frontend/backend on VIP port 8779 (SSL-terminated)
- `trove.conf` with database, messaging, Keystone auth, memcached, Cinder/Swift/Designate integration flags
- `trove-guestagent.conf` (injected into VMs at launch) with RabbitMQ addresses resolved from the `dbaas-mgmt` provider network interface
- Secure RPC messaging keys (auto-generated)
- Datastore and datastore version registration (from `trove_datastores`)
- Systemd services: trove-api (uWSGI), trove-conductor, trove-taskmanager
- Horizon plugin auto-enablement (`trove-dashboard`)

#### What we must handle manually

- **dbaas-mgmt provider network entry** in `openstack_user_config.yml.j2` — OSA needs this to resolve RabbitMQ addresses for guest agent config
- **Trove guest image** — build with `trovestack` and upload to Glance with appropriate tags
- **Management Neutron network** — create with `openstack network create` and set UUID in `trove_config_overrides`
- **Management security group** — create and set UUID in `trove_config_overrides`
- ~~**Cinder volume type**~~ — skipped, using existing LVM backend on cloud-eugene
- **Service project quotas** — ensure the `service` project can create enough VMs/volumes/ports
- **Routing/connectivity** — ensure the management network can reach RabbitMQ (via router or provider network)

#### No custom env.d needed

The built-in `env.d/trove.yml` mapping handles everything: trove-api, trove-conductor, and trove-taskmanager all run inside a single `trove_api_container` LXC on cloud-4core.

### Phase 13 — Octavia Load Balancer

Load-balancer service [(install guide)](https://docs.openstack.org/octavia/2025.1/install/) [(user guide)](https://docs.openstack.org/octavia/2025.1/user/) [(OSA role docs)](https://docs.openstack.org/openstack-ansible-os_octavia/2025.1/) [(OSA configure guide)](https://docs.openstack.org/openstack-ansible-os_octavia/2025.1/configure-octavia.html) [(dashboard)](https://opendev.org/openstack/octavia-dashboard) — `python-octaviaclient`, `octavia-dashboard`

#### What Octavia is

Octavia provides Load Balancing as a Service (LBaaS v2) for OpenStack. It deploys actual load balancer instances — **amphora** VMs — that run HAProxy inside a managed Ubuntu VM. Each load balancer is its own isolated instance. Octavia manages the full lifecycle: create, update listeners/pools/members, health monitoring, and delete.

Octavia supports two provider drivers:

| Provider | How it works | Capabilities |
|---|---|---|
| **Amphora** (default) | Spins up a Ubuntu VM running HAProxy per load balancer | Full L4/L7: HTTP/HTTPS, TLS termination, session persistence, health monitors, connection limits |
| **OVN** | Native OVN load balancer rules, no VM needed | L4 only (TCP/UDP). Lightweight, instant, no extra resources. |

Since we use **OVN** (`neutron_plugin_type: ml2.ovn`), the OVN provider is **auto-enabled**. Both providers will be available — users choose per load balancer.

#### OSA support status

OSA has **full Octavia support**:

| Component | Status |
|---|---|
| Ansible role | `os_octavia` at `opendev.org/openstack/openstack-ansible-os_octavia` |
| Playbook | `os-octavia-install.yml` |
| env.d | `octavia.yml` — single `octavia_server_container` LXC in `octavia-infra_containers` |
| Secrets | Pre-generated in `user_secrets.yml`: `octavia_cert_client_password`, `octavia_container_mysql_password`, `octavia_health_hmac_key`, `octavia_oslomsg_rpc_password`, `octavia_service_password` |
| HAProxy | Role includes haproxy service definitions for port 9876 |
| OVN integration | Auto-enabled when `neutron_plugin_type` is `ml2.ovn` |

#### Architecture for this cluster

```
                    ┌─────────── cloud-4core ────────────┐
                    │                                    │
  Tenant / CLI ──▶ │  HAProxy :9876                     │
                    │    └──▶ octavia_server_container   │
                    │           ├─ octavia-api (uWSGI)   │
                    │           ├─ octavia-worker         │
                    │           ├─ octavia-housekeeping   │
                    │           ├─ octavia-health-manager │
                    │           └─ octavia-driver-agent   │
                    │                  │              (OVN│
                    │     ┌────────────┤              drv)│
                    │     ▼            ▼                  │
                    │  Keystone    Galera/RabbitMQ        │
                    │  (existing)  (existing)             │
                    └────────────────────────────────────┘

  Amphora path:                    OVN path:
  octavia-worker ──▶ Nova VM       octavia-driver-agent ──▶ OVN NB DB
    (amphora: Ubuntu + HAProxy)      (native OVN LB rules, no VM)
```

All services run in a **single LXC container** on cloud-4core. The `octavia-driver-agent` handles the OVN provider (auto-enabled).

#### Dependencies

| Dependency | Status | Notes |
|---|---|---|
| Keystone | ✅ Deployed | Authentication, service accounts |
| Neutron (OVN) | ✅ Deployed | Amphora management network, OVN LB provider |
| Nova | ✅ Deployed | Amphora VM creation |
| Glance | ✅ Deployed | Amphora image storage |
| Barbican | ✅ Deployed | Optional TLS certificate storage |
| Zookeeper | ✅ Deployed | Coordination backend for amphorav2 jobboard |

#### Octavia services

| Service | Type | Purpose |
|---|---|---|
| `octavia-api` | uWSGI behind HAProxy | REST API, port 9876 |
| `octavia-worker` | systemd daemon | Creates/deletes amphora VMs, configures HAProxy |
| `octavia-housekeeping` | systemd daemon | Rotates amphora images, manages spare pool, DB cleanup |
| `octavia-health-manager` | systemd daemon | Receives heartbeats from amphora VMs, failover |
| `octavia-driver-agent` | systemd daemon | OVN provider driver (auto-enabled with ml2.ovn) |

#### Amphora management network

The amphora provider needs a **dedicated management network** (`lbaas`) for the Octavia control plane to communicate with amphora VMs:

- **Health heartbeats:** Amphora VMs send UDP heartbeats on port 5555 to `octavia-health-manager`
- **Configuration:** `octavia-worker` pushes HAProxy config to amphora VMs via REST on port 9443
- **Isolation:** This network is internal to the `service` project, not exposed to tenants

OSA expects this as a **provider network** (flat or VLAN) with a bridge on the controller:

1. A `br-lbaas` bridge on cloud-4core
2. A `provider_networks` entry in `openstack_user_config.yml.j2`
3. A `cidr_networks` entry for the IP pool
4. The role auto-creates the Neutron network, subnet, and security group

**Bridge implementation:** cloud-4core has no OVS and no spare physical NICs — all 4 are assigned to br-mgmt, br-vxlan, br-vlan, and br-storage. A flat `br-lbaas` with no physical uplink would be a dead-end bridge with no L2 path to compute nodes.

**Solution:** Use a **VLAN provider network** (ID 232) riding on the **storage bridge** (`br-storage`). The storage network uses an unmanaged hub, which passes VLAN-tagged frames without inspection. VLAN tagging is done entirely in software by the Linux kernel (no NIC or switch hardware support needed). On cloud-4core, a VLAN sub-interface (`br-storage.232`) is enslaved to `br-lbaas`, giving the Octavia LXC container L2 connectivity to amphora VMs on compute nodes. On compute nodes, OVN adds the `lbaas:br-storage` bridge mapping and handles VLAN tagging in OVS.

#### Amphora image

The role downloads a test amphora image by default:

- URL: `http://tarballs.openstack.org/octavia/test-images/test-only-amphora-x64-haproxy-ubuntu-noble.qcow2`
- `octavia_download_artefact: true` (default) — auto-downloads and uploads to Glance
- Tagged `octavia-amphora-image` in Glance

**Approach:** Use the test image initially to validate the full deployment (L7 LB creation, heartbeats, config push). Once amphora is confirmed working, build a custom image with `diskimage-builder` (Ubuntu Noble base, 10 GB disk, no FIPS). Ceilometer telemetry integration for amphora VMs is a future-phase concern.

#### Amphora compute resources

The role auto-creates:

- **Nova flavor:** `m1.amphora` — 1 vCPU, 1024MB RAM, 20GB disk
- **SSH keypair:** `octavia_key` (SSH disabled by default; enable with `octavia_ssh_enabled: true` for debugging)
- **Security group:** `octavia_sec_grp` with rules for agent (TCP 9443), heartbeat (UDP 5555), ICMP

#### Certificates

Octavia uses mutual TLS between the control plane and amphora VMs. The role auto-generates self-signed certificates:

- **Server CA** (`OctaviaServerRoot`) — signs amphora server certificates
- **Client CA** (`OctaviaClientRoot`) — signs control plane client certificates
- **OVN certificates** — for SSL communication with OVN NB/SB databases

No manual certificate setup is needed — `octavia_generate_certs: true` (default).

#### IaC changes needed

1. **`openstack_user_config.yml.j2`** — add lbaas network and host group:

   In `cidr_networks`:
   ```yaml
   lbaas: 172.29.232.0/22
   ```

   In `used_ips`:
   ```yaml
   # Octavia lbaas management network
   - "172.29.232.0,172.29.232.9"
   ```

   In `provider_networks`:
   ```yaml
   # Octavia amphora management network — VLAN 232 on the storage bridge.
   # cloud-4core has no OVS; a Linux br-lbaas with VLAN sub-interface
   # (br-storage.232) provides L2 to compute nodes via the storage hub.
   # On compute nodes, OVN adds lbaas:br-storage to ovn-bridge-mappings.
   - network:
       container_bridge: "br-lbaas"
       container_type: "veth"
       container_interface: "eth14"
       host_bind_override: "br-storage"
       ip_from_q: "lbaas"
       type: "vlan"
       range: "232:232"
       net_name: "lbaas"
       group_binds:
         - neutron_ovn_controller
         - octavia_all
   ```

   > **Implementation note:** `group_binds` must use `octavia_all` (the container group),
   > not `octavia-infra_hosts` (the physical host group). Using the physical host group
   > causes the Octavia LXC container to lack the lbaas network interface.

   Host group:
   ```yaml
   # Octavia Load Balancer
   octavia-infra_hosts:
     cloud-4core:
       ip: 192.168.50.168
   ```

2. **`user_variables.yml.j2`** — add Octavia overrides:
   ```yaml
   # Phase 13: Octavia Load Balancer
   # Single amphora topology (no HA pair) — sufficient for a home lab
   octavia_loadbalancer_topology: SINGLE
   # Disable anti-affinity (only 1 amphora per LB in SINGLE mode)
   octavia_enable_anti_affinity: false
   # Management network — VLAN on br-storage
   octavia_provider_network_type: vlan
   octavia_provider_segmentation_id: 232
   octavia_management_net_subnet_cidr: 172.29.232.0/22
   octavia_management_net_subnet_allocation_pools: "172.29.232.10-172.29.235.200"
   # Default LB provider — amphorav2 for L7 support; tenants can request
   # ovn provider explicitly with: --provider ovn
   octavia_default_provider_driver: amphorav2
   # Service project quotas — sized for upcoming 3×16C/64GB hardware upgrade
   _max_amphora_instances: 50
   openstack_user_identity:
     quotas:
       - name: "service"
         cores: "{{ _max_amphora_instances }}"
         ram: "{{ (_max_amphora_instances | int) * 1024 }}"
         instances: "{{ _max_amphora_instances }}"
         port: "{{ (_max_amphora_instances | int) * 10 }}"
         server_groups: "{{ ((_max_amphora_instances | int) * 0.5) | int | abs }}"
         server_group_members: 50
         security_group: "{{ (_max_amphora_instances | int) * 1.5 | int | abs }}"
         security_group_rule: "{{ ((_max_amphora_instances | int) * 1.5 | int | abs) * 100 }}"
   ```

3. **`configure_networking` role** — extended for Octavia lbaas networking:

   **Controller (cloud-4core):** `br-lbaas` Linux bridge + `br-storage.232` VLAN sub-interface
   created via NetworkManager. The Octavia container's `eth14` veth plugs into `br-lbaas`.

   **Compute nodes:** OVS bridge `br-storage` + veth pair (`veth-stor-lnx` ↔ `veth-stor-ovs`)
   connecting OVS to the Linux `br-storage`. This is required because `br-storage` is a
   Linux bridge managed by NetworkManager, but OVN needs an OVS bridge for the
   `lbaas:br-storage` mapping. A systemd oneshot service (`octavia-veth-bridge.service`)
   recreates the veth pair on boot after OVS starts.

   > **Implementation note:** `neutron_ml2_drivers_type` must include `vlan` (i.e.,
   > `"geneve,flat,vlan"`) or Neutron will reject the lbaas provider network with
   > `network_type value 'vlan' not supported`.

#### Deployment plan

1. Update `configure_networking` role with lbaas bridge setup (controller + compute)
2. Run `prepare_target_hosts.yml` to deploy br-lbaas (controller) and octavia-veth-bridge service (compute)
3. Add lbaas network config and `octavia-infra_hosts` to `openstack_user_config.yml.j2`
4. Add Octavia overrides + `neutron_ml2_drivers_type: "geneve,flat,vlan"` to `user_variables.yml.j2`
5. Deploy OSA config: `ansible-playbook playbooks/deploy_osa_config.yml`
6. Update Neutron for VLAN type: `openstack-ansible playbooks/os-neutron-install.yml --tags neutron-config`
7. Apply service project quotas: `openstack-ansible playbooks/openstack-resources.yml`
8. Create LXC container: `openstack-ansible playbooks/containers-lxc-create.yml --limit lxc_hosts,octavia_all`
9. Run: `openstack-ansible playbooks/os-octavia-install.yml`
10. Update HAProxy: `openstack-ansible playbooks/haproxy-install.yml`
11. Install `octavia-dashboard` Horizon plugin: `openstack-ansible playbooks/os-horizon-install.yml`
12. Verify: `openstack loadbalancer list` — should return empty list
13. Test OVN provider: `openstack loadbalancer create --name test-lb --provider ovn --vip-subnet-id <subnet>`
14. Test amphora provider: `openstack loadbalancer create --name test-lb-amp --provider amphorav2 --vip-subnet-id <subnet>`

#### Open questions for Octavia

**All resolved.**

- ~~br-lbaas bridge implementation~~ → **VLAN 232 on br-storage.** cloud-4core has no OVS and no spare physical NICs. A flat br-lbaas would be a dead-end bridge. Instead, create a Linux bridge `br-lbaas` with a VLAN sub-interface (`br-storage.232`) enslaved to it. The storage network uses an unmanaged hub that passes VLAN-tagged frames without inspection. VLAN tagging is software-only (Linux kernel) — no NIC or switch hardware support needed. On compute nodes, OVN adds `lbaas:br-storage` to `ovn-bridge-mappings` and handles VLAN tagging in OVS. The management router (RT-AX58U) is not involved.

- ~~Amphora image — test vs production~~ → **Test image first, then diskimage-builder.** Use the default test image (`test-only-amphora-x64-haproxy-ubuntu-noble.qcow2`) to validate the full deployment (L7 LB creation, heartbeats, config push, health checks). Once amphora is confirmed working, build a custom image with `diskimage-builder` — Ubuntu Noble base, 10 GB disk, no FIPS. Ceilometer telemetry integration for amphora VMs is a future-phase concern.

- ~~Octavia quotas~~ → **50 amphora instances.** The OSA docs suggest 10,000 — wildly excessive. Set `_max_amphora_instances: 50` in `user_variables.yml.j2`, which translates to 50 vCPU, 50 GB RAM, 500 ports, 25 server groups. Sized for the upcoming hardware upgrade (3 × 16C/32T × 64 GB compute nodes). Applied via `openstack_user_identity.quotas` on the `service` project.

- ~~OVN provider as default?~~ → **amphorav2 as default, both providers enabled.** Tenants choose with `--provider ovn` for L4 (instant, no VM) or get amphorav2 by default for full L7 (HTTP health checks, TLS termination, header insertion). Both providers are auto-enabled when `neutron_plugin_type: ml2.ovn`.

- ~~`octavia-dashboard` Horizon plugin~~ → **Install in Phase 13** alongside the Octavia service deployment. Each phase installs its own Horizon plugin.

### Phase 14 — Zun Container as a Service

Zun is "Nova but for containers." Tenants run `openstack appcontainer run --image docker.io/nginx zun-nginx` and it launches a Docker container on compute nodes, managed like a Nova instance (gets a Neutron port, security groups, etc.). [(install guide)](https://docs.openstack.org/zun/2025.1/install/) [(dashboard)](https://opendev.org/openstack/zun-ui) — clients: `python-zunclient`, `zun-ui`

#### OSA has full Zun support

Unlike Zaqar, OSA ships a complete `os_zun` role with playbook, env.d, HAProxy integration, and auto-provisioned secrets. This is a first-class OSA deployment — no custom roles needed.

- **Role:** `os_zun` (at opendev.org/openstack/openstack-ansible-os_zun)
- **Playbook:** `os-zun-install.yml` → `openstack.osa.zun`
- **env.d:** `zun.yml` — maps `zun_api` (LXC) and `zun_compute` (bare metal, `is_metal: true`)
- **Secrets:** Already generated in `user_secrets.yml` (`zun_galera_password`, `zun_service_password`, `zun_oslomsg_rpc_password`, `zun_kuryr_service_password`)
- **HAProxy:** Automatic — the playbook calls `openstack.osa.haproxy_service_config` with `zun_haproxy_services`
- **Maturity:** `status: development`, `created_during: rocky` (Rocky cycle, ~2018)

#### What Zun deploys

**Services:**

| Service | Where | How | Description |
|---|---|---|---|
| `zun-api` | cloud-4core | LXC container via uWSGI | REST API on port 9517 |
| `zun-wsproxy` | cloud-4core | LXC container | WebSocket proxy for `exec`/`attach` (port 6784) |
| `zun-compute` | compute nodes | Bare metal (is_metal) | Container lifecycle daemon |
| `kuryr-libnetwork` | compute nodes | Bare metal (uWSGI) | Docker network plugin → Neutron integration |
| `zun-cni-daemon` | compute nodes | Bare metal | CNI plugin for container networking |
| `docker` | compute nodes | Bare metal (systemd) | Container engine (Docker CE) |
| `containerd` | compute nodes | Bare metal | Container runtime (for Kata support) |

**Dependencies (all existing):**

- Keystone — authentication
- Neutron — container networking via Kuryr
- Placement — resource tracking and claims
- Galera — `zun` database
- RabbitMQ — `zun-api` ↔ `zun-compute` RPC
- HAProxy — frontend for zun-api and zun-wsproxy
- Optional: Glance (container image caching), Cinder (container volumes), Heat (orchestration)

#### Zun Architecture for this cluster

```bash
                         ┌──────────── cloud-4core ────────────┐
                         │                                     │
   Tenant / CLI ──────▶ │  HAProxy :9517 (zun-api)            │
   openstack             │  HAProxy :6784 (zun-wsproxy)        │
   appcontainer run      │      │                              │
                         │      └──▶ zun_api_container (LXC)  │
                         │           ├─ zun-api (uWSGI)        │
                         │           └─ zun-wsproxy            │
                         │                                     │
                         │  Galera ─── zun DB                  │
                         │  RabbitMQ ─── /zun vhost            │
                         │  Keystone ─── zun + kuryr users     │
                         └─────────────────────────────────────┘
                                        │ RPC
                         ┌──────────────┼────────────────────────┐
                         │              ▼                       │
   ┌─ cloud-6core ───┐  ┌─ cloud-celeron  ─┐  ┌─ cloud-eugene ───┐
   │   zun-compute   │  │   zun-compute    │  │   zun-compute   │
   │   kuryr-libnet  │  │   kuryr-libnet   │  │   kuryr-libnet  │
   │   zun-cni-daemon│  │   zun-cni-daemon │  │   zun-cni-daemon│
   │   Docker CE     │  │   Docker CE      │  │   Docker CE     │
   │   containerd    │  │   containerd     │  │   containerd    │
   │   (+ Kata opt.) │  │   (+ Kata opt.)  │  │   (+ Kata opt.) │
   │                 │  │                  │  │                 │
   │  [containers]   │  │  [containers]    │  │  [containers]   │
   │  ├ Neutron port │  │  ├ Neutron port  │  │  ├ Neutron port │
   │  └ sec groups   │  │  └ sec groups    │  │  └ sec groups   │
   └─────────────────┘  └──────────────────┘  └─────────────────┘
```

Zun runs `zun-compute` on all compute nodes **alongside Nova** — controlled by `host_shared_with_nova = true` in the config. The `os_zun` role installs Docker CE, containerd, Kata Containers, Kuryr-libnetwork, and the CNI plugin directly on the host (bare metal, not in LXC).

#### Zun Key configuration variables

```yaml
# openstack_user_config.yml — add these sections:

# Zun API (control plane) — LXC on cloud-4core
zun-infra_hosts:
  cloud-4core:
    ip: 192.168.50.168

# Zun compute (container engine) — bare metal on all compute nodes
zun-compute_hosts:
  cloud-6core:
    ip: 192.168.50.171
  cloud-celeron:
    ip: 192.168.50.178
  cloud-eugene:
    ip: 192.168.50.234
```

```yaml
# user_variables.yml — Zun overrides:

# Compute nodes are shared with Nova (both manage workloads)
zun_zun_conf_overrides:
  compute:
    host_shared_with_nova: true

# Kata Containers — enabled by default in os_zun. Set to false if
# compute node CPUs don't support nested virt (check /proc/cpuinfo for vmx/svm)
# zun_kata_enabled: "False"
```

#### Zun Deployment plan

**Step 0 — Pre-checks** ✅

- [x] Verify compute node CPU virtualization extensions for Kata:
  `grep -c 'vmx\|svm' /proc/cpuinfo` on each compute node
  (Kata requires HW virt; if missing, set `zun_kata_enabled: "False"`)
- [x] Verify Docker is not already installed on compute nodes:
  `dpkg -l | grep docker` — the role will install Docker CE and may conflict with existing installs
- [x] Check available disk space on compute nodes for Docker images:
  `/var/lib/docker` needs room for container images (10G+ recommended)
- [x] Verify Placement service is operational:
  `openstack resource provider list` should show compute nodes

  **Step 1 — Update `openstack_user_config.yml.j2`** ✅

  Add `zun-infra_hosts` and `zun-compute_hosts` sections to the config template. This tells OSA where to deploy Zun.

  **Step 2 — Update `user_variables.yml.j2`** ✅

  Add the `zun_zun_conf_overrides` section with `host_shared_with_nova: true`. Decide on Kata Containers (enabled by default — requires nested virt or bare metal virt extensions).

  **Step 3 — Deploy OSA config** ✅

```bash
cd /home/kevin/Repos/home-cloud
ansible-playbook playbooks/deploy_osa_config.yml
```

This renders the updated templates to `/etc/openstack_deploy/`.

**Step 4 — Run the Zun playbook** ✅

```bash
cd /opt/openstack-ansible
# Must create LXC container first (os-zun-install.yml doesn't do it)
openstack-ansible playbooks/lxc-containers-create.yml --limit cloud-4core-zun-api-container*
openstack-ansible playbooks/os-zun-install.yml
```

This single playbook does everything:
1. Creates the `zun_api_container` LXC on cloud-4core
2. Creates the `zun` database in Galera
3. Creates `zun` and `kuryr` users in Keystone
4. Creates `container` service + endpoints in Keystone catalog
5. Creates RabbitMQ vhost and user
6. Installs Zun (from source) in a Python venv
7. Configures `zun.conf` and `kuryr.conf`
8. Installs Docker CE + containerd + Kata on compute nodes
9. Installs Kuryr-libnetwork on compute nodes
10. Installs CNI plugin on compute nodes
11. Configures HAProxy frontends for ports 9517 and 6784
12. Starts all systemd services

**Step 5 — Verify** ✅

```bash
# Check services are up
openstack appcontainer service list

# Install the CLI if not already available
pip install python-zunclient

# Run a test container on a selfservice network
NET_ID=$(openstack network show selfservice -f value -c id 2>/dev/null || \
         openstack network list -f value -c ID --limit 1)
openstack appcontainer run --name test-nginx --net network=$NET_ID \
  --image docker.io/library/cirros:latest ping -c 4 8.8.8.8

# Check it's running
openstack appcontainer list
openstack appcontainer show test-nginx

# Interactive shell
openstack appcontainer exec --interactive test-nginx /bin/sh

# Cleanup
openstack appcontainer stop test-nginx
openstack appcontainer delete test-nginx
```

**Step 6 — Install zun-ui Horizon plugin** ✅

The `zun-ui` dashboard plugin adds a "Containers" panel to Horizon. This is a separate install — the os_zun role doesn't include it. Installed via `pip install zun-ui` in the Horizon container's venv, then restarted Apache. Panel symlinks are created automatically by pip.

#### IaC approach

Since OSA handles the entire deployment, our IaC is simpler than Trove:

1. **`openstack_user_config.yml.j2`** — add `zun-infra_hosts` and `zun-compute_hosts`
2. **`user_variables.yml.j2`** — add `zun_zun_conf_overrides`
3. **Run `deploy_osa_config.yml`** — renders templates to `/etc/openstack_deploy/`
4. **Run `os-zun-install.yml`** — OSA handles everything else

No custom `deploy_zun.yml` playbook is needed unless we want to automate the verification step or zun-ui installation.

#### Docker on workstation compute nodes — potential concerns

These compute nodes are Ubuntu 24.04 **desktop workstations**. The `os_zun` role will install Docker CE on all three. Things to watch for:

1. **Docker CE + existing snap Docker:** If `docker.io` snap or apt package is already installed, conflicts may occur. Check with `snap list docker` and `dpkg -l | grep docker`.

2. **Docker daemon listening on TCP:** The role configures Docker to listen on `tcp://0.0.0.0:2375` (unencrypted!) for `zun-compute` to manage containers remotely. This is bound to the management network only via the bridge, but be aware it's open.

3. **Disk space:** Docker images land in `/var/lib/docker`. Container images (especially if users pull large images like tensorflow, pytorch) can fill disks quickly. Consider setting `zun_docker_prune_images: true` and `zun_docker_prune_frequency: day`.

4. **Resource contention:** Containers and Nova VMs will compete for CPU/RAM on the same hosts. The `host_shared_with_nova: true` setting tells Zun's scheduler to account for this, but it's not a hard guarantee.

5. **Kata Containers:** Enabled by default. Kata runs containers inside lightweight VMs (QEMU), so it needs VT-x/AMD-V. On the desktop workstations, check that `/proc/cpuinfo` shows `vmx` (Intel) or `svm` (AMD). If not available or if you want simpler operation, set `zun_kata_enabled: "False"` to use `runc` only.

#### Open questions

**Resolved:**

- ~~zun-ui Horizon plugin~~ → **Install in Phase 14** alongside the Zun service deployment. Each phase installs its own Horizon plugin.

- ~~Kata Containers — enable or disable?~~ → **Disable (use `runc`).** Set `zun_kata_enabled: "False"`, `zun_container_runtime: runc`. Kata dedicates resources per container (own kernel, pinned memory) — a micro-VM that holds its allocation even when idle. With runc, containers share the host kernel and can overcommit CPU/RAM via cgroup scheduling, which is much better for a resource-constrained lab. The architectural lessons of Zun (API, scheduling, Neutron integration, image management) are identical regardless of runtime — it's a one-line config change. Kata can be enabled later on a single node as an experiment.

- ~~Existing Docker installations~~ → **Not a conflict; Zun will take ownership.** Docker CE 29.4.0 is installed on all 4 nodes but is not used by OpenStack (only LXC containers). Each node has only a stale `hello-world` container from initial testing (~492KB in `/var/lib/docker`). The `os_zun` role will reconfigure the Docker daemon (add TCP listener, set group, manage via systemd). The existing installation is harmless.

- ~~Docker image storage~~ → **Default root filesystem is fine.** Zun uses Docker as its container engine (Zun → Docker daemon → runc). Image drivers are `glance` and `docker` (Docker Hub), default is `docker`. Either way, images end up in `/var/lib/docker` on each compute node (overlay2 storage driver). Glance is an alternative image *source* (Zun downloads from Glance into a local directory, then loads into Docker), not a replacement for local storage. For a lab with modest usage, a few dozen container images = a few GB on the root disk. Enable `zun_docker_prune_images: true` to auto-clean unused images.

- ~~Docker TCP exposure~~ → **Restrict to management network.** Set `zun_docker_bind_host` to each node's management IP (e.g., `192.168.50.x`) instead of the default `0.0.0.0`. This limits the unauthenticated Docker TCP API to the management VLAN. The role also binds to the local Unix socket for local access.

- ~~Kuryr + OVN~~ → Kuryr-libnetwork is bundled into the `os_zun` role and deployed on compute nodes as a Docker network plugin. Not a standalone service — no separate deployment phase needed. OVN compatibility required two hotfixes — see "Issues encountered" below.

**All Zun open questions resolved.**

#### Issues encountered during deployment

1. **Docker apt repo conflict:** Pre-existing `/etc/apt/sources.list.d/docker.list` (legacy one-line format) conflicted with the `os_zun` role's `docker-ce.sources` (DEB822 format) — different `Signed-By` values for the same repository. **Fix:** Removed `docker.list` on all 3 compute nodes before re-running.

2. **LXC container not auto-created:** `os-zun-install.yml` does not create the LXC container for the Zun API — it expects it to already exist. **Fix:** Ran `lxc-containers-create.yml --limit cloud-4core-zun-api-container*` before the Zun playbook.

3. **libssl3 stale package on cloud-celeron:** A stale `rc` (removed, config-files) entry for `libssl3` blocked apt resolution of `libssl3` → `libssl3t64` (Ubuntu 24.04 time_t ABI transition). The `uwsgi` role hardcodes `libssl3` as a dependency. **Fix:** `sudo dpkg --purge libssl3` on cloud-celeron.

4. **Zun Docker driver KeyError (bug in 2025.2):** `zun/container/docker/driver.py` line 268 uses `image_dict['Config']['Entrypoint']` (direct dict access) which raises `KeyError` for images without an Entrypoint field (e.g., cirros). **Hotfix:** Patched all 3 compute nodes to use `.get('Entrypoint')` and `.get('Cmd')`. This is a Zun bug — will be overwritten on next OSA update.

5. **Kuryr + OVN MAC address conflict (bug in kuryr-libnetwork with OVN):** When creating a container endpoint, Kuryr's `port_driver/driver.py:update_port()` tries to update both `binding:host_id` and `mac_address` on a Neutron port in a single API call. OVN processes the binding first, then rejects the MAC change on the now-bound port: *"port is already bound, port type: ovs, old_mac fa:16:3e:..., new_mac f6:b8:88:..."*. The MAC update is unnecessary because the veth binding driver (`kuryr/lib/binding/drivers/veth.py:port_bind()`) already sets the container interface MAC to the Neutron port's MAC address. **Hotfix:** Commented out lines 144-145 in `kuryr_libnetwork/port_driver/driver.py` on all 3 compute nodes to skip the MAC update. Restarted kuryr-libnetwork. This is a Kuryr bug with OVN — will be overwritten on next OSA update.

For right now, we're leaving these buys unfixed and waiting for upstream fixes.

### Phase 15 — Magnum Kubernetes as a Service

**Note:** Docker Swarm support has been removed from Magnum. Only the **Kubernetes** COE remains. The title is updated to reflect this.

**Warning — Heat driver deprecation:** The Magnum user guide states: *"The heat driver described here is deprecated in favor of the `k8s_capi_helm` or `k8s_cluster_api` driver and will be removed in a future Magnum version."* However, 2025.1 docs only document the Heat driver, the CAPI drivers have minimal documentation, and the OSA `os_magnum` role has **no CAPI driver configuration** (confirmed by grepping the role defaults). For this home lab we will use the **Heat-based `k8s_fedora_coreos_v1` driver** — the only one fully supported by OSA. If/when the CAPI driver matures, it can be evaluated later.

#### What Magnum is

Magnum is an OpenStack API service that makes Kubernetes available as a first-class resource. Users create **ClusterTemplates** (defining image, network driver, flavors, etc.) and then create **Clusters** from those templates. Magnum uses **Heat** to orchestrate Nova VMs running Fedora CoreOS with Kubernetes pre-configured. It provides full lifecycle management: create, scale (add/remove worker nodes), update, and delete clusters.

Key capabilities:

- Multi-tenant Kubernetes clusters (each cluster gets its own private Neutron network)
- TLS-secured cluster API endpoints (certificates managed by Magnum)
- Keystone integration for k8s authentication/authorization
- Cinder CSI for persistent volumes inside k8s pods
- Node groups for heterogeneous clusters (different flavors per node group)
- Auto-healing and auto-scaling (optional)
- `kubectl` access via `eval $(openstack coe cluster config <name>)`

#### Magnum OSA support status

OSA has **full Magnum support**:

| Component | Status |
|---|---|
| Ansible role | `os_magnum` at `opendev.org/openstack/openstack-ansible-os_magnum` |
| Playbook | `os-magnum-install.yml` → `openstack.osa.magnum` collection playbook |
| env.d | `magnum.yml` — single `magnum_container` LXC in `magnum-infra_containers` |
| Secrets | Pre-generated in `user_secrets.yml`: `magnum_galera_password`, `magnum_oslomsg_rpc_password`, `magnum_service_password`, `magnum_trustee_password` |
| HAProxy | Role includes haproxy service definitions for port 9511 |

#### Magnum Architecture for this cluster

```bash
                    ┌─────────── cloud-4core ────────────┐
                    │                                    │
  Tenant / CLI ──▶ │  HAProxy :9511                     │
                    │    └──▶ magnum_container (LXC)    │
                    │           ├─ magnum-api (uWSGI)    │
                    │           └─ magnum-conductor      │
                    │                  │                 │
                    │     ┌────────────┼────────────┐    │
                    │     ▼            ▼            ▼    │
                    │  Keystone    Galera/RabbitMQ  Heat │
                    │  (existing)  (existing)  (existing)│
                    └────────────────────────────────────┘

  When user runs: openstack coe cluster create ...
                    │
                    ▼
  Magnum ──▶ Heat stack ──▶ Nova VMs (Fedora CoreOS)
                             ├─ master (kube-apiserver, etcd, scheduler, controller-manager)
                             └─ workers (kubelet, kube-proxy, flannel/calico)
                             on cloud-6core / cloud-celeron / cloud-eugene compute nodes
```

Magnum is **control-plane only** — no agents on compute nodes. The k8s master and worker nodes are Nova VMs running Fedora CoreOS. Compute nodes just need Nova (already deployed).

Unlike **Zun** (Phase 13), Magnum does NOT install Docker/containerd on the bare-metal compute hosts. The container runtime runs inside the Nova VMs.

#### Dependencies

| Dependency | Status | Notes |
|---|---|---|
| Keystone | ✅ Deployed | Authentication, trust domains |
| Neutron | ✅ Deployed | Private cluster networks, routers |
| Nova | ✅ Deployed | VM-based k8s nodes |
| Glance | ✅ Deployed | Fedora CoreOS image storage |
| Cinder | ✅ Deployed | Persistent volumes (CSI), docker-volume-size |
| Barbican | ✅ Deployed | Certificate storage — using `barbican` cert manager |
| Placement | ✅ Deployed | Resource scheduling |
| Heat | ✅ Deployed | Magnum uses Heat stacks to orchestrate cluster VMs |
| Octavia | ⏳ Phase 13 | Needed for `--master-lb-enabled` (multi-master HA). Deploying as Phase 13 before Magnum. |

#### IaC gap: `orchestration_hosts` not in template

Heat is deployed and working (Orchestration dashboard in Horizon, HOT templates tested in TESTING.md), but `orchestration_hosts` is missing from our `openstack_user_config.yml.j2` template. The Heat container (`cloud-4core-heat-api-container-0c7ea218`) was created during initial OSA deployment before this repo tracked the config. We should backfill this to keep IaC in sync with reality.

#### Magnum services

| Service | Type | Container | Listens |
|---|---|---|---|
| `magnum-api` | uWSGI behind HAProxy | `magnum_container` (LXC on cloud-4core) | Port 9511 |
| `magnum-conductor` | systemd service (AMQP) | Same `magnum_container` | No external port |

Both services run in a **single LXC container** on cloud-4core, same as other control-plane services.

#### Keystone trust domain

Magnum creates a special Keystone setup for cluster VM credential delegation:

- Domain: `magnum` (configurable via `magnum_trustee_domain_name`)
- Admin user: `trustee_domain_admin` in that domain (password from `magnum_trustee_password`)
- Cluster VMs receive delegated trust tokens to call OpenStack APIs (Nova, Neutron, Cinder)

The `os_magnum` role's `magnum_service_setup.yml` task handles this automatically.

#### Cluster images

The default Magnum driver (`k8s_fedora_coreos_v1`) requires a **Fedora CoreOS** image in Glance with `os_distro=fedora-coreos` property.

Tested versions (from the Magnum 2025.1 user guide):

| OpenStack Release | k8s Version | FCOS Image |
|---|---|---|
| 19.0.0 (Dalmatian) | v1.28.9-rancher1 | fedora-coreos-38.20230806.3.0 |
| 18.0.0 (Caracal) | v1.27.8-rancher2 | fedora-coreos-38.20230806.3.0 |

**2025.2 (Flamingo) is not yet in the tested matrix.** The Dalmatian combination is the safest starting point.

**Important: FCOS 38 ships containerd 1.4.4, which only supports CRI v1alpha2. kubelet v1.28+ requires CRI v1 (containerd >= 1.6).** Magnum's install-cri.sh downloads a containerd tarball from GitHub and extracts it over the system binary. The default `CONTAINERD_VERSION=1.4.4` is too old. You **must** set `containerd_version=1.7.25` (or later 1.7.x) on the cluster template labels. Using a newer FCOS image (e.g., FCOS 43) avoids the system containerd being old, but Magnum still overwrites it with whatever `containerd_version` is set to.

The `os_magnum` role can auto-upload images via the `magnum_glance_images` variable, or you can upload manually:
```bash
curl -L -o fedora-coreos-43.qcow2.xz \
  "https://builds.coreos.fedoraproject.org/prod/streams/stable/builds/43.20260316.3.1/x86_64/fedora-coreos-43.20260316.3.1-openstack.x86_64.qcow2.xz"
xz -d fedora-coreos-43.qcow2.xz
openstack image create fedora-coreos-43 \
  --disk-format qcow2 --container-format bare --public \
  --property os_distro=fedora-coreos \
  --file fedora-coreos-43.qcow2
```

#### Certificate management

| Mode | Config value | Notes |
|---|---|---|
| DB-stored | `x509keypair` (default) | Stores certs in Magnum DB. Simplest. |
| Barbican | `barbican` | Recommended for production. We have Barbican deployed. |
| Local filesystem | `local` | Single-conductor only. Not recommended. |

Since we have Barbican deployed, the recommendation is `magnum_cert_manager_type: barbican`.

#### Cluster networking

Magnum creates a **private Neutron network** per cluster with a router to the external network. Container networking inside the k8s cluster is handled by a CNI plugin:

| Network Driver | Notes |
|---|---|
| `flannel` (default) | Overlay network. Backend options: `vxlan` (default), `host-gw` (best perf on private Neutron net), `udp` (slow). |
| `calico` | Network policy support. Requires `cgroup_driver=cgroupfs`. |

For a home lab, **flannel with host-gw backend** is recommended (best performance on Magnum's private Neutron network where all VMs are on the same L2).

#### Key OSA configuration variables

From `os_magnum` role defaults:

| Variable | Default | Recommended |
|---|---|---|
| `magnum_cert_manager_type` | `x509keypair` | `barbican` (we have it) |
| `magnum_glance_images` | `[]` | Upload FCOS image (can be manual or via this var) |
| `magnum_cluster_templates` | `[]` | Optionally pre-create a default template |
| `magnum_flavors` | `[]` | Optionally pre-create k8s flavors |
| `magnum_trustee_domain_name` | `magnum` | Default is fine |
| `magnum_bind_port` | `9511` | Default is fine |

#### IaC changes needed

1. **`openstack_user_config.yml.j2`** — add host groups:

   ```yaml
   # Backfill: Heat (Orchestration) — already deployed, syncing IaC with reality
   orchestration_hosts:
     mgmt.cloud-4core.local:
       ip: 192.168.50.168

   # Phase 15: Magnum (Container Infrastructure Management)
   magnum-infra_hosts:
     mgmt.cloud-4core.local:
       ip: 192.168.50.168
   ```

2. **`user_variables.yml.j2`** — add Magnum overrides:

   ```yaml
   # Phase 15: Magnum
   magnum_cert_manager_type: barbican
   ```

3. **Playbooks** — no new playbook needed (use OSA's `os-heat-install.yml` and `os-magnum-install.yml`). Could add a `deploy_magnum.yml` wrapper for consistency.

#### Magnum Deployment plan

**Step 1 — Deploy Magnum:**

1. Backfill `orchestration_hosts` in `openstack_user_config.yml.j2` (sync IaC with deployed reality)
2. Add `magnum-infra_hosts` to `openstack_user_config.yml.j2`
3. Add `magnum_cert_manager_type: barbican` to `user_variables.yml.j2`
4. Add `magnum_wsgi_processes: 2` and `magnum_conductor_workers: 2` to `user_variables.yml.j2` (OSA defaults to 8 each on cloud-4core — excessive for a home lab)
5. Deploy OSA config: `ansible-playbook playbooks/deploy_osa_config.yml`
6. Create LXC container: `openstack-ansible playbooks/lxc-containers-create.yml --limit magnum*`
7. Run: `openstack-ansible /opt/openstack-ansible/playbooks/os-magnum-install.yml`
8. Verify: `openstack coe service list` — should show magnum-conductor
9. Verify Keystone: `openstack domain show magnum` — trust domain created

**Step 2 — Install magnum-ui Horizon plugin:**

Install `magnum-ui` and verify the Container Infra panel appears in Horizon.

**Step 2.5 — Register `volumev3` Keystone service alias:**

cinder-csi (gophercloud) looks for a `volumev3` service type in the Keystone catalog, but OpenStack 2025.2 only registers `block-storage`. Create an alias:

```bash
openstack service create --name cinderv3 --description "Cinder Volume Service v3 (alias for cinder-csi compatibility)" volumev3
CINDER_URL="https://$(grep internal_lb_vip_address /etc/openstack_deploy/openstack_user_config.yml | awk '{print $2}'):8776/v3"
for iface in public internal admin; do
  openstack endpoint create --region RegionOne volumev3 $iface "$CINDER_URL"
done
```

Verify: `openstack endpoint list --service volumev3` — should show 3 endpoints.

**Step 3 — Upload Fedora CoreOS image and create cluster template:**

1. Download and upload Fedora CoreOS image to Glance (with `os_distro=fedora-coreos`)

2. Create a cluster template:

   ```bash
   openstack coe cluster template create k8s-calico \
     --image fedora-coreos-43 \
     --keypair magnum-key \
     --external-network provider-net \
     --dns-nameserver 8.8.8.8 \
     --master-flavor k8s.small \
     --flavor k8s.small \
     --network-driver calico \
     --volume-driver cinder \
     --docker-volume-size 30 \
     --coe kubernetes \
     --master-lb-enabled \
     --floating-ip-enabled \
     --docker-storage-driver overlay2 \
     --labels calico_ipv4pool=10.100.0.0/16,calico_ipv4pool_ipip=Off,calico_tag=v3.26.4,cgroup_driver=cgroupfs,container_runtime=containerd,kube_tag=v1.28.9-rancher1,containerd_version=1.7.25,containerd_tarball_sha256=6b987a57a3f2257ca2cc5f4697b481eec917bd2085299aeab0547d388ff8b983,cloud_provider_tag=v1.28.3,cinder_csi_plugin_tag=v1.28.3,k8s_keystone_auth_tag=v1.28.3
   ```

3. Create a test cluster:
   ```bash
   openstack coe cluster create test-k8s \
     --cluster-template k8s-small \
     --master-count 1 \
     --node-count 1
   ```

4. Wait for CREATE_COMPLETE, then:
   ```bash
   eval $(openstack coe cluster config test-k8s)
   kubectl get nodes
   kubectl get pods --all-namespaces
   ```

   **Step 4 — Verify Magnum end-to-end:**

1. Confirm Heat stack reached CREATE_COMPLETE: `openstack stack show $(openstack coe cluster show test-k8s -f value -c stack_id)`
2. Confirm cluster VMs are ACTIVE: `openstack server list` — should show master and worker Nova instances
3. Verify k8s API reachable: `kubectl get nodes` — all nodes should be Ready
4. Verify system pods: `kubectl get pods -A` — coredns, calico, kube-proxy all Running
5. Deploy a test workload:

   ```bash
   kubectl create deployment nginx --image=nginx:alpine --replicas=2
   kubectl expose deployment nginx --port=80 --type=NodePort
   kubectl get pods -o wide   # should show 2 running pods
   kubectl get svc nginx      # should show NodePort
   ```

6. Clean up test workload: `kubectl delete deployment nginx && kubectl delete svc nginx`
7. Delete test cluster: `openstack coe cluster delete test-k8s` — wait for DELETE_COMPLETE
8. Verify Heat stack cleaned up: `openstack stack list` — test-k8s stack should be gone

**Known issues discovered during cluster bring-up:**

1. **OpenStack integration image tags — Magnum defaults are ancient and don't exist in registries.** Magnum's Heat templates hardcode defaults: `cloud_provider_tag=v1.23.1`, `cinder_csi_plugin_tag=v1.23.0`, `k8s_keystone_auth_tag=v1.18.0`. These tags do **not** exist in `registry.k8s.io/provider-os/` (minimum available is v1.24.6). For K8s v1.28.9, the correct tag for all three is `v1.28.3`. **Fix:** Set `cloud_provider_tag=v1.28.3,cinder_csi_plugin_tag=v1.28.3,k8s_keystone_auth_tag=v1.28.3` as labels on the cluster template (already added to Step 3 above).

2. **keystone-auth webhook chicken-and-egg.** kube-apiserver is configured with `--authorization-mode=Node,Webhook,RBAC` pointing to `k8s-keystone-auth` on port 8443. If the keystone-auth pod can't start (e.g., bad image tag + `imagePullPolicy: Always`), the webhook endpoint is unreachable and **all** API operations — including GET and the patches needed to fix the pod — are blocked. **Workaround if hit:** SSH into the master VM, edit `/etc/kubernetes/apiserver` to temporarily remove `Webhook` from `--authorization-mode` and comment out the `--authentication-token-webhook-config-file` / `--authorization-webhook-config-file` lines, restart kube-apiserver (`systemctl restart kube-apiserver`), apply fixes, then restore from backup (`apiserver.bak`).

3. **cinder-csi `volumev3` service type required.** cinder-csi v1.28.3 uses gophercloud which looks for a `volumev3` service type in the Keystone catalog. OpenStack 2025.2 registers only `block-storage` as the service type (per the modern standard). Neither `bs-version=v3` nor `bs-version=auto` in the cloud-config helps — the endpoint discovery fails before the version negotiation. **Fix:** Register a `volumev3` service alias in Keystone (see prerequisite step below).

4. **Podman image pulls stall inside FCOS VMs.** Container image pulls via podman (used by Heat software-config agent and etcd) frequently stall — `pigz -d` sits at 0.0% CPU for 10+ minutes. Affects `quay.io/coreos/etcd:v3.4.6` and other images. **Workaround:** Kill the stalled pull (`systemctl stop <service>`, `podman rm -f <container>`), then re-pull manually (`podman pull <image>`) — typically succeeds instantly on retry. Restart the service after.

#### Resolved questions for Magnum

- ~~Certificate manager~~ → **Barbican** (`magnum_cert_manager_type: barbican`)

- ~~FCOS version for 2025.2~~ → **FCOS 43** (`fedora-coreos-43.20260316.3.1`). FCOS 38 (the Dalmatian-tested image) ships containerd 1.4.4 which lacks CRI v1 support needed by kubelet v1.28+. Magnum's `install-cri.sh` downloads a containerd tarball specified by the `containerd_version` label and overwrites the system binary, so the FCOS version matters less than the label — but using a modern FCOS avoids other staleness issues. Confirmed working: FCOS 43 + `containerd_version=1.7.25`.

- ~~k8s version / labels~~ → **Start with Dalmatian-tested labels** (`kube_tag=v1.28.9-rancher1`, etc.) as a known-good baseline. k8s version is independent of both FCOS and Magnum — it's set via `kube_tag` label on the cluster template and pulled at boot time as container images. Once the cluster works, experiment with newer k8s versions.

- ~~containerd version~~ → **1.7.25** (latest 1.7.x series). Magnum defaults to `CONTAINERD_VERSION=1.4.4` which only supports CRI v1alpha2. kubelet v1.28+ requires CRI v1 (containerd >= 1.6). Set via `containerd_version=1.7.25` and `containerd_tarball_sha256=6b987a57a3f2257ca2cc5f4697b481eec917bd2085299aeab0547d388ff8b983` labels on the cluster template. The tarball is downloaded from GitHub at `https://github.com/containerd/containerd/releases/download/v{VERSION}/cri-containerd-cni-{VERSION}-linux-amd64.tar.gz`.

- ~~Cluster node sizing~~ → **Three flavors** for Magnum clusters. Master needs etcd + apiserver so minimum 2 vCPU / 4GB. Workers scale with workload. Create these Nova flavors:

  | Flavor | vCPUs | RAM | Root Disk | Use case |
  |---|---|---|---|---|
  | `k8s.small` | 2 | 4 GB | 20 GB | Master node (minimum viable), light worker |
  | `k8s.medium` | 3 | 6 GB | 20 GB | Comfortable master, typical worker |
  | `k8s.large` | 4 | 8 GB | 20 GB | Master with headroom, heavier worker |

  A minimal learning cluster: 1 master (`k8s.small`) + 2 workers (`k8s.small`) = 6 vCPUs, 12 GB RAM. With anti-affinity, Nova spreads these across the 3 compute nodes.

- ~~Docker storage volume size~~ → **30 GB per node.** This Cinder volume holds container images pulled by the kubelet (via containerd/overlay2). k8s system images (pause, coredns, kube-proxy, flannel) total ~1-2 GB. A handful of app images adds another few GB. 30 GB gives comfortable headroom for a lab without wasting Cinder LVM capacity. For a minimal 3-node cluster that's 90 GB out of 476.9 GB available on cloud-eugene `/dev/sde`. Increase to 50 GB if running image-heavy workloads.

- ~~CAPI driver future~~ → **Not tracking.** The Heat driver works today and is fully supported by OSA. If CAPI matures, it'll surface in OpenStack release notes / newsletters.

- ~~External network & floating IPs~~ → **Already configured.** `provider-net` (`192.168.2.0/24`, flat on `physnet1`, `router:external=True`) is exactly what Magnum needs as `--external-network provider-net`. Floating IPs are allocated from the pool `192.168.2.100-.200` (101 addresses). A 3-node cluster uses ~4 floating IPs (3 nodes + 1 master LB VIP). `test-router` already provides NAT between tenant networks and the provider network.

- ~~Network driver — flannel or calico?~~ → **Calico.** Magnum only supports `flannel` and `calico` as network drivers (no Cilium). Calico provides NetworkPolicy support for pod-level firewall rules, which is valuable for learning real-world Kubernetes networking. Requires `cgroup_driver=cgroupfs` (the default in Magnum). Uses BGP to distribute routes between nodes — no encapsulation overhead by default (`calico_ipv4pool_ipip=Off`). Labels: `calico_ipv4pool=10.100.0.0/16`, `calico_tag=v3.26.4` (from Dalmatian-tested set).

- ~~OpenStack integration image tags~~ → **Must match K8s minor version.** Magnum's Heat templates default to `cloud_provider_tag=v1.23.1`, `cinder_csi_plugin_tag=v1.23.0`, `k8s_keystone_auth_tag=v1.18.0` — these tags don't exist in `registry.k8s.io/provider-os/`. For K8s v1.28.9, use `v1.28.3` for all three. Set via labels on the cluster template.

- ~~cinder-csi endpoint discovery~~ → **Requires `volumev3` Keystone service alias.** cinder-csi (gophercloud) looks for `volumev3` service type but OpenStack 2025.2 only registers `block-storage`. Neither `bs-version=v3` nor `bs-version=auto` helps — the lookup fails before version negotiation. Fix: register a `volumev3` service alias in Keystone pointing to the same cinder endpoint URL (see Step 2.5).

**All Magnum open questions resolved.**

#### Operational Notes for Magnum

In production Kubernetes, separating the master and worker VMs onto different physical hosts is a best practice for fault tolerance — if the hypervisor hosting the master dies, you don't also lose workers (and vice versa). But it's not a technical requirement — Kubernetes works fine with everything on one host.

With Magnum, yes, you can control placement. Two approaches:

Nova anti-affinity server groups — Magnum supports passing a server group to the cluster template. You create an anti-affinity group, and Nova's scheduler ensures the VMs land on different hypervisors:

The Kubernetes VMs are just regular Nova instances — they coexist with your other VMs on the same hypervisors. Nothing is "blocked off."

For your learning setup, sizing might look like:

- 1 master VM: 2 vCPU, 4G RAM, 20G disk

- 2 worker VMs: 2 vCPU, 4G RAM, 40G disk each

  That's 6 vCPUs and 12G RAM total for a minimal k8s cluster, leaving plenty of capacity on your hypervisors for other VMs.

```bash
openstack server group create --policy anti-affinity k8s-spread
# Then reference this group in the Magnum cluster template
```

Nova availability zones — You could create AZs per hypervisor and pin master/worker roles to specific zones, though this is heavier-handed.

For your 3-hypervisor setup, anti-affinity would naturally spread a 3-VM cluster (1 master + 2 workers) across all three compute nodes, which is ideal.

That said, for a learning setup, it honestly doesn't matter if they land on the same hypervisor. The Kubernetes behavior is identical either way. Anti-affinity only matters when you care about surviving hardware failure — which isn't a concern for a lab where you're learning how the pieces fit together.

If your goal is specifically to learn how providers offer managed Kubernetes, Magnum is the right tool. Just be aware it's a non-trivial deployment — it needs its own container images (Fedora CoreOS or Ubuntu with k8s pre-installed), a Heat stack under the hood, and integration with Barbican (for secrets) or at minimum certificate management. It's a project in itself on top of your existing cloud.

### Phase 16 — Ceilometer + Gnocchi (Telemetry Data Collection)

Ceilometer collects telemetry data (metrics and events) from all OpenStack services via `oslo.messaging` notifications and polling agents. It pushes metrics to **Gnocchi** (time-series database) and events to the message bus. Aodh (Phase 17) consumes this data for alarming.

**Architecture:**

- **Gnocchi** — time-series metric storage with a REST API (port 8041). Uses a **storage backend** for metric data (file, Swift, Ceph, S3) and **Galera** for the indexer database. Must be deployed first since Ceilometer publishes to it.

- **Ceilometer central/notification agents** — run in an LXC container on cloud-4core. The notification agent listens to RabbitMQ for events from all services. The central (polling) agent polls APIs for metrics that aren't available via notifications (e.g., object-store stats).

- **Ceilometer compute agent** — runs directly on each compute host (bare metal, not LXC) to poll hypervisor-level metrics (CPU, memory, disk, network for VMs via libvirt).

**OSA roles:** `os_gnocchi`, `os_ceilometer` — fully automated. Deploy order: Gnocchi → Ceilometer.

**Services created:**

| Service | Port | Type | Container |
|---|---|---|---|
| Gnocchi API | 8041 | `metric` | `cloud-4core-gnocchi-container-*` (LXC) |
| Gnocchi metricd | — | — | Same container (background worker) |
| Ceilometer notification agent | — | — | `cloud-4core-ceilometer-central-container-*` (LXC) |
| Ceilometer polling agent (central) | — | — | Same container |
| Ceilometer polling agent (compute) | — | — | Bare metal on each compute host |

**Host inventory needed** (`/etc/openstack_deploy/conf.d/`):

- `metering-infra_hosts` → cloud-4core (central + notification agents, in LXC)
- `metering-compute_hosts` → cloud-6core, cloud-celeron, cloud-eugene (compute polling agent, bare metal)
- `metrics_hosts` → cloud-4core (Gnocchi, in LXC)

#### What Ceilometer gives us

- **VM resource metering** — CPU utilization, memory usage, disk I/O, network I/O for every Nova instance, collected every 600 seconds (default, configurable via `ceilometer_sample_interval`).
- **Service event tracking** — instance create/delete/resize, volume attach/detach, image upload, network changes — everything that emits oslo.messaging notifications.
- **Foundation for autoscaling** — Aodh alarms (Phase 17) + Heat auto-scaling groups use Ceilometer data to trigger scale-up/down.
- **Usage/billing data** — if ever needed, Ceilometer + CloudKitty can produce cost reports.

#### Ceilometer Implementation

**Step 1 — Create conf.d host mappings:**

Create `/etc/openstack_deploy/conf.d/gnocchi.yml`:

```yaml
metrics_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

Create `/etc/openstack_deploy/conf.d/ceilometer.yml`:

```yaml
metering-infra_hosts:
  cloud-4core:
    ip: 192.168.50.168

metering-compute_hosts:
  cloud-6core:
    ip: 192.168.50.171
  cloud-celeron:
    ip: 192.168.50.178
  cloud-eugene:
    ip: 192.168.50.234
```

No `env.d/` files needed — OSA ships `ceilometer.yml`, `gnocchi.yml` in `inventory/env.d/` already.

**Step 2 — Configure Gnocchi storage backend (user_variables.yml):**

Add to `/etc/openstack_deploy/user_variables.yml`:

```yaml
# Gnocchi — use Swift for metric storage (already deployed)
gnocchi_storage_driver: swift
```

The default `file` driver stores metrics on the container's local filesystem — fine for testing but fragile (data lost if container is recreated). Since Swift is already running on cloud-eugene, using it gives us durable metric storage with no extra infrastructure. The Galera indexer database is automatic.

**Step 3 — Deploy Gnocchi:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-gnocchi-install.yml
```

This creates the Gnocchi LXC container on cloud-4core, sets up the Galera database, registers the Keystone `metric` service/endpoints, configures HAProxy, and starts gnocchi-api + gnocchi-metricd.

Verify:

```bash
openstack metric status   # should show storage driver info
openstack metric list     # empty initially
```

**Step 4 — Deploy Ceilometer:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-ceilometer-install.yml
```

This:

- Creates the Ceilometer LXC container on cloud-4core (central + notification agents)
- Installs ceilometer-polling on each compute host (bare metal)
- Configures all OpenStack services' notification drivers to publish to RabbitMQ (Ceilometer's oslo.messaging listener picks them up)
- Sets up the Gnocchi publisher so metrics flow to Gnocchi

Verify:

```bash
# After a few minutes, metrics should start appearing
openstack metric list
openstack metric resource list

# Check VM metrics (after at least one polling cycle = 600 seconds)
openstack metric resource show <instance-uuid>
openstack metric measures show --resource-id <instance-uuid> cpu
```

**Step 5 — Re-run Horizon to pick up any telemetry changes:**

Note: OSA's Horizon role does **not** ship a `ceilometer-dashboard` or `gnocchi-grafana` plugin. Telemetry data is accessed via the `openstack metric` and `gnocchi` CLI commands, or by integrating with external Grafana (our Phase 14 monitoring stack has Grafana already).

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-horizon-install.yml
```

#### Secrets

Already generated in `/etc/openstack_deploy/user_secrets.yml`:

- `gnocchi_container_mysql_password`, `gnocchi_service_password`
- `ceilometer_container_db_password`, `ceilometer_service_password`, `ceilometer_telemetry_secret`, `ceilometer_oslomsg_rpc_password`

#### Ceilometer Open questions

- ~~Gnocchi storage backend~~ → **Swift.** Already deployed, durable, zero extra infrastructure. Set `gnocchi_storage_driver: swift`.
- ~~Horizon plugin?~~ → **None.** No `ceilometer-dashboard` in OSA's Horizon role. Use CLI or integrate with Grafana.
- ~~Deploy order~~ → **Gnocchi first, then Ceilometer.** Ceilometer publishes to Gnocchi, so Gnocchi must exist first.
- ~~Ceilometer compute agent~~ → **Automatic.** `metering-compute_hosts` in conf.d causes OSA to install the polling agent on each compute host as bare-metal service (not LXC). The `is_metal: true` flag in env.d handles this.

### Phase 17 — Aodh (Telemetry Alarming)

Aodh provides an alarming service that evaluates conditions against Gnocchi metrics and triggers actions (webhooks, log messages, trust-based actions). Depends on Ceilometer + Gnocchi being deployed first.

**Architecture:**

- **Aodh API** — REST API (port 8042, uWSGI behind HAProxy) for alarm CRUD.

- **Aodh evaluator** — periodically evaluates alarm rules against Gnocchi metrics, transitions alarm state (ok → alarm → insufficient data).

- **Aodh notifier** — fires actions when alarm state transitions (HTTP callback, log, trust-based actions like Heat auto-scaling).

- **Aodh listener** — listens to Ceilometer events on RabbitMQ for event-based alarms.

All four services run in a single LXC container on cloud-4core.

**OSA role:** `os_aodh` — fully automated. Uses Galera for alarm storage.

**Services created:**

| Service | Port | Type | Container |
|---|---|---|---|
| Aodh API | 8042 | `alarming` | `cloud-4core-aodh-container-*` (LXC) |
| Aodh evaluator | — | — | Same container |
| Aodh notifier | — | — | Same container |
| Aodh listener | — | — | Same container |

**Host inventory needed** (`/etc/openstack_deploy/conf.d/`):

- `metering-alarm_hosts` → cloud-4core

#### What Aodh gives us

- **Threshold alarms** — fire when a Gnocchi metric crosses a threshold (e.g., "alarm if average CPU > 80% over 5 minutes").

- **Event alarms** — fire on specific Ceilometer events (e.g., "alarm when any instance is deleted").

- **Composite alarms** — combine multiple sub-alarms with AND/OR logic.

- **Heat auto-scaling integration** — Heat's `OS::Ceilometer::Alarm` resource type creates Aodh alarms that trigger `OS::Heat::ScalingPolicy` to add/remove instances from an auto-scaling group. This is the standard OpenStack auto-scaling pattern.

#### Aodh Implementation

**Step 1 — Create conf.d host mapping:**

Create `/etc/openstack_deploy/conf.d/aodh.yml`:

```yaml
metering-alarm_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

**Step 2 — Deploy Aodh:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-aodh-install.yml
```

This creates the Aodh LXC container on cloud-4core, sets up the Galera `aodh` database, registers the Keystone `alarming` service/endpoints, configures HAProxy, and starts all four Aodh services.

**Step 3 — Verify:**

```bash
# Check Aodh API is responding
openstack alarm list   # should return empty list

# Create a test threshold alarm
openstack alarm create \
  --name test-cpu-alarm \
  --type gnocchi_resources_threshold \
  --metric cpu \
  --resource-type instance \
  --aggregation-method mean \
  --granularity 300 \
  --evaluation-periods 3 \
  --threshold 80000000000 \
  --comparison-operator gt \
  --alarm-action 'log://'

# Check alarm state
openstack alarm show test-cpu-alarm -c state -f value
# Should show "insufficient data" initially (no metrics yet matching)

# Clean up
openstack alarm delete test-cpu-alarm
```

**Step 4 — Re-run HAProxy (if needed):**

OSA's `os-aodh-install.yml` should update HAProxy automatically. If not:

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/haproxy-install.yml
```

#### Aodh Secrets

Already generated in `/etc/openstack_deploy/user_secrets.yml`:

- `aodh_container_db_password`, `aodh_service_password`, `aodh_oslomsg_rpc_password`, `aodh_oslomsg_notify_password`

### Phase 18 — Mistral Workflow Service

Mistral provides a workflow-as-a-service engine that lets users define multi-step task graphs (workflows) in a YAML-based DSL. Workflows can orchestrate OpenStack API calls, run arbitrary actions, and integrate with other services. Depends on RabbitMQ, Galera, and Keystone being deployed. Mistral can be used for CRON. Similar to AWS Step Functions.

**Links:** [User Guide](https://docs.openstack.org/mistral/2025.1/user/) · [Dashboard](https://docs.openstack.org/mistral-dashboard/latest/) · CLI: `python-mistralclient` · Horizon plugin: `mistral-dashboard`

**Architecture:**

- **Mistral API** — REST API (port 8989, uWSGI behind HAProxy) for workflow/execution/action CRUD.
- **Mistral engine** — evaluates workflow DSL, schedules tasks, manages execution state.
- **Mistral executor** — runs individual task actions (OpenStack API calls, HTTP, SSH, JavaScript, etc.).
- **Mistral notifier** — sends notifications on workflow/task state transitions via oslo.messaging.

All four services run in a single LXC container on cloud-4core.

**OSA role:** `os_mistral` — fully automated. Uses Galera for workflow/execution storage. HAProxy configured automatically.

**Services created:**

| Service | Port | Type | Container |
|---|---|---|---|
| Mistral API | 8989 | `workflowv2` | `cloud-4core-mistral-container-*` (LXC) |
| Mistral engine | — | — | Same container |
| Mistral executor | — | — | Same container |
| Mistral notifier | — | — | Same container |

**Host inventory needed** (`/etc/openstack_deploy/conf.d/`):

- `mistral-infra_hosts` → cloud-4core

#### What Mistral gives us

- **Workflow definitions** — YAML-based DSL for defining directed acyclic graphs of tasks. Supports branching, joining, error handling, retry, and time-based policies.

- **Heat integration** — Heat can trigger Mistral workflows as stack lifecycle hooks. Mistral workflows can call Heat APIs to manage stacks, enabling complex orchestration patterns.

- **Cron triggers** — schedule workflows to run on a cron expression (e.g., "every hour, clean up orphaned ports").

- **Event triggers** — execute workflows in response to Ceilometer/Aodh events (complementary to Aodh's alarm actions).

- **Standard action library** — built-in actions for OpenStack API calls (`nova.servers_create`, `neutron.create_port`, etc.), HTTP requests, SSH commands, JavaScript expressions, and email.

- **Custom actions** — Python-based action plugins for domain-specific logic.

#### Mistral Implementation

**Step 1 — Create conf.d host mapping:**

Create `/etc/openstack_deploy/conf.d/mistral.yml`:

```yaml
mistral-infra_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

**Step 2 — Create Mistral LXC container:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/lxc-containers-create.yml --limit mistral-infra_all
```

**Step 3 — Deploy Mistral:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-mistral-install.yml
```

This creates the Galera `mistral` database, registers the Keystone `workflowv2` service/endpoints (port 8989), configures HAProxy, and starts all four Mistral services (API via uWSGI, engine, executor, notifier).

**Step 4 — Re-run Horizon to enable Mistral dashboard:**

OSA's Horizon role automatically detects `mistral_all` group membership and installs `mistral-dashboard` from `opendev.org/openstack/mistral-dashboard`. The variable `horizon_enable_mistral_ui` evaluates to `true` when `groups['mistral_all']` is non-empty. Re-running Horizon installs the pip package and registers the dashboard panels.

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-horizon-install.yml
```

After this, Horizon will have a **Workflow** panel group under the Project tab with panels for Workflows, Executions, Actions, Cron Triggers, and more.

**Step 5 — Re-run utility container to pick up `python-mistralclient`:**

The utility container's client list is auto-discovered from OSA's upper constraints file — it matches `python-*client==*` patterns. `python-mistralclient===6.0.0` is already in the constraints, so re-running the utility setup installs the CLI plugin automatically.

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/utility-install.yml
```

After this, the `openstack workflow` CLI commands will be available in the utility container.

**Step 6 — Verify:**

```bash
# Check Mistral API is responding
openstack workflow list   # should return empty list (no workflows defined yet)

# Check service catalog
openstack catalog show workflowv2

# Create a test workflow
cat <<'EOF' > /tmp/test_workflow.yaml
version: '2.0'

test_echo:
  type: direct
  input:
    - message
  tasks:
    echo_task:
      action: std.echo output="<% $.message %>"
      publish:
        result: <% task().result %>
EOF

openstack workflow create /tmp/test_workflow.yaml
openstack workflow execution create test_echo '{"message": "Hello from Mistral"}'

# Check execution result
openstack workflow execution list
openstack workflow execution show <execution-id>

# Clean up
openstack workflow delete test_echo
```

**Step 7 — Update Grafana dashboard:**

Add Mistral container log queries to the existing Ceilometer, Gnocchi & Aodh Grafana dashboard (or create a separate dashboard). Add `|.*mistral.*` to the Loki container regex filters and add a "Mistral Workflow" stat panel.

#### Secrets

Already generated in `/etc/openstack_deploy/user_secrets.yml` (auto-populated by `pw-token-gen.py`):

- `mistral_galera_password` — Galera database password
- `mistral_oslomsg_rpc_password` — RabbitMQ messaging password
- `mistral_service_password` — Keystone service account password

#### Horizon dashboard integration

The `mistral-dashboard` plugin is automatically enabled by OSA's Horizon role when Mistral is deployed. The role checks:

```yaml
horizon_enable_mistral_ui: "{{ (groups['mistral_all'] is defined) and (groups['mistral_all'] | length > 0) }}"
```

When true, it adds `mistral-dashboard` to the Horizon venv pip packages. The `mistral-dashboard` plugin provides panels under **Project → Workflow** including:

- Workflows — define/upload/delete workflow definitions
- Executions — launch workflows, view execution history and state
- Tasks — inspect individual task runs within executions
- Actions — browse available actions and custom action plugins
- Cron Triggers — manage scheduled workflow runs
- Event Triggers — manage event-driven workflow triggers

#### CLI plugin

`python-mistralclient` (v6.0.0 pinned in OSA constraints) adds `openstack workflow *` commands:

- `openstack workflow list/create/delete/show`
- `openstack workflow execution create/list/show/delete`
- `openstack workflow execution input/output show`
- `openstack action definition list/show`
- `openstack cron trigger create/list/delete`

Installed automatically in the utility container when `utility-install.yml` is re-run (auto-discovered from upper constraints).

#### Deploy order summary

1. Create conf.d file (`mistral.yml`)
2. `lxc-containers-create.yml --limit mistral-infra_all` → create Mistral container
3. `os-mistral-install.yml` → Mistral API + engine + executor + notifier
4. `os-horizon-install.yml` → enable Mistral dashboard plugin
5. `utility-install.yml` → install `python-mistralclient` CLI
6. Update Grafana dashboard with Mistral log queries
7. Verify: `openstack workflow list`, `openstack catalog show workflowv2`

### Phase 19 — Implement Docker Distribution Image Repository

**Decision:** Implementing plain Docker Distribution (`registry:2`) on cloud-4core. Harbor was evaluated but rejected for now — cloud-4core is too resource-constrained for Harbor's 9 containers + PostgreSQL + Redis (~2-4 GB RAM). When cloud-4core hardware is upgraded in the future, migrate to Harbor for RBAC, Trivy scanning, and web UI.

Running Docker Distribution on cloud-4core with /dev/sdc

Current state of cloud-4core

| Resource                  | Value                                                    | Concern?                                           |
| ------------------------- | -------------------------------------------------------- | -------------------------------------------------- |
| **RAM**                   | 15 GB total, 12 GB used, 3.4 GB available                | Tight but manageable — `registry:2` uses ~30-50 MB |
| **Swap**                  | 24 GB, 15.4 GB used                                      | Heavy swap pressure already                        |
| **Root disk** (/dev/sdd2) | 117 GB, 98 GB used, **13 GB free (89%)**                 | Critical — no room for registry data here          |
| **CPU**                   | 8 threads (Xeon E31270)                                  | Fine — registry is I/O bound, not CPU              |
| **Docker**                | v29.4.0 + Compose v5.1.1, running, nearly empty (492 KB) | Ready to use                                       |
| **LXC containers**        | 28 (control plane)                                       | Already hosting everything                         |
| **/dev/sdc**              | 119.2 GB SSD, XFS, **unmounted, empty** (117 GB free)    | Perfect candidate                                  |

Why this works despite the tight system

The registry:2 container is extremely lightweight:

~30 MB RAM at idle, ~50-100 MB under load (it's a single Go binary)
Negligible CPU — serves blobs over HTTP, mostly just disk I/O
No database — metadata is stored as files alongside blobs on the filesystem
Single container — vs Harbor's 9 containers + PostgreSQL + Redis
The key insight is that the root disk problem is solved by using /dev/sdc — the registry data never touches /dev/sdd2. Docker daemon itself is only 492 KB on the root disk; the registry:2 image is ~25 MB. The registry's persistent data (all the container images) would be a bind-mounted volume on /dev/sdc.

Partition plan for /dev/sdc (119.2 GB SSD)

| Partition   | Size       | Filesystem | Mount           | Purpose                           |
| ----------- | ---------- | ---------- | --------------- | --------------------------------- |
| `/dev/sdc1` | **100 GB** | ext4       | `/srv/registry` | Docker Distribution image storage |
| `/dev/sdc2` | **~19 GB** | ext4       | `/srv/mongodb`  | MongoDB for Freezer metadata      |

Why 100 GB for the registry:

Realistic image storage estimate for your home lab:

| Image set                                                    | Compressed size |
| ------------------------------------------------------------ | --------------- |
| Magnum K8s stack (heat-container-agent, hyperkube, calico, coredns, dashboard, etcd, flannel, pause) | ~2-4 GB         |
| Multiple K8s versions (keep 2-3 versions)                    | ~6-12 GB        |
| Zun base images (if you pre-cache common ones)               | ~2-5 GB         |
| Custom project images                                        | ~5-10 GB        |
| **Realistic total**                                          | **~15-30 GB**   |
| **With generous headroom**                                   | **< 50 GB**     |

100 GB gives you 3-6x headroom over realistic usage. Container images compress aggressively (layers are gzipped), so even a large collection of images rarely exceeds 50 GB in a home lab.

Why 19 GB for MongoDB:

Freezer is a backup service — MongoDB stores only backup metadata (job definitions, session records, client registrations), not the actual backup data. MongoDB metadata for Freezer would typically be < 1 GB even with heavy use. 19 GB is extreme overkill but uses the remainder of the drive. This could also serve other future metadata needs.

Comparison: Docker Distribution on cloud-4core vs Harbor on workstation

| Factor             | registry:2 on cloud-4core                                    | Harbor on workstation                              |
| ------------------ | ------------------------------------------------------------ | -------------------------------------------------- |
| RAM impact         | ~50 MB                                                       | ~2-4 GB (9 containers + PostgreSQL + Redis)        |
| Disk               | Dedicated SSD partition                                      | Shares workstation root disk                       |
| Networking         | Already on management network (192.168.50.168) — no secondary IP needed | Needs secondary IP (.201)                          |
| Features           | No UI, no scanning, no RBAC                                  | Full UI, Trivy scanning, RBAC, audit logs          |
| Complexity         | 1 container, 1 bind mount, trivial                           | 9 containers, TLS certs, docker-compose, installer |
| Port               | 5000 (non-standard — clients need `192.168.50.168:5000`)     | 443 (standard — clean `harbor.home.local/img`)     |
| Reliability        | On a box with 89% disk usage and heavy swap                  | On a box with 58% disk and abundant RAM            |
| Magnum integration | `container_infra_prefix=192.168.50.168:5000/magnum/`         | `container_infra_prefix=harbor.home.local/magnum/` |

The real trade-off
registry:2 on cloud-4core is simpler and lighter but:

No web UI (you manage images entirely via docker push/docker pull and the HTTP API)
No vulnerability scanning (no Trivy)
Port 5000 makes client config slightly noisier
cloud-4core is already under significant memory pressure (15 GB swap used)
That said, registry:2 adds barely any load (~50 MB RAM, negligible CPU), and /dev/sdc completely sidesteps the root disk space issue. For the Magnum use case (pre-cache images locally to avoid Docker Hub rate limits), a plain registry is perfectly sufficient.

The implementation would be roughly:

```bash
# Partition sdc
sudo parted /dev/sdc mklabel gpt
sudo parted /dev/sdc mkpart registry ext4 0% 100GB
sudo parted /dev/sdc mkpart mongodb ext4 100GB 100%
sudo mkfs.ext4 /dev/sdc1
sudo mkfs.ext4 /dev/sdc2

# Mount
sudo mkdir -p /srv/registry /srv/mongodb
# Add to /etc/fstab
sudo mount /dev/sdc1 /srv/registry

# Run registry
sudo docker run -d --restart=always -p 5000:5000 \
  -v /srv/registry:/var/lib/registry \
  --name registry \
  registry:2
```

#### Future: Harbor (after cloud-4core hardware upgrade)

Harbor is a CNCF-graduated container image registry with RBAC, vulnerability scanning (Trivy), image replication, audit logs, and a web UI. It wraps Docker Distribution (registry:2) and adds enterprise features. Would be deployed via Docker Compose on the deployment workstation or on upgraded cloud-4core hardware.

**Links:** [Documentation](https://goharbor.io/docs/2.12.0/) · [Installation](https://goharbor.io/docs/2.12.0/install-config/) · [Configuration](https://goharbor.io/docs/2.12.0/install-config/configure-yml-file/) · [GitHub](https://github.com/goharbor/harbor)

**Original motivation:** Magnum K8s node boot pulls images from Docker Hub, which stalls due to rate limits / slow WAN. A local registry eliminates this. Harbor is chosen over plain `registry:2` because the cluster already has Zun (container service) and Magnum (K8s) — both benefit from RBAC, vulnerability scanning, and a browseable UI for managing images.

#### Harbor Architecture

Harbor runs as ~9 Docker Compose containers: core, portal (nginx), registry (distribution/registry:2), jobservice, redis, PostgreSQL, trivy-adapter, registryctl, and log (rsyslog). All managed by a single `docker-compose.yml` generated by the Harbor installer.

**Requirements:** Docker Engine 20.10+, Docker Compose v2, 4 CPU / 8 GB RAM recommended, 160 GB disk recommended. Ports: 443 (HTTPS UI + registry API), 80 (HTTP redirect), 4443 (Docker Content Trust, optional).

#### Host selection: deployment workstation

| Candidate | Disk free | RAM available | Docker? | Verdict |
|---|---|---|---|---|
| cloud-4core | 14 GB (89% full) | 3.5 GB (15 GB total, 22 LXC containers) | No | **Too tight** — already at capacity with control plane |
| cloud-eugene | 56 GB | Adequate | No | Compute node — adding Docker Compose here conflicts with Nova/Zun |
| **workstation** | **511 GB** (42% used) | **10 GB** (124 GB total) | **Docker + Compose v2 installed** | **Best fit** — abundant resources, Docker ready, not a cluster node |

The workstation is the deployment host, already outside the OSA-managed cluster. Running Harbor here:

- Doesn't consume cluster resources or interfere with OSA
- Has Docker Engine + Compose v2.39 already installed
- Has 511 GB free on root SSD — more than enough for image storage
- Is always on when the lab is in use (it's the admin machine)

#### Networking: dedicated management IP

Harbor needs a stable, routable IP on the management network (192.168.50.0/24) so all cluster nodes and Magnum VMs can reach it. The workstation's management NIC (`eno1`) currently gets `.210` via DHCP.

**Approach: add a secondary static IP to `eno1` via NetworkManager.**

The workstation's `eno1` is enslaved into `br-mgmt` as part of the wired connection "Wired connection 1" (DHCP, ipv4.method=auto). Adding a secondary IP:

```bash
# Add a secondary static IP to the management NIC
nmcli con modify "Wired connection 1" +ipv4.addresses "192.168.50.201/24"
nmcli con up "Wired connection 1"
```

This gives the workstation two IPs on the management network: `.210` (DHCP, general use) and `.201` (static, dedicated to Harbor). Harbor binds to `.201` so there's no port conflict with anything else on the workstation.

**Why .201?** Scan of the 192.168.50.0/24 range shows these IPs are taken:
- `.1` (router), `.168` (cloud-4core), `.171` (cloud-6core), `.178` (cloud-celeron), `.234` (cloud-eugene), `.210` (workstation)
- `.52–.252` range: 22 LXC container IPs managed by OSA (`.52`, `.54`, `.65`, `.68`, `.78`, `.79`, `.80`, `.82`, `.85`, `.86`, `.95`, `.107`, `.112`, `.115`, `.143`, `.148`, `.150`, `.163`, `.182`, `.184`, `.188`, `.200`, `.206`, `.216`, `.223`, `.235`, `.252`)
- `.87` (workstation wifi), `.111` (provider router WAN)

`.201` is confirmed free by ping scan. It's adjacent to `.200` (trove container) which is fine — no conflict.

**Alternative considered:** Running Harbor on port 5000 on the existing `.210` IP. This works but is non-standard (Docker clients default to port 443 for registries), and using a dedicated IP on standard ports (443/80) is cleaner for `docker pull harbor.local/project/image` without needing `:port` suffixes.

**DNS/hosts:** Add `harbor.home.local` → `192.168.50.201` to `/etc/hosts` on the workstation and cluster nodes (via the `prepare_target_host` role), or use bare IP. For Magnum VMs that boot on the provider network, they still need management network routing (which they have via the router).

#### Storage backend options

| Option | Pros | Cons |
|---|---|---|
| **A: Local filesystem (workstation)** | Simplest. 511 GB free. Fast SSD. No dependencies. | Only on one machine. Not HA (not needed for home lab). |
| B: Swift backend | Reuses existing Swift (3.6 TB on cloud-eugene). Distributed storage. | Adds latency for every layer push/pull. Complex config. Swift TLS certs needed. |
| C: cloud-4core sdc (120G SSD, empty, XFS) | Dedicated disk, good IOPS. | Only 117 GB free. On an already-overloaded node. Would need NFS/iSCSI export to workstation. |

**Recommended: Option A — local filesystem on the workstation.**

Harbor's `data_volume` points to a local directory (default `/data`). On the workstation with 511 GB free, this is more than sufficient. Container images compress well — a typical OpenStack Magnum image set (heat-container-agent, hyperkube, calico, coredns, dashboard, etc.) is ~5–10 GB total. Even with many additional project images, storage won't be a constraint.

Swift (Option B) is technically supported — Harbor's `storage_service` accepts Swift config directly:

```yaml
storage_service:
  swift:
    username: admin
    password: ADMIN_PASS
    authurl: https://192.168.50.168:35357/v3/auth
    tenant: admin
    domain: default
    region: RegionOne
    container: harbor_images
```

But this adds unnecessary complexity and latency. Swift is better reserved for its intended purpose (object storage, Glance backend). If storage ever becomes an issue on the workstation, Swift can be added later without data loss (Harbor supports storage migration).

#### TLS certificates

Harbor requires HTTPS in production. Options:

1. **Self-signed CA** — generate a CA, sign Harbor's cert, distribute CA to all Docker clients (cluster nodes, Magnum VMs). Docker needs the CA in `/etc/docker/certs.d/harbor.home.local/ca.crt`.

2. **Existing OpenStack PKI** — OSA already has an internal CA. Could sign Harbor's cert with the same CA, but this couples Harbor to OSA's cert lifecycle.

3. **Let's Encrypt** — not applicable (no public DNS for `192.168.50.201`).

**Recommended: self-signed CA** — simplest for a home lab. The `prepare_target_host` role can distribute the CA cert to all nodes. The Ansible role for Harbor deployment can generate the CA + cert.

#### Magnum integration

Once Harbor is running, Magnum cluster templates can use it:

```bash
# Pre-push images to Harbor
docker pull docker.io/openstackmagnum/heat-container-agent:wallaby-stable-1
docker tag docker.io/openstackmagnum/heat-container-agent:wallaby-stable-1 harbor.home.local/magnum/heat-container-agent:wallaby-stable-1
docker push harbor.home.local/magnum/heat-container-agent:wallaby-stable-1

# Set Magnum labels to use Harbor
openstack coe cluster template create k8s-harbor \
  --labels container_infra_prefix=harbor.home.local/magnum/ \
  ...
```

For images not controlled by `container_infra_prefix` (hyperkube, calico, coredns, etc.), the Magnum node's containerd must be configured with Harbor as a mirror. This is done via Magnum's `containerd_configure_registries` label or cloud-init scripts.

#### Harbor Implementation

**Step 1 — Add secondary IP to workstation:**

Codify in an Ansible role/playbook (this is a change to the deployment host, not a default Ubuntu thing, so direct application is acceptable per project rules — but codifying is cleaner):

```bash
nmcli con modify "Wired connection 1" +ipv4.addresses "192.168.50.201/24"
nmcli con up "Wired connection 1"
```

**Step 2 — Generate TLS certificates:**

```bash
# Create CA
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -sha512 -days 3650 -key ca.key -out ca.crt -subj "/CN=Harbor Home Lab CA"

# Create Harbor server cert
openssl genrsa -out harbor.home.local.key 4096
openssl req -sha512 -new -key harbor.home.local.key -out harbor.home.local.csr \
  -subj "/CN=harbor.home.local"
cat > v3ext.cnf <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=@alt_names
[alt_names]
DNS.1=harbor.home.local
IP.1=192.168.50.201
EOF
openssl x509 -req -sha512 -days 3650 -extfile v3ext.cnf \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -in harbor.home.local.csr -out harbor.home.local.crt
```

**Step 3 — Download and configure Harbor:**

```bash
# Download Harbor offline installer (latest 2.12.x)
wget https://github.com/goharbor/harbor/releases/download/v2.12.2/harbor-offline-installer-v2.12.2.tgz
tar xzf harbor-offline-installer-v2.12.2.tgz
cd harbor

# Edit harbor.yml
# hostname: harbor.home.local (or 192.168.50.201)
# https.certificate: /path/to/harbor.home.local.crt
# https.private_key: /path/to/harbor.home.local.key
# harbor_admin_password: <strong password>
# data_volume: /srv/harbor  (or /data)
# Optional: enable Trivy scanner, metrics endpoint
```

**Step 4 — Run Harbor installer:**

```bash
sudo ./install.sh --with-trivy
```

This generates `docker-compose.yml` and starts all Harbor containers.

**Step 5 — Distribute CA cert to cluster nodes:**

Add to the `prepare_target_host` role:

```yaml
- name: Create Docker certs directory for Harbor
  file:
    path: /etc/docker/certs.d/harbor.home.local
    state: directory

- name: Deploy Harbor CA certificate
  copy:
    src: harbor-ca.crt
    dest: /etc/docker/certs.d/harbor.home.local/ca.crt
```

Also add the CA to the system trust store so containerd (used by Magnum K8s nodes) trusts it.

**Step 6 — Create Harbor projects and push images:**

```bash
# Login
docker login harbor.home.local -u admin

# Create 'magnum' project in Harbor UI or API
# Push Magnum images
for img in heat-container-agent hyperkube calico-node calico-cni coredns; do
  docker pull <upstream>/$img:<tag>
  docker tag <upstream>/$img:<tag> harbor.home.local/magnum/$img:<tag>
  docker push harbor.home.local/magnum/$img:<tag>
done
```

**Step 7 — Configure Magnum to use Harbor:**

Update cluster template labels to point to Harbor for image pulls.

**Step 8 — Verify:**

```bash
# Harbor UI
curl -k https://harbor.home.local/api/v2.0/health

# Docker pull from a cluster node
ssh cloud-6core "docker pull harbor.home.local/magnum/heat-container-agent:wallaby-stable-1"

# Check Harbor dashboard at https://192.168.50.201
```

#### Codification in IaC

Since Harbor runs on the deployment workstation (not a cluster node), the Ansible playbook should:

1. **New playbook:** `playbooks/deploy_harbor.yml` — deploys Harbor on localhost
2. **New role:** `playbooks/roles/deploy_harbor/` — generates certs, downloads installer, templates `harbor.yml`, runs `install.sh`, creates systemd service for auto-start
3. **Update role:** `playbooks/roles/prepare_target_host/` — distributes Harbor CA cert to cluster nodes
4. **Inventory:** No changes needed — Harbor runs on the deployment host (localhost in Ansible terms)

The workstation secondary IP (`192.168.50.201`) is a deviation from a default Ubuntu install, so it should be codified in the deploy_harbor role (per project rules).

### Phase ?? — Adjutant Registration Service

Adjutant is a Django-based workflow framework that automates admin tasks within an OpenStack cluster — self-service project sign-ups, user invitations, password resets, role management, and quota change requests. It fills functionality gaps in Keystone by wrapping business-logic approval workflows around identity operations. Built on Django + Django-Rest-Framework, it uses Galera for task persistence and Keystone for auth.

**Links:** [Documentation](https://docs.openstack.org/adjutant/latest/) · [Features](https://docs.openstack.org/adjutant/latest/features.html) · [Configuration](https://docs.openstack.org/adjutant/latest/configuration.html) · [Dashboard](https://opendev.org/openstack/adjutant-ui) · CLI: `python-adjutantclient` (PyPI, v1.5.0) · Horizon plugin: `adjutant-ui`

**Architecture:**

- **Adjutant API** — Django REST API (port 5050, uWSGI behind HAProxy). Single service — no separate engine/worker processes like Mistral.
- **Task workflow** — Three-phase state machine: initial submission → admin approval → token submission. Not all phases are used for every task type.
- **Config format** — YAML (`/etc/adjutant/adjutant.yaml`), uses CONFspirator library (not oslo.config).

Single service runs in a single LXC container on cloud-4core.

**OSA automation:** Full automation available — `os-adjutant-install.yml` playbook, `os_adjutant` role (from `openstack-ansible-os_adjutant`), `env.d/adjutant.yml`, HAProxy group vars, Horizon auto-detection.

**Current state:** The `os_adjutant` role is **not yet installed** (not in `/etc/ansible/roles/`). The collection playbook (`adjutant.yml`) exists. The role must be fetched via `get-ansible-role-requirements.yml` before deployment.

**Services created:**

| Service | Port | Type | Container |
|---|---|---|---|
| Adjutant API | 5050 | `registration` | `cloud-4core-adjutant-container-*` (LXC) |

**Secrets needed** (3, in `user_secrets.yml` — not yet populated):

- `adjutant_galera_password` — Galera database password
- `adjutant_service_password` — Keystone service account password
- `adjutant_secret_key` — Django SECRET_KEY for session/token signing

**Host inventory needed** (`/etc/openstack_deploy/conf.d/`):

- `registration_hosts` → cloud-4core (env.d maps `registration_containers` → `adjutant_container` → `adjutant_api`)

#### What Adjutant gives us

- **Self-service sign-ups** — unauthenticated API where prospective users request a project + account. Admin approval required (configurable auto-approve). Horizon panel: "Sign Up".

- **User invitations** — project admins can invite users by email. Invitee receives a token link to set password and join the project. Horizon panel: "Project Users".

- **Role management** — project admins/mods can manage roles for users in their project. Role hierarchy is configurable (e.g., `project_admin` can assign `project_mod`, `member`, `heat_stack_owner`). Horizon panel: "Project Users".

- **Password reset** — unauthenticated self-service password reset via email token. Horizon panel: "Forgot Password".

- **Email update** — authenticated users can change their email. Confirmation sent to new address; notification sent to old address. Horizon panel: "Update Email Address".

- **Quota management** — users request quota changes between predefined size tiers (small/medium/large). Can require admin approval or auto-approve. Horizon panel: "Quota Management".

- **Audit trail** — all tasks are persisted in Galera with full state history, providing an audit log of all admin-workflow operations.

#### Email considerations

Adjutant sends emails for invitations, password resets, sign-ups, and notifications. The default email backend is `django.core.mail.backends.smtp.EmailBackend`. For a home lab without an SMTP server, options:

1. **Console backend** — `django.core.mail.backends.console.EmailBackend` — prints emails to the Adjutant container log (Loki-observable). Good for dev/testing.
2. **File backend** — `django.core.mail.backends.filebased.EmailBackend` — writes emails to files in the container. Useful for debugging.
3. **SMTP relay** — configure `adjutant_email_host` to point at an actual SMTP server (e.g., Postfix on localhost, or an external service).

For the home lab, **console backend** is recommended initially — email content will appear in container logs and be visible in Grafana via Loki. Override via `adjutant_adjutant_conf_overrides` in `user_variables.yml`.

#### CLI client note

`python-adjutantclient` (v1.5.0) is available on PyPI but is **NOT** in OSA's upper constraints file — auto-discovery by the utility container will not pick it up. It must be installed manually in the utility container after deployment, or added to the utility container's pip packages via `utility_pip_extra_packages` in `user_variables.yml`.

#### Adjutant Implementation

**Step 0 — Install the `os_adjutant` role:**

The role is defined in `ansible-role-requirements.yml` but not yet fetched. Run the role bootstrap to install it (and any other missing roles):

```bash
cd /opt/openstack-ansible
sudo openstack-ansible scripts/get-ansible-role-requirements.yml
```

This clones `os_adjutant` from `opendev.org/openstack/openstack-ansible-os_adjutant` (commit `ff967920`) into `/etc/ansible/roles/os_adjutant/`. Verify with `ls /etc/ansible/roles/os_adjutant/`.

**Step 1 — Generate secrets:**

```bash
cd /opt/openstack-ansible
sudo scripts/pw-token-gen.py --file /etc/openstack_deploy/user_secrets.yml
```

This populates `adjutant_galera_password`, `adjutant_service_password`, and `adjutant_secret_key`. Verify with `sudo grep adjutant /etc/openstack_deploy/user_secrets.yml`.

**Step 2 — Create conf.d host mapping:**

Create `playbooks/templates/openstack_deploy/conf.d/adjutant.yml.j2` and add a deploy task to `deploy_osa_config.yml`:

```yaml
---
# Adjutant (Registration) host mappings
registration_hosts:
  cloud-4core:
    ip: 192.168.50.168
```

Deploy: `ansible-playbook playbooks/deploy_osa_config.yml`

**Step 3 — Configure email backend (optional but recommended):**

Add to `user_variables.yml` (or via overrides template):

```yaml
adjutant_adjutant_conf_overrides:
  django:
    email:
      email_backend: django.core.mail.backends.console.EmailBackend
```

This sends all Adjutant emails to stdout (container log → Loki → Grafana).

**Step 4 — Create Adjutant LXC container:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/lxc-containers-create.yml --limit registration_all
```

**Step 5 — Deploy Adjutant:**

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-adjutant-install.yml
```

This creates the Galera `adjutant` database, registers the Keystone `registration` service/endpoints (port 5050), configures HAProxy, and starts the Adjutant API service (uWSGI).

**Step 6 — Re-run Horizon to enable Adjutant dashboard:**

OSA's Horizon role automatically detects `adjutant_all` group membership via `horizon_enable_adjutant_ui: "{{ (groups['adjutant_all'] is defined) and (groups['adjutant_all'] | length > 0) }}"` and installs `adjutant-ui` from `opendev.org/openstack/adjutant-ui`. Re-running Horizon installs the pip package and registers the dashboard panels.

```bash
cd /opt/openstack-ansible
sudo openstack-ansible playbooks/os-horizon-install.yml
```

After this, Horizon will have panels for: **Project Users** (invite, role management), **Sign Up**, **Forgot Password**, **Update Email Address**, and **Quota Management**.

**Step 7 — Install CLI client in utility container:**

Since `python-adjutantclient` is not in upper constraints, install manually:

```bash
# Option A: Manual pip install
ssh cloud-4core
sudo lxc-attach -n cloud-4core-utility-container-*
pip install python-adjutantclient

# Option B (preferred, survives re-runs): Add to user_variables.yml
# utility_pip_extra_packages:
#   - python-adjutantclient
# Then re-run: sudo openstack-ansible playbooks/utility-install.yml
```

**Step 8 — Update Grafana dashboard:**

Add Adjutant container log queries to the telemetry Grafana dashboard — same pattern as Ceilometer/Gnocchi/Aodh/Mistral.

**Step 9 — Verify:**

```bash
# Check Adjutant API service is running
sudo lxc-attach -n cloud-4core-adjutant-container-* -- systemctl status adjutant-api

# Check Keystone catalog
openstack catalog show registration

# Check the API responds
openstack adjutant task-list  # or: curl -k https://192.168.50.168:5050/v1/tasks/ -H "X-Auth-Token: ..."

# Test via Horizon
# Navigate to Project → Project Users, Identity → Sign Up
```

### Phase ?? — Zaqar Messaging Service

Zaqar 2025.2 (v21.0.0) is actively maintained — releases through 2026.1 exist. However, OSA has zero Zaqar automation — this will be a fully custom Ansible deployment.

Storage backend options — MongoDB is the default, but Zaqar 2025.2 also supports Swift for message storage and SQLAlchemy for management storage. Since your cluster already has both Swift and MariaDB/Galera, you could potentially skip MongoDB entirely (Option B in the plan). However, it's less tested.

8 open questions in the plan to resolve before implementing:

- MongoDB vs Swift+SQLAlchemy — MongoDB is safer, but existing infra reuse is tempting
- MongoDB version — needs MongoDB's own apt repo (not in Ubuntu repos), and AVX CPU support must be verified on cloud-4core
- Container vs bare-metal for Zaqar — LXC (consistent with OSA) vs host install (simpler)
- Container vs bare-metal for MongoDB — /dev/sdc access is easier from bare-metal
- HAProxy integration — needs to survive OSA re-runs
- WebSocket transport — probably WSGI-only for simplicity
- TLS termination — HAProxy handles it, Zaqar uses plain HTTP internally
/- dev/sdc filesystem — already xfs, may just need mount option tweaks

#### What Zaqar is

Zaqar is a multi-tenant cloud messaging and notification service (similar to AWS SQS + SNS). It provides:

- **Queues** — FIFO message queues with claim-based consumption (like SQS)
- **Subscriptions/Notifications** — push notifications to HTTP/HTTPS/email endpoints when messages arrive (like SNS)
- **Pre-signed URLs** — time-limited access tokens for queue operations without Keystone auth
- Two transport drivers: **WSGI** (HTTP REST API on port 8888) and **WebSocket** (port 9000)

Clients: `python-zaqarclient` (CLI), `zaqar-ui` (Horizon dashboard plugin)

#### Architecture for this cluster

```bash
                    ┌───────── cloud-4core ─────────┐
                    │                                │
  Tenant / CLI ──▶  │  HAProxy :8888                 │
                    │    └──▶ zaqar-server (LXC)     │
                    │           │         │          │
                    │           ▼         ▼          │
                    │    Keystone    MongoDB (LXC)   │
                    │   (existing)   /dev/sdc data   │
                    │                                │
                    └────────────────────────────────┘
```

Zaqar runs entirely on the controller (cloud-4core). No compute node involvement — it's a control-plane-only service.

#### Zaqar 2025.2 (v21.0.0) — key facts

- **Python ≥ 3.10** required (Ubuntu 24.04 ships 3.12 ✓)
- OSA has **NO Zaqar role, playbook, or conf.d template** — only a tempest plugin git reference exists. This is a fully manual deployment, codified in our own Ansible role.
- Storage backends available in 2025.2:

| Store type | MongoDB | Redis | Swift | SQLAlchemy |
|---|---|---|---|---|
| `message_store` | ✓ (default) | ✓ | ✓ | ✗ |
| `management_store` | ✓ (default) | ✓ | ✗ | ✓ |

- The old config group names `drivers:storage:*` were **removed** in 2025.2. Use `drivers:message_store:*` and `drivers:management_store:*` instead.
- Install docs are **severely outdated** (last written for Ubuntu 14.04 / Python 2.7 / Ocata). We'll follow the config reference and adapt.

#### Storage backend decision

**Option A: MongoDB for both stores** (recommended by upstream docs)

- Pro: Best tested path, single backend to manage, recommended for production
- Con: Need to install MongoDB (new dependency), manage a new database service
- MongoDB data on cloud-4core `/dev/sdc` (119.2G, currently xfs-formatted but unmounted/unused)

**Option B: Swift (messages) + SQLAlchemy (management)**

- Pro: Reuses existing Swift (cloud-eugene) and MariaDB/Galera — zero new services
- Con: Swift has higher latency for messaging, less tested for Zaqar, may not support all features (e.g., claims). The Swift message_store driver is functional but not the primary path.

**Option C: Redis for both stores**

- Pro: Very fast, lightweight
- Con: Need to install Redis, data durability concerns without careful config

**Decision:** TBD — see Open Questions below.

#### Deployment plan (once decisions are made)

**Step 0: MongoDB installation on cloud-4core**

- Mount `/dev/sdc` at `/var/lib/mongodb` (reformat to xfs with appropriate mount options, or reuse existing xfs)
- Install MongoDB Community Edition (version TBD — 7.0 LTS or 8.0)
- Single standalone instance (no replica set needed for home lab)
- Bind to `127.0.0.1` and/or management network `192.168.50.21`
- Create `zaqar` database and user with authentication

**Step 1: Zaqar LXC container on cloud-4core**

- Create a new LXC container (consistent with OSA's approach for other services)
- Alternative: install directly in the `zaqar_server` utility container or on the host
- Install Zaqar from pip (matching `stable/2025.2` branch)
- Dependencies: `pymongo`, `falcon`, `uwsgi` (or use the built-in WSGI server)

**Step 2: Zaqar configuration (`/etc/zaqar/zaqar.conf`)**

```ini
[DEFAULT]
auth_strategy = keystone
log_file = /var/log/zaqar/server.log

[drivers]
transport = wsgi
message_store = mongodb
management_store = mongodb

[drivers:message_store:mongodb]
uri = mongodb://zaqar:PASSWORD@127.0.0.1:27017/zaqar_messages
database = zaqar_messages

[drivers:management_store:mongodb]
uri = mongodb://zaqar:PASSWORD@127.0.0.1:27017/zaqar_management
database = zaqar_management

[keystone_authtoken]
www_authenticate_uri = http://192.168.50.21:5000
auth_url = http://192.168.50.21:5000
auth_type = password
project_domain_name = Default
user_domain_name = Default
project_name = service
username = zaqar
password = ZAQAR_SERVICE_PASSWORD

[drivers:transport:wsgi]
bind = 0.0.0.0
port = 8888

[signed_url]
secret_key = GENERATED_SECRET

[storage]
message_pipeline = zaqar.notification.notifier
```

**Step 3: Keystone registration**
```bash
openstack user create --domain default --password PASSWORD zaqar
openstack role add --project service --user zaqar admin
openstack service create --name zaqar --description "Messaging" messaging
openstack endpoint create --region RegionOne messaging public https://192.168.50.21:8888
openstack endpoint create --region RegionOne messaging internal http://192.168.50.21:8888
openstack endpoint create --region RegionOne messaging admin http://192.168.50.21:8888
```

**Step 4: HAProxy configuration**
- Add `zaqar_api` backend on cloud-4core's HAProxy (port 8888)
- Similar to how trove-api, designate-api, etc. are configured

**Step 5: Horizon dashboard (optional)**
- Install `zaqar-ui` plugin in the Horizon container
- Provides web UI for queue management

**Step 6: Verification**
```bash
# CLI test
openstack messaging queue create test-queue
openstack messaging message post test-queue '[{"body": {"hello": "world"}, "ttl": 300}]'
openstack messaging message list test-queue
openstack messaging queue delete test-queue
```

#### IaC approach

Since there's no OSA role, we'll create:

- `playbooks/deploy_zaqar.yml` — main playbook with multiple plays:
  1. Install and configure MongoDB on cloud-4core (mount /dev/sdc, install mongod, create DB/user)
  2. Install Zaqar in an LXC container (or on host)
  3. Register Zaqar in Keystone (user, service, endpoints)
  4. Configure HAProxy backend
  5. Optionally install zaqar-ui in Horizon
- `playbooks/roles/deploy_zaqar/` — custom role with templates for zaqar.conf, systemd service, etc.

#### Zaqar Open questions (resolve before implementing)

1. **MongoDB vs Swift+SQLAlchemy backend?**
   - MongoDB is the upstream default and best tested. But Swift + SQLAlchemy would avoid installing a new database service entirely.
   - For a home lab, is the simplicity of reusing existing infra (Option B) worth the risk of less-tested code paths?
   - Leaning toward **Option A (MongoDB)** since the user's initial suggestion was to use /dev/sdc for MongoDB.

2. **MongoDB version?**
   - MongoDB 7.0 (LTS, supported through 2027) vs 8.0 (latest)
   - Ubuntu 24.04 has no MongoDB in official repos — need MongoDB's own apt repo
   - MongoDB Community Edition requires AVX CPU support since 5.0. Need to verify cloud-4core's CPU supports AVX.

3. **Container vs bare-metal for Zaqar?**
   - OSA deploys most services in LXC containers on cloud-4core. Should Zaqar follow this pattern?
   - If LXC: need to manually create the container, set up networking, and install Zaqar inside
   - If bare-metal: simpler, but pollutes the host and is inconsistent with other services
   - Middle ground: install in an existing utility container?

4. **Container vs bare-metal for MongoDB?**
   - MongoDB needs direct access to `/dev/sdc` (or its mount point). LXC with bind-mount is possible but adds complexity.
   - Bare-metal MongoDB simplifies disk I/O and management.
   - Leaning toward **bare-metal MongoDB** with Zaqar in a container (or vice versa).

5. **HAProxy integration method?**
   - OSA manages HAProxy config via its own templates in `/etc/haproxy/conf.d/`. Adding a custom backend file needs to survive OSA re-runs.
   - Options: (a) add a custom drop-in file, (b) use `haproxy_extra_services` variable in OSA config, (c) manage HAProxy separately for Zaqar

6. **Do we need WebSocket transport?**
   - Zaqar supports both WSGI (HTTP REST) and WebSocket transports, but only one at a time
   - For basic queue/notification usage, WSGI is sufficient
   - Leaning toward **WSGI only** (simpler)

7. **TLS termination?**
   - OSA's HAProxy already handles TLS termination for other services
   - Zaqar behind HAProxy can use plain HTTP internally
   - Public endpoint should be HTTPS via HAProxy

8. **`/dev/sdc` filesystem?**
   - Currently xfs-formatted. MongoDB recommends xfs with specific mount options (`noatime,nodiratime`)
   - Reformat or just remount with correct options?

### Learning Phase

Multi-tenancy with separate projects/users

**Projects & Users:**

- Create a lab project for actual workloads
- Create a non-admin user (e.g., kevin) with member role on lab and optionally reader on admin
- Generate an openrc file for the new user (so you're not running everything as admin)
- The new project auto-gets its own default security group

**Images:**

- Upload Ubuntu 24.04 cloud image (`noble-server-cloudimg-amd64.img`) — this is a production-quality qcow2
- Optionally Debian, Alpine, or other cloud images you'd want
- Remove the test cirros image or keep it for quick smoke tests

**Flavors:**

- Create a useful set beyond `m1.tiny` — e.g., `m1.small` (1 vCPU, 2G RAM, 20G disk), `m1.medium` (2 vCPU, 4G), `m1.large` (4 vCPU, 8G)
- Size them relative to your actual compute capacity (`cloud-6core` has the most headroom)

**Quotas:**

- Set per-project limits: cores, RAM, instances, floating IPs, volumes, volume storage GB
- Prevents accidentally consuming all resources from one project

**Hardening (lower priority for home lab):**

- The ansible-hardening role is RHEL7 STIG — dead for Ubuntu 24.04
- Practical alternatives: CIS Ubuntu 24.04 benchmark tasks, or just targeted items (disable password SSH, restrict API endpoints to mgmt network, TLS everywhere — which you already have)

For a home lab behind a NAT router, this is less urgent

**Clean up:**

- Remove leftover test resources from the admin project (test-net, test-router, floating IPs, security group rules you added to default)
- Keep provider-net and provider-subnet (shared infrastructure)

The biggest value items are projects/users and images — those are what make the cloud actually usable beyond testing. Quotas and hardening are "nice to have" for a home lab.

## Button-Down

Deploy Ansible Vault for `user_secrets.yml` at rest. Decrypt at playbook runtime with `--ask-vault-pass`.

## Improve Log Coverage

### Problem

OSA 2025.2 hardcodes `use_journal = True` in every `os_*` role's `.j2` config template. All OpenStack services log to journald inside their LXC container. But Promtail only scrapes:
- **File logs** via `lxc_containers` job: globs `/var/lib/lxc/*/rootfs/var/log/**/*.log` — finds only `dpkg.log`, `bootstrap.log`, etc. Zero OpenStack service logs.
- **Host journal** via `journal` job: reads the host journal only. Container journals at `/var/lib/lxc/<container>/rootfs/var/log/journal/<machine-id>/` are never read.

**Result:** Loki has `{job="journal", "syslog", "openvswitch"}` only. No OpenStack service logs, no HAProxy request logs.

### What's Already Working

| Source | In Loki? | Query |
|--------|----------|-------|
| Host-level services (cinder-volume, nova-compute, swift-*) | Yes | `{job="journal", host="cloud-eugene", unit="cinder-volume.service"}` |
| RabbitMQ file logs (`/var/log/rabbitmq/`) | Yes (via glob) | `{job="openstack", container="rabbit-mq-container"}` |
| OVN file logs (`/var/log/ovn/`) | Yes (via glob) | `{job="openstack", container="neutron-ovn-northd-container"}` |
| Repo container Apache/GlusterFS logs | Yes (via glob) | `{job="openstack", container="repo-container"}` |

### What's Missing

| Source | Container | Root Cause |
|--------|-----------|------------|
| All containerized OpenStack services | 18 containers | `use_journal=True` hardcoded, no log files |
| Galera (MariaDB) | galera-container | `log_error` commented out, logs to journal only |
| ZooKeeper | zookeeper-container | logback.xml ROLLINGFILE appender commented out, CONSOLE-only → journal |
| HAProxy request logs | host (cloud-4core) | `log /dev/log local0` but no `option httplog`, rsyslog not routing to file |

### Implementation Plan

#### Step 1: Switch OpenStack services to file-based logging

`use_journal = True` is hardcoded in each role's `.j2` template (not a variable). But each role applies `*_conf_overrides` via `openstack.config_template.config_template` **after** rendering the template, so overrides win.

Add to `user_variables.yml.j2` a YAML anchor + per-service overrides:

```yaml
# Logging: disable journal, enable file-based logging for Promtail collection
_openstack_logging_overrides: &openstack_logging_overrides
  DEFAULT:
    use_journal: false
    use_stderr: false
    log_dir: /var/log/{{ service_name }}   # each service already has its own log_dir default

cinder_cinder_conf_overrides:
  DEFAULT:
    use_journal: false
    use_stderr: false

nova_nova_conf_overrides:
  DEFAULT:
    use_journal: false
    use_stderr: false

# ... (one per deployed service, see full list below)
```

**Deployed services needing overrides** (18 containers with hardcoded `use_journal = True`):

| Container | Override Variable | Notes |
|-----------|-------------------|-------|
| cinder-api | `cinder_cinder_conf_overrides` | |
| nova-api | `nova_nova_conf_overrides` | |
| neutron-server | `neutron_neutron_conf_overrides` | Also need `neutron_ovn_metadata_agent_ini_overrides`? |
| keystone | `keystone_keystone_conf_overrides` | |
| glance | `glance_glance_api_conf_overrides` | Also `glance_glance_cache_conf_overrides` |
| heat-api | `heat_heat_conf_overrides` | |
| octavia-server | `octavia_octavia_conf_overrides` | |
| magnum | `magnum_config_overrides` | Already has `drivers.openstack_ca_file` — must merge |
| placement | `placement_placement_conf_overrides` | |
| barbican | `barbican_config_overrides` | |
| designate | `designate_designate_conf_overrides` | |
| aodh | `aodh_aodh_conf_overrides` | |
| ceilometer | `ceilometer_ceilometer_conf_overrides` | |
| gnocchi | `gnocchi_conf_overrides` | |
| manila | `manila_manila_conf_overrides` | |
| mistral | `mistral_mistral_conf_overrides` | |
| trove-api | `trove_config_overrides` | |
| zun-api | `zun_zun_conf_overrides` | Already has `compute.host_shared_with_nova` — must merge |
| swift-proxy | `swift_swift_conf_overrides` | Swift uses its own paste logging — check if this works |
| horizon | N/A | Django app, uses `/var/log/horizon/` by default |

**Re-deploy:** Run the individual service playbooks (e.g., `os-cinder-install.yml`) or the full `setup-openstack.yml`. Each role will re-render the config and restart services.

#### Step 2: Enable galera file logging

```yaml
galera_my_cnf_overrides:
  mysqld:
    log_error: /var/log/mysql/error.log
```

**Re-deploy:** `galera-install.yml`

#### Step 3: Enable ZooKeeper file logging

ZK uses logback (not log4j). The default `logback.xml` has the ROLLINGFILE appender commented out and only uses CONSOLE (→ stdout → journal). Options:
- **Option A:** Deploy a custom `logback.xml` via a task in our `prepare_target_host` role or a new role. Uncomment ROLLINGFILE, add it to root logger, set `zookeeper.log.dir=/var/log/zookeeper`.
- **Option B:** Set ZK environment variable `ZOO_LOG_DIR=/var/log/zookeeper` and `ZOO_LOG4J_PROP=INFO,ROLLINGFILE` — but this is log4j syntax and ZK 3.8+ uses logback, so may not work.
- **Recommendation:** Option A. Deploy logback.xml template.

**Re-deploy:** `zookeeper-install.yml` (or SSH + restart for one-off fix)

#### Step 4: Fix HAProxy request logging

Current state: `log /dev/log local0` in config, `option dontlognull` in defaults, but no `option httplog`. Request logs go to syslog at `local0` facility but `/var/log/haproxy.log` only has startup messages.

Changes needed:
1. Add `option httplog` to HAProxy defaults (via OSA override variable — check `haproxy_server` role)
2. Ensure rsyslog routes `local0.*` to `/var/log/haproxy.log` (may need rsyslog config on cloud-4core host)
3. Add Promtail scrape for HAProxy request logs (the existing `haproxy` job in `promtail.yml.j2` already reads `/var/log/haproxy.log` — just needs content to appear)

#### Step 5: Collect Docker registry logs

The Docker Distribution registry on cloud-4core runs as a Docker container (not LXC) with the default `json-file` log driver. Logs live at `/var/lib/docker/containers/<id>/<id>-json.log` and are not scraped by any existing Promtail job. These logs are critical for diagnosing image pull timeouts during Magnum deployments.

Add a `docker_containers` scrape job to `promtail.yml.j2` (controller only):
- Glob: `/var/lib/docker/containers/**/*-json.log`
- Pipeline: parse Docker JSON format (`stream`, `time`, `log` fields), extract container name from path or Docker labels
- Labels: `job=docker`, `container=registry`

#### Step 6: Update Promtail config

The existing `lxc_containers` job glob (`/var/lib/lxc/*/rootfs/var/log/**/*.log`) should automatically pick up the new file logs after Step 1-3. Verify the pipeline stages correctly extract:
- `container` label from path
- `logpath` label from filename
- Consider adding `service` label extraction from filename (e.g., `cinder-api.log` → `service=cinder`)

#### Step 7: Grafana dashboards

Add panels:
- Error log stream — `{job="openstack"} |= "ERROR"` across all services
- Per-service panels — HAProxy, Galera, Heat, Magnum, Nova, Octavia, Cinder, Neutron
- HAProxy 5xx panel — catch Gateway Timeouts
- Galera error panel — `{job="openstack", container=~"galera.*"}`

### IaC Files to Modify

1. `playbooks/templates/openstack_deploy/user_variables.yml.j2` — add all `*_conf_overrides` for file logging
2. `playbooks/roles/deploy_monitoring/templates/promtail.yml.j2` — add `docker_containers` scrape job, verify/update pipeline stages
3. `playbooks/roles/deploy_monitoring/files/` or `templates/` — Grafana dashboard JSON (if codified)
4. Possibly a new ZooKeeper logback.xml template (in `prepare_target_host` or dedicated role)
5. HAProxy rsyslog config (if not handled by OSA's `haproxy_server` role)

### Execution Order

1. Add `*_conf_overrides` to `user_variables.yml.j2` and deploy via `deploy_osa_config.yml`
2. Re-run affected OSA playbooks to regenerate service configs and restart services
3. Verify file logs appear in containers: `ls /var/lib/lxc/*/rootfs/var/log/<service>/`
4. Verify Promtail picks them up: `curl localhost:9080/targets` on cloud-4core
5. Verify logs in Loki: `{job="openstack"}` query in Grafana
6. Deploy ZK logback.xml and galera override, verify
7. Fix HAProxy request logging, verify
8. Add Docker container log scraping to Promtail, redeploy, verify `{job="docker"}` in Grafana
9. Build Grafana dashboard panels

Two commands to run in sequence:

1. Galera (infrastructure — not included in setup-openstack):

```bash
env -u ANSIBLE_INVENTORY openstack-ansible playbooks/galera-install.yml --tags galera-config,galera-install 2>&1 | tee /tmp/galera-logging.log
```

2. All OpenStack services:

```bash
env -u ANSIBLE_INVENTORY openstack-ansible playbooks/setup-openstack.yml 2>&1 | tee /tmp/setup-openstack-logging.log
```

Check status (from another terminal):

```bash
# Watch the log live
tail -f /tmp/setup-openstack-logging.log

# Quick check which play is running
grep "^PLAY \[" /tmp/setup-openstack-logging.log | tail -3

# Check for failures so far
grep -c "failed=\([1-9]\)" /tmp/setup-openstack-logging.log
```

The galera run should be quick (a few minutes). The setup-openstack.yml will take a while — it runs through all deployed services. Each service will detect the changed config (use_journal override), rewrite it, and restart.

## Pushing a new Image to Docker Distribution on cloud-4core

From local workstation:

```bash
sudo docker pull docker.io/kubernetesui/dashboard:v2.0.0
sudo docker tag docker.io/kubernetesui/dashboard:v2.0.0 192.168.50.168:5050/openstackmagnum/dashboard:v2.0.0
sudo docker push 192.168.50.168:5050/openstackmagnum/dashboard:v2.0.0
```

### Cert for Docker Distribution Issues

Whether TLS is the better fix depends on what kind of cert you can realistically serve:

- If you can give the registry a cert chained to a CA the FCOS nodes already trust, then a secure registry is the cleaner design.
- If you would use a private/self-signed CA, you still have to inject CA trust into the Magnum nodes at boot. That is not much simpler than injecting "treat this registry as insecure" into containerd.

For your current setup, I would not switch to TLS just to solve this one cluster failure. The faster and smaller fix is to teach Magnum's containerd config that 192.168.50.168:5050 is an insecure registry. That directly addresses the observed failure.

A secure registry starts to make more sense if:

- You want this registry to be durable infrastructure used by Magnum, Zun, and anything else going forward.
- You are willing to codify certificate issuance plus CA distribution to the ephemeral FCOS nodes.
- You can use a stable DNS name and not just a raw IP.
- You want to stop carrying runtime-specific insecure-registry exceptions.

So my recommendation is:

- For the current unblock: use the Magnum-side insecure-registry path.
- For the longer term: move the registry to TLS, but only as a separate cleanup step with proper CA/DNS automation.
