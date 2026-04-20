# Home Cloud

Infrastructure-as-code for a 4-node OpenStack private cloud built with [OpenStack-Ansible](https://docs.openstack.org/openstack-ansible/latest/) (OSA) on Ubuntu 24.04 desktop workstations.

## What This Is

A fully functional OpenStack deployment running on commodity desktop hardware in a home lab — no enterprise switches, no VLANs, no dedicated server hardware. The nodes double as workstations; OSA is layered on top of stock Ubuntu 24.04 desktop installs.

The Ansible playbooks in this repo handle everything outside of OSA itself: host preparation, network bridge configuration, storage provisioning, container image mirroring, and a full observability stack.

## Cluster Architecture

| Role | Host | Hardware |
|---|---|---|
| Controller (all control plane services) | cloud-4core | Xeon E31270, 16 GB DDR3 |
| Compute + OVN Gateway | cloud-6core | i5-10400F, 32 GB DDR4 |
| Compute + OVN Gateway | cloud-celeron | Pentium G3250, 8 GB DDR3 |
| Compute + Storage (Cinder LVM, Swift) | cloud-eugene | Ryzen 5 2600X, 32 GB DDR4 |

A separate workstation serves as the Ansible deployment host.

**OpenStack version:** 2025.2 (Flamingo)

**Services deployed:** Keystone, Glance, Nova, Neutron (ML2/OVN), Cinder, Swift, Heat, Horizon, Placement, Magnum, Ceilometer

## Networking

Four isolated networks, each on a dedicated physical NIC per node, connected via unmanaged switches:

| Network | Subnet | Purpose |
|---|---|---|
| Management | `192.168.50.0/24` | API endpoints, LXC container traffic, SSH, Horizon |
| Overlay | `192.168.60.0/24` | Geneve-encapsulated tenant traffic between compute nodes |
| Storage | `192.168.70.0/24` | Cinder iSCSI, Swift replication, Glance image transfers |
| Provider | `192.168.2.0/24` | Flat external network for floating IPs (separate physical router) |

**No VLANs.** Each network is physically separated at the NIC/switch level. The overlay network uses **Geneve tunnels** managed by OVN — tenant VMs get full self-service networking (virtual routers, subnets, security groups, floating IPs) without any L2 trunking configuration.

The provider network NICs carry no IP addresses — they are raw L2 ports bridged into OVS (`br-vlan`). A dedicated consumer router on the provider subnet handles upstream NAT for floating IPs.

On the management network, the RT-AX58U router is also the DNS resolver and has host overrides for `openstack-office-cluster.cloud` names (for example, `mgmt.openstack-office-cluster.cloud` -> `192.168.50.168`). The Magnum `k8s-calico` template is configured with `dns_nameserver=192.168.50.1` so Fedora CoreOS cluster nodes can resolve these internal names.

All compute nodes act as **OVN distributed gateways** (DVR), so north-south traffic egresses directly from the node hosting the VM rather than hairpinning through the controller.

## What the Playbooks Do

```
playbooks/
├── prepare_target_hosts.yml      # Packages, kernel modules, sysctl, NTP, SSH cert auth
├── prepare_deployment_host.yml   # Clone OSA, bootstrap Ansible on deployment host
├── deploy_osa_config.yml         # Template and deploy /etc/openstack_deploy/ configs
├── run_osa_deploy.yml            # Execute the OSA playbook sequence
├── verify_openstack.yml          # Post-deploy smoke tests
├── deploy_monitoring.yml         # Prometheus, Loki, Grafana, Promtail, node_exporter
├── deploy_registry.yml           # Docker Distribution registry for Magnum images
└── deploy_trove.yml              # DBaaS setup (Trove)
```

### Host Preparation

The `prepare_target_host` role bridges the gap between a stock Ubuntu 24.04 desktop and an OSA-ready node:

- **NetworkManager coexistence** — OSA assumes systemd-networkd, but these are desktop machines running NetworkManager. Bridge interfaces (`br-mgmt`, `br-vxlan`, `br-storage`, `br-vlan`) are configured via Netplan with the NetworkManager renderer.
- **SSH certificate authentication** — nodes use an ed25519 user CA and host CA. OSA's `ssh_keypairs` role adds its own RSA CA; the `prepare_target_host` role ensures both CAs coexist in `/etc/ssh/trusted_ca.d/`.
- **Host-level service log directories** — OSA deploys some services (ceilometer-polling, neutron-ovn-metadata-agent, cinder-volume) directly on compute hosts but doesn't always create their log directories. The role creates them proactively from per-host variable definitions.
- **Logrotate fixes** — prevents logrotate from creating rotated files with root ownership when the service runs as a non-root user (e.g., neutron).

### Monitoring Stack

Deployed via the `deploy_monitoring` role:

- **Prometheus** + **node_exporter** — system metrics from all 4 nodes
- **Loki** + **Promtail** — centralized log aggregation from systemd journals and OpenStack service logs (including LXC container logs via bind-mount glob patterns)
- **Grafana** — pre-provisioned dashboards: node overview, OpenStack service logs, operations dashboard, Ceilometer/Gnocchi metrics

### Container Image Registry

A Docker Distribution (registry:2) instance on the controller serves container images to Magnum Kubernetes clusters. The `deploy_registry` role also configures the controller's Docker daemon to trust the controller management IP on port `5050` as an insecure registry endpoint, so the mirror workflow survives a clean rebuild. A [mirror script](scripts/mirror-magnum-images.sh) pulls required images from upstream registries (registry.k8s.io, quay.io, docker.io) and pushes them under a unified `openstackmagnum/` namespace.

Run the mirror script from the controller after [playbooks/deploy_registry.yml](playbooks/deploy_registry.yml) completes.

## Storage

| Backend | Device | Host | Capacity |
|---|---|---|---|
| Cinder LVM | `/dev/sde` (SSD) | cloud-eugene | 477 GB |
| Swift (2 replicas) | `/dev/sdc`, `/dev/sdd` (HDD) | cloud-eugene | 2 × 1.8 TB |
| Glance images | `/dev/sda` (SSD) | cloud-4core | 128 GB |
| Nova ephemeral | HDD per compute node | cloud-6core, cloud-eugene | 932 GB each |

## Kubernetes (Magnum)

The cluster template (`k8s-calico`) provisions Fedora CoreOS VMs with:

- **Calico** networking with NetworkPolicy enforcement
- **Cinder CSI** for persistent volumes
- **OpenStack Cloud Controller Manager** for load balancer and node lifecycle integration
- **containerd** runtime
- All images served from the local registry (no external pulls during bootstrap)

## Terraform

A [test stack](terraform/test-stack/) provisions a tenant network, router, security groups, and a VM with a floating IP — used for validating the OpenStack deployment end-to-end.

## Project Structure

```
├── playbooks/
│   ├── inventory/            # Ansible inventory, host_vars, group_vars
│   ├── roles/                # Host prep, networking, storage, monitoring, registry
│   └── templates/            # OSA config templates (openstack_user_config, user_variables)
├── scripts/                  # Operational scripts (image mirroring)
├── terraform/                # OpenStack resource provisioning
├── collections/              # Vendored Ansible collections
├── INVENTORY.md              # Hardware specs, network topology, block devices
└── PLANNING.md               # Architecture decisions and OSA role mapping
```

## Requirements

- 4 machines with 4+ NICs each (or fewer nodes — adjust the inventory)
- Ubuntu 24.04 (desktop or server)
- 4 unmanaged switches/hubs (one per network) or a managed switch with VLANs
- A separate router for the provider network (or a direct upstream connection)
- [OpenStack-Ansible](https://docs.openstack.org/openstack-ansible/latest/) cloned to `/opt/openstack-ansible` on the deployment host
