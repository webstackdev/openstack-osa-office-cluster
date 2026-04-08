# Home Cloud

9 OpenStack services registered (Keystone, Glance, Nova, Neutron, Cinder, Swift, Heat, Horizon, Placement)
3 compute nodes (cloud-6core, cloud-celeron, cloud-eugene) — all enabled / up
6 OVN agents (3 Controller Gateway + 3 Metadata) — all `:-)` / UP

## Contributions

he barbican-ui package is essentially a scaffolding project — the panel group (_90) sets PANEL_GROUP_DASHBOARD = 'barbican', which refers to a top-level dashboard slug barbican that doesn't exist. Normal Horizon plugins register under PANEL_GROUP_DASHBOARD = 'project' to appear in the Project tab. Since there's no barbican dashboard defined, the panel silently goes nowhere.

This is consistent with the OSA defaults comment that said barbican-ui "does not provide any functionality at this time" and why horizon_enable_barbican_ui defaults to false. The project has only 13 commits and its README says "Features: TODO".

Bottom line: The barbican-ui package is not functional — it's an incomplete scaffolding. There is no working Barbican Horizon plugin at this point. The Barbican team hasn't built out the UI. You can manage secrets via the CLI (openstack secret store/list/get/delete), which is the standard approach.

## Node roles (adapted for 4-node home lab)

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

## Future Work

### Phase 6 — Observability (Loki + Prometheus + Grafana)

**Goal:** Centralized logging and metrics for all cluster nodes and LXC containers, queryable from a single Grafana instance on cloud-4core.

**Current state:** Logs are scattered across cloud-4core's 16 LXC containers (`/var/log/nova/`, `/var/log/neutron/`, etc.), plus HAProxy / host syslog on each node, and nova-compute / OVN / OVS logs on the three compute nodes.

#### Architecture

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

#### Implementation Plan

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

#### Versions (pinned)

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

### Phase 8 — Install Barbican Key Manager

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

#### What OSA handles automatically

- LXC container creation and networking
- Galera database and user
- RabbitMQ vhost and user
- Keystone service catalog registration (service type `key-manager`, port 9311)
- HAProxy frontend/backend on VIP port 9311 (SSL-terminated)
- `barbican.conf` with simple_crypto plugin and KEK from `user_secrets.yml`
- Systemd services for API, worker, and Keystone listener

#### No custom env.d or conf.d needed

Unlike Cinder (which needed a `env.d/cinder.yml` override for bare-metal LVM), Barbican runs entirely inside its LXC container with no host-level dependencies. The built-in `env.d/barbican.yml` mapping is sufficient.

### Phase 9 — Playbook for Openstack CLI on this workstation

- Install Openstack CLI on this workstation (it's already installed, just need to scaffold it IaC)
- Install python-heatclient (already installed, again just IaC)
- Install python-barbicanclient

### Phase 10 — Updates to Horizon

Need to make sure we install plugins to Horizon for all of the services we add that aren't default:

- openstack-dashboard-heat-partition
- barbican-ui

### Phase 11 — Manila Shared File Systems service

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

#### Implementation Steps

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

### Phase 12

(**Designate**) DNS service [(install guide)](https://docs.openstack.org/designate/2025.1/install/) [(user guide)](https://docs.openstack.org/designate/2025.1/user/) [(dashboard)](https://opendev.org/openstack/designate-dashboard) - `python-designateclient`, `designate-dashboard` or `openstack-designate-ui`

### Last Phase

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

### Phase X - Magnum and Zun

Your current setup can only launch VMs (KVM/QEMU) via Nova. There's no container workload support deployed.

OpenStack offers two paths for tenant containers:

**Zun** — Container as a Service. The most direct equivalent of what you're asking. Tenants run openstack appcontainer run --image docker.io/nginx zun-nginx and it launches a Docker/Podman container on compute nodes, managed like a Nova instance (gets a Neutron port, security groups, etc.). Think of it as "Nova but for containers."

**Magnum** — Kubernetes/Docker Swarm cluster as a Service. Tenants create entire Kubernetes clusters (openstack coe cluster create ...) which are themselves a set of Nova VMs running k8s. Then the tenant uses kubectl to deploy containers within that cluster. More heavyweight — you're running VMs that run containers.

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

## Octavia with Magnum

Is Octavia required for Magnum?

It depends on the cluster template's configuration:

With Octavia (default for production): Magnum places an Octavia load balancer in front of the k8s API server. If you have multiple masters (HA), this is how clients reach the API. Octavia is listed as a Magnum dependency in most deployment guides.

Without Octavia: For single-master clusters, you can configure the template to skip the LB and point directly at the master VM's IP. Some drivers support master_lb_enabled: false.

For your lab with a single master, you could skip Octavia. But it's one more thing to configure correctly, and Octavia itself is a non-trivial deployment (it launches "amphora" VMs that run HAProxy — VMs inside VMs).

Control plane VMs. The Octavia load balancer sits in front of the Kubernetes API server (kube-apiserver), which only runs on control plane nodes. When you have multiple control plane nodes for HA, kubectl needs a single endpoint to reach any of them — that's what the Octavia LB provides (a VIP that balances across the API servers on each control plane VM).

Worker nodes don't run kube-apiserver, so they're not behind the LB. Workers connect to the LB as clients (kubelet → LB VIP → kube-apiserver).

With a single control plane node (your likely lab setup), the LB is redundant — kubectl can just point directly at that one node's IP, which is why master_lb_enabled: false works for single-master clusters.
