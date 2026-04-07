# Home Cloud Planning

I want to set up a home cloud, using Openstack Ansible, on bare metal (not in Docker containers). Our goal is to create an effective infrastructure as code repo for the deployment of openstack to a home cloud cluster. These machines are also used as workstations in a computer lab, so have a desktop version of Ubuntu 24.04. It should be close to the default install. It's okay to change things directly via ssh if they involve a deviation from a default install - but if it's a change we would have to make to a default install of ubuntu 24.04, we should do so via ansible in the repo.

This cluster is for learning and experimentation — getting experience with deploying apps on OpenStack and general familiarity with OpenStack. Load will never be significant.

The first phase is to set up the core Openstack services: Nova, Neutron, Keystone, Cinder, Swift, and Horizon. The version of Openstack should be whatever recent version has Openstack Ansible scripts to install. I'm not sure if they're available yet for the most recent version (2026.1).

There are four nodes in the cloud cluster. All have Ubuntu 24.04 installed. All have SSL certificates exchanged with this workstation for use over the management network ports.

The four nodes are:

- cloud-4core.local
- cloud-6core.local
- cloud-celeron.local
- cloud-eugene.local

cloud-4core is the management node. It is the one that should have Horizon and Keystone installed. The other three are all compute nodes. cloud-celeron will eventually host a Kubernetes controller as a VM (VPS) on a compute node — not bare metal. cloud-6core and cloud-eugene will be the compute nodes configured to be in different logical zones.

There are four networks, and all nodes have connectivity with each other on all networks. This workstation only has connectivity with the mgmt and provider networks. The provider networks will need the ASUS RT-AC57U router they're connected to to have port forwarding set up for outside accessibility. This workstation has wireless wifi access to the RT-AC57U router, but not direct wired connectivity. The overlay and storage networks are provided by ethernet hubs with the four nodes connected to it.

There are a number of options for configuring network connectivity with Openstack Neutron. I want to set it up to use overlay networks with OVN and OVS, so that tenants can configure their own networking.

Details of each node are in ./INVENTORY.md

Documents for Openstack Ansible are [here](https://docs.openstack.org/openstack-ansible/latest/).

This repo can be changed in any way appropriate. It started out as an experiment in learning how to use Ansible and set up an Ansible repo.

Let's develop a plan to install, configure, setup, and be able to use an Openstack cluster on the four nodes. Let's use this file for planning.

---

## Repo Assessment

### What exists today

- `ansible.cfg` — configured with inventory at `playbooks/inventory/hosts.yml`, roles path, vault password file, custom collections path
- `playbooks/inventory/hosts.yml` — groups: `controllers` (cloud-4core), `compute` (6core, celeron, eugene), `storage` (all four)
- `playbooks/inventory/group_vars/all.yml` — `ansible_user: kevin`, SSH key auth, python3
- `playbooks/inventory/host_vars/` — each host has `server_name` only
- `playbooks/harden_host.yml` — uses `ansible-hardening` role
- `playbooks/setup_node_playbook.yml` — installs base packages (bridge-utils, debootstrap, openssh-server, tcpdump, vlan, python3)
- `playbooks/group_vars/all/vault.yml` — Ansible Vault encrypted secrets
- `collections/` — contains `containers.podman` and `webstack_builders.setup_node`
- `playbooks/roles/ansible-hardening/` — RHEL7 STIG hardening role

### What needs to change

This repo started as an Ansible learning experiment. To serve as the single source of truth for the entire OpenStack deployment it needs significant additions but the existing structure is a reasonable foundation.

**Keep as-is:**

- `ansible.cfg` (will extend, not replace)
- Existing inventory structure and SSH configuration
- Vault for secrets
- `INVENTORY.md`, `PLANNING.md`

**Obsolete (needs replacement or removal):**

- `playbooks/harden_host.yml` and `playbooks/roles/ansible-hardening/` — RHEL7 STIG role, written for CentOS 7, doesn't work with modern distros. Will need a replacement hardening approach post-deployment.

**Add:**

- Playbooks and roles for target host preparation (networking bridges, packages, kernel modules, LVM, NTP)
- Playbooks to prepare the deployment host (this workstation) — clone OSA, bootstrap Ansible
- OSA configuration file templates (`openstack_user_config.yml`, `user_variables.yml`, `user_secrets.yml`) stored in this repo and deployed to `/etc/openstack_deploy/` on this workstation
- A playbook that deploys OSA configuration and triggers the OSA installation playbooks
- A verification playbook

**Can remove later (not blocking):**

- `service-inventory-to-remove` (leftover notes file)

---

## Architecture Decisions

### OpenStack-Ansible (OSA) deployment model

OSA is cloned to `/opt/openstack-ansible` on the **deployment host** (this workstation). The deployment host only needs management network connectivity to all target hosts — it does not need to be one of the cloud nodes. Using the workstation avoids putting additional load on cloud-4core.

OSA uses its own inventory system driven by files in `/etc/openstack_deploy/`. OSA runs its own playbooks that install OpenStack services into LXC containers (or on metal) on target hosts.

**This repo's role** is to:

1. Prepare all hosts (OS-level config, networking, storage)
2. Install and configure OSA on the deployment host (this workstation)
3. Deploy the OSA configuration files to the deployment host
4. Trigger the OSA playbook runs from the deployment host
5. Run post-deployment verification and hardening

### Version target

**OpenStack 2025.2 (Flamingo)** — the current stable release with full OSA support. 2026.1 (Gazpacho) is under development and may not be stable enough. We'll use the `stable/2025.2` branch of OSA. Can upgrade later.

### Node roles (adapted for 4-node home lab)

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

**Note on cloud-4core (16GB RAM):** Running all infra services on a single node is comfortable with 16GB. LXC container overhead is small.

**Note on cloud-celeron (8GB RAM, 2C/2T):** Very limited as a compute node. Small VMs only. Future plan is to run a Kubernetes controller as a VM on one of the compute nodes (not bare metal on celeron).

### Networking architecture

The environment uses **Neutron Option 2 (Self-service networks)** with the ML2/OVN plugin. This provides full L2/L3 virtual networking — tenants can create their own virtual networks, routers, and subnets without knowledge of the underlying physical infrastructure. Overlay networks use **Geneve** tunnels.

**Key design principle:** The physical provider network has NO IP addresses assigned to the cloud nodes. It is a layer-2-only bridge (`br-vlan`) that OVN uses for north-south traffic (floating IPs, SNAT). Tenants create self-service networks on Geneve overlays. OVN routers handle NAT between tenant networks and the external (provider) network.

#### Physical networks

| Network | CIDR | Bridge | Purpose | Node IPs? |
|---|---|---|---|---|
| Management | 192.168.50.0/24 | br-mgmt | Container mgmt, API endpoints, SSH | Yes — static IPs per node |
| Overlay/Tunnel | 192.168.60.0/24 | br-vxlan | Geneve encapsulated tenant traffic (OVN) | Yes — static IPs per node |
| Storage | 192.168.70.0/24 | br-storage | Cinder, Glance, Swift traffic | Yes — static IPs per node |
| Provider/External | 192.168.2.0/24 | br-vlan | Floating IPs, SNAT for tenant VMs | **No** — layer-2 only, managed by OVN |

#### Bridge-to-interface mapping per host

| Host | br-mgmt (iface) | br-vxlan (iface) | br-storage (iface) | br-vlan (iface) |
|---|---|---|---|---|
| cloud-4core | enp12s0 (192.168.50.168) | enp6s0 (192.168.60.6) | enp11s0 (192.168.70.12) | enp7s0 (no IP) |
| cloud-6core | enp16s0 (192.168.50.171) | enp11s0 (192.168.60.10) | enp7s0 (192.168.70.10) | enp6s0 (no IP) |
| cloud-celeron | enp12s0 (192.168.50.178) | enp6s0 (192.168.60.11) | enp11s0 (192.168.70.11) | enp7s0 (no IP) |
| cloud-eugene | enp13s0 (192.168.50.234) | enp8s0 (192.168.60.13) | enp7s0 (192.168.70.13) | enp12s0 (no IP) |

#### How self-service networking works

1. **Provider network** (`physnet1` on `br-vlan`, type `flat`): Mapped to the RT-AC57U router's 192.168.2.0/24 subnet. Created by the admin as an OpenStack "external" network. OVN uses this for floating IPs and SNAT. Nodes do NOT have IPs on this network — it's purely bridged.

2. **Geneve overlay** (type `geneve`, range `1:1000` on `br-vxlan`): Carries all tenant self-service network traffic. Each tenant network gets a unique Geneve VNI. Traffic is encapsulated in Geneve tunnels between compute nodes over the 192.168.60.0/24 underlay.

3. **OVN routers**: Tenants create virtual routers that connect their self-service networks to the external provider network. OVN handles SNAT (for outbound) and DNAT (for floating IPs). Compute nodes act as OVN gateways (DVR model), so VMs can reach the external network directly through their local compute node.

#### OSA provider_networks configuration (in openstack_user_config.yml)

```yaml
provider_networks:
  - network:
      container_bridge: "br-mgmt"
      container_type: "veth"
      container_interface: "eth1"
      ip_from_q: "management"
      type: "raw"
      group_binds:
        - all_containers
        - hosts
      is_management_address: true
  - network:
      container_bridge: "br-vxlan"
      container_type: "veth"
      container_interface: "eth10"
      ip_from_q: "tunnel"
      type: "geneve"
      range: "1:1000"
      net_name: "geneve"
      group_binds:
        - neutron_ovn_controller
  - network:
      container_bridge: "br-vlan"
      container_type: "veth"
      container_interface: "eth12"
      host_bind_override: "eth12"
      type: "flat"
      net_name: "physnet1"
      group_binds:
        - neutron_ovn_controller
  - network:
      container_bridge: "br-storage"
      container_type: "veth"
      container_interface: "eth2"
      ip_from_q: "storage"
      type: "raw"
      group_binds:
        - glance_api
        - cinder_api
        - cinder_volume
        - nova_compute
        - swift_proxy
```

**Post-deployment OpenStack setup** (admin creates the external network once):

```bash
openstack network create --external --provider-network-type flat \
  --provider-physical-network physnet1 provider-net

openstack subnet create --network provider-net --subnet-range 192.168.2.0/24 \
  --gateway 192.168.2.1 --allocation-pool start=192.168.2.100,end=192.168.2.200 \
  --no-dhcp provider-subnet
```

Then tenants can:

```bash
# Create a self-service network
openstack network create my-network
openstack subnet create --network my-network --subnet-range 10.0.0.0/24 my-subnet

# Create a router connecting to external
openstack router create my-router
openstack router set --external-gateway provider-net my-router
openstack router add subnet my-router my-subnet

# Assign floating IPs
openstack floating ip create provider-net
openstack server add floating ip my-instance <floating-ip>
```

---

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

### Phase 6: Post-deployment configuration

- [ ] Create the external provider network and subnet (see networking section above)
- [ ] Find a replacement for the obsolete ansible-hardening RHEL7 STIG role, or write targeted hardening tasks for Ubuntu 24.04
- [ ] Create non-admin OpenStack projects and users
- [ ] Upload production VM images (Ubuntu cloud image, etc.)
- [ ] Configure quotas

---

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

---

## Resolved Decisions

1. **Provider network IPs:** The provider network (`br-vlan`) is layer-2 only. OVN manages it for floating IPs and SNAT. The RT-AC57U router DHCP serves 192.168.2.2 - 50 only, leaving 192.168.2.51 - 254 free. OpenStack floating IP allocation pool will use a subset (e.g., 192.168.2.100 - 200).

2. **External VIP / FQDN:** Horizon and API endpoints accessible via cloud-4core's management IP (192.168.50.168). No external access needed — this is a learning cluster. Both `internal_lb_vip_address` and `external_lb_vip_address` will be set to `192.168.50.168` in `openstack_user_config.yml`.

3. **Swift:** Deploy in Phase 4 alongside other services. cloud-eugene has `/dev/sdc` and `/dev/sdd` (2x 1.8T HDD) dedicated to Swift.

4. **Glance backend:** Local disk on cloud-4core — `/dev/sda` (128G SSD). Accessed via the storage network (192.168.70.x).

5. **cloud-celeron:** Remains a compute node. The Kubernetes controller will be a VM (VPS) on a compute node in the future, not bare metal on celeron.

6. **SSL/TLS:** Self-signed certificates using OSA's built-in PKI. The HAProxy role has a built-in self-signed CA that generates a Root CA → Intermediate CA → server certificate chain. This is sufficient for a learning cluster. Barbican (OpenStack Key Manager) is a separate service for _storing_ secrets/keys/certificates — it's not a CA itself. It could store certificates issued by an external CA, but for this cluster the HAProxy PKI is simpler and sufficient.

7. **Eugene's NVMe (`/dev/nvme0n1`, 465.8G):** NOT available for OpenStack. This is Eugene's personal drive.

8. **cloud-4core drive allocation:** All drives are now assigned: `/dev/sda` (128G SSD) = Glance, `/dev/sdb` (931.5G HDD) = Manila (future), `/dev/sdc` (128G SSD) = Trove (future), `/dev/sdd` (119.2G SSD) = Root FS. Only Glance is deployed in Phase 4; Manila and Trove are future services.

9. **Deployment host:** This workstation (not cloud-4core). The workstation has management network connectivity to all nodes, which is all OSA requires. This avoids putting additional load on cloud-4core.

10. **Hardening role:** The existing `ansible-hardening` role (RHEL7 STIG) is obsolete. It was written for CentOS 7 and hit problems during the Red Hat restructuring. Needs replacement with a modern Ubuntu 24.04 hardening approach post-deployment.

---

## Remaining Open Items

All blocking decisions are resolved. The only remaining detail is the `used_ips` configuration, which is documented below and ready to implement.

### `used_ips` — IP exclusion map for OSA

OSA auto-assigns IPs from `cidr_networks` to LXC containers and internal bridges. The `used_ips` list in `openstack_user_config.yml` tells OSA which addresses are already taken so it doesn't create conflicts. This is only relevant for the three CIDRs that OSA allocates from (management, tunnel, storage). The provider network has no `cidr_networks` entry — it's layer-2 only.

**No router configuration changes needed.** The management router (RT-AX58U) already has static assignments for the nodes. The overlay and storage networks are on dumb hubs with static IPs only — no DHCP. The provider router (RT-AC57U) DHCP range is 192.168.2.2  -  50, which doesn't overlap with the OpenStack floating IP pool (192.168.2.100  -  200).

#### Recommended `used_ips` configuration

```yaml
used_ips:
  # Management network (192.168.50.0/24)
  # Reserve .1 (router), .168/.171/.178/.234 (nodes), .210 (workstation)
  # Also reserve .1 through .50 as a general safety range for router DHCP/infra
  - "192.168.50.1,192.168.50.50"
  - "192.168.50.168"          # cloud-4core
  - "192.168.50.171"          # cloud-6core
  - "192.168.50.178"          # cloud-celeron
  - "192.168.50.210"          # workstation (deployment host)
  - "192.168.50.234"          # cloud-eugene

  # Overlay/Tunnel network (192.168.60.0/24)
  # Reserve .10-.13 (nodes). No router on this network.
  - "192.168.60.1,192.168.60.9"   # safety range
  - "192.168.60.10"           # cloud-6core
  - "192.168.60.11"           # cloud-celeron
  - "192.168.60.6"            # cloud-4core
  - "192.168.60.13"           # cloud-eugene

  # Storage network (192.168.70.0/24)
  # Reserve .10-.13 (nodes). No router on this network.
  - "192.168.70.1,192.168.70.9"   # safety range
  - "192.168.70.10"           # cloud-6core
  - "192.168.70.11"           # cloud-celeron
  - "192.168.70.12"           # cloud-4core
  - "192.168.70.13"           # cloud-eugene
```

This leaves OSA free to allocate container IPs from:

- **Management:** ~192.168.50.51 - 167, 169 - 170, 172 - 177, 179 - 209, 211 - 233, 235 - 254
- **Overlay:** ~192.168.60.14 - 254
- **Storage:** ~192.168.70.14 - 254

Plenty of room for LXC containers (a typical single-infra-node deployment creates ~15 - 20 containers).

---

## Session Log — Deployment Progress (as of 2026-04-05)

ssh kevin@mgmt.cloud-4core.local "sudo lxc-attach -n cloud-4core-utility-container-a6b0d01e -- /bin/bash -c '
> source /root/openrc
>
> echo \"=== Creating self-service network ===\"
> openstack network create test-net 2>&1
>
> echo \"=== Creating subnet ===\"
> openstack subnet create --network test-net --subnet-range 10.0.0.0/24 --dns-nameserver 8.8.8.8 test-subnet 2>&1
>
> echo \"=== Creating router ===\"
> openstack router create test-router 2>&1
>
> echo \"=== Setting external gateway ===\"
> openstack router set --external-gateway provider-net test-router 2>&1
>
> echo \"=== Adding subnet to router ===\"
> openstack router add subnet test-router test-subnet 2>&1
> '"
=== Creating self-service network ===
+---------------------------+--------------------------------------+
| Field                     | Value                                |
+---------------------------+--------------------------------------+
| admin_state_up            | UP                                   |
| availability_zone_hints   | nova                                 |
| availability_zones        |                                      |
| created_at                | 2026-04-06T23:43:48Z                 |
| description               |                                      |
| dns_domain                | None                                 |
| id                        | 84565d80-d832-45af-bec5-c7c057b643b3 |
| ipv4_address_scope        | None                                 |
| ipv6_address_scope        | None                                 |
| is_default                | False                                |
| is_vlan_qinq              | None                                 |
| is_vlan_transparent       | None                                 |
| mtu                       | 1442                                 |
| name                      | test-net                             |
| port_security_enabled     | True                                 |
| project_id                | c5a31a936e9c4da7b99d670a4d544b1b     |
| provider:network_type     | geneve                               |
| provider:physical_network | None                                 |
| provider:segmentation_id  | 12                                   |
| qinq                      | False                                |
| qos_policy_id             | None                                 |
| revision_number           | 1                                    |
| router:external           | Internal                             |
| segments                  | None                                 |
| shared                    | False                                |
| status                    | ACTIVE                               |
| subnets                   |                                      |
| tags                      |                                      |
| updated_at                | 2026-04-06T23:43:48Z                 |
+---------------------------+--------------------------------------+
=== Creating subnet ===
+----------------------+--------------------------------------+
| Field                | Value                                |
+----------------------+--------------------------------------+
| allocation_pools     | 10.0.0.2-10.0.0.254                  |
| cidr                 | 10.0.0.0/24                          |
| created_at           | 2026-04-06T23:43:53Z                 |
| description          |                                      |
| dns_nameservers      | 8.8.8.8                              |
| dns_publish_fixed_ip | None                                 |
| enable_dhcp          | True                                 |
| gateway_ip           | 10.0.0.1                             |
| host_routes          |                                      |
| id                   | 97ff1b16-aa92-40cb-a7f7-d06496639045 |
| ip_version           | 4                                    |
| ipv6_address_mode    | None                                 |
| ipv6_ra_mode         | None                                 |
| name                 | test-subnet                          |
| network_id           | 84565d80-d832-45af-bec5-c7c057b643b3 |
| project_id           | c5a31a936e9c4da7b99d670a4d544b1b     |
| revision_number      | 0                                    |
| router:external      | False                                |
| segment_id           | None                                 |
| service_types        |                                      |
| subnetpool_id        | None                                 |
| tags                 |                                      |
| updated_at           | 2026-04-06T23:43:53Z                 |
+----------------------+--------------------------------------+
=== Creating router ===
+---------------------------+--------------------------------------+
| Field                     | Value                                |
+---------------------------+--------------------------------------+
| admin_state_up            | UP                                   |
| availability_zone_hints   | nova                                 |
| availability_zones        |                                      |
| created_at                | 2026-04-06T23:43:58Z                 |
| description               |                                      |
| enable_default_route_bfd  | False                                |
| enable_default_route_ecmp | False                                |
| enable_ndp_proxy          | None                                 |
| external_gateway_info     | null                                 |
| external_gateways         | []                                   |
| flavor_id                 | None                                 |
| ha                        | True                                 |
| id                        | c73686ad-87ec-4b8f-8a80-fb32adad450e |
| name                      | test-router                          |
| project_id                | c5a31a936e9c4da7b99d670a4d544b1b     |
| revision_number           | 1                                    |
| routes                    |                                      |
| status                    | ACTIVE                               |
| tags                      |                                      |
| updated_at                | 2026-04-06T23:43:58Z                 |
+---------------------------+--------------------------------------+
=== Setting external gateway ===
=== Adding subnet to router ===

# Download on cloud-4core host, then push into the container
ssh kevin@mgmt.cloud-4core.local "curl -sL -o /tmp/cirros.img http://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img && ls -la /tmp/cirros.img && sudo cp /tmp/cirros.img /var/lib/lxc/cloud-4core-utility-container-a6b0d01e/rootfs/tmp/cirros.img"

ssh kevin@mgmt.cloud-4core.local "sudo lxc-attach -n cloud-4core-utility-container-a6b0d01e -- /bin/bash -c '
source /root/openrc
echo "=== Downloading cirros ==="
curl -sL -o /tmp/cirros.img http://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img
ls -la /tmp/cirros.img
echo "=== Creating image ==="
openstack image create --disk-format qcow2 --container-format bare --public --file /tmp/cirros.img cirros 2>&1

ssh kevin@mgmt.cloud-4core.local "sudo lxc-attach -n cloud-4core-utility-container-a6b0d01e -- /bin/bash -c '
source /root/openrc
echo "=== Launching test instance ==="
openstack server create --flavor m1.tiny --image cirros --network test-net test-instance 2>&1

(base) kevin@workstation:~/Repos/home-cloud$  ssh kevin@mgmt.cloud-4core.local "sudo lxc-attach -n cloud-4core-utility-container-a6b0d01e -- /bin/bash -c '
> source /root/openrc
> echo \"=== Creating floating IP ===\"
> openstack floating ip create provider-net -f value -c floating_ip_address 2>&1
> '"
=== Creating floating IP ===
192.168.2.174
(base) kevin@workstation:~/Repos/home-cloud$  ssh kevin@mgmt.cloud-4core.local "sudo lxc-attach -n cloud-4core-utility-container-a6b0d01e -- /bin/bash -c '
> source /root/openrc
> echo \"=== Assigning floating IP ===\"
> openstack server add floating ip test-instance 192.168.2.174 2>&1
> echo \"=== Server status ===\"
> openstack server list 2>&1
> '"
=== Assigning floating IP ===
=== Server status ===
+--------------------------------------+---------------+--------+------------------------------------+--------+---------+
| ID                                   | Name          | Status | Networks                           | Image  | Flavor  |
+--------------------------------------+---------------+--------+------------------------------------+--------+---------+
| 10714d80-c4a5-44b6-b19d-116d2f0ab0d4 | test-instance | ACTIVE | test-net=10.0.0.155, 192.168.2.174 | cirros | m1.tiny |
+--------------------------------------+---------------+--------+------------------------------------+--------+---------+
