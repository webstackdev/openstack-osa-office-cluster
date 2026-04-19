# Hardware Specifications

Liam Li A3-mATX Case

- 2 × 2.5" SSD on PSU mounting plate
- 1 × 2.5" SSD or 1 × 3.5" HDD at bottom of chassis

## Network Topology

```bash
ISP (94.26.168.70)
  │ WAN
RT-AX58U (LAN: 192.168.50.1) ← management router
  │ LAN ports → unmanaged hub
  ├── workstation (.210)
  ├── cloud-4core (.168)     ← Heat API, Keystone, etc.
  ├── cloud-6core (.171)
  ├── cloud-celeron (.178)
  ├── cloud-eugene (.234)
  └── RT-AC57U WAN (.111)    ← provider router
        │ LAN (192.168.2.1)
        └── provider flat network (physnet1)
```

Add a route on workstation to the provider network:

```bash
sudo ip route add 192.168.2.0/24 via 192.168.50.111
```

The physical underlying interface for a provider network (such as one used for Geneve encapsulation) typically does not have an IP address assigned to it in the host's operating system.

In an OpenStack configuration using Geneve (standard for OVN-based deployments), the networking works through two distinct layers:

1. The Overlay Interface (Encapsulation IP)

While the physical interface itself remains unaddressed to act as a Layer 2 bridge, your compute and controller nodes still require an Encapsulation IP assigned to a separate management or tunnel interface (often referred to as the local_ip or OVN Encap IP).

- This IP is used to establish the Geneve tunnels between nodes.

- This address is typically assigned to a virtual bridge (like br-phy or a management interface) rather than the raw physical NIC dedicated to provider traffic.

2. The Provider Interface (Tenant-Configurable)

For the specific interface that bridges your physical network to the virtual environment:

- No IP Address: The physical NIC (e.g., eth1) should have no IP address assigned by the OS. It is often placed in promiscuous mode so it can pass all traffic to the virtual bridge (like br-ex or br-provider).

- Bridge Mappings: You must map this physical interface to an Open vSwitch (OVS) bridge in your configuration (e.g., bridge_mappings = physnet1:br-ex).

- Tenant Configuration: When a tenant creates a network on this provider segment, OpenStack handles the virtual IP assignments within that network's subnet. The physical host remains unaware of these tenant IPs.

Summary Table

Interface Type | IP Address Required? | Purpose |
| --- | --- | --- |
| Physical NIC | No | Acts as a raw pipe for L2 traffic into the OVS bridge. |
| Encapsulation/Tunnel Interface | Yes | Used by OVN/Neutron to send Geneve-encapsulated traffic between hosts. |
| Virtual Bridge (e.g., br-ex) | Optional | Only needs an IP if the host itself needs to communicate on that specific provider network (e.g., for management). |

## Hosts config

1. RT-AX58U Management Network

- 192.168.50.1   mgmt.router.local
- 192.168.50.210  mgmt.workstation.local
- 192.168.50.171  mgmt.cloud-6core.local
- 192.168.50.178  mgmt.cloud-celeron.local
- 192.168.50.168  mgmt.cloud-4core.local
- 192.168.50.234  mgmt.cloud-eugene.local

2. RT-AC57U Provider Network

- 192.168.2.1   provider.router.local
- provider.cloud-6core.local
- provider.cloud-celeron.local
- provider.cloud-4core.local
- provider.cloud-eugene.local

3. Overlay Network

- 192.168.60.10  overlay.cloud-6core.local
- 192.168.60.11  overlay.cloud-celeron.local
- 192.168.60.6   overlay.cloud-4core.local
- 192.168.60.13  overlay.cloud-eugene.local

4. Storage Network

- 192.168.70.10  storage.cloud-6core.local
- 192.168.70.11  storage.cloud-celeron.local
- 192.168.70.12  storage.cloud-4core.local
- 192.168.70.13  storage.cloud-eugene.local

## Nodes

### mgmt.cloud-4core.local

#### mgmt.cloud-4core.local Specs

| Component | Make | Model | Spec |
| --- | --- | --- | --- |
| Motherboard | ASUS | P8H61-MX | 1 x PCIe x16, 1 x PCIe x4, 1 x PCIe x1 (1 free)<br />Wake-on-LAN, PXE, PME Wake Up, WOR by Ring |
| CPU | Intel | Xeon E31270 | 4C / 8T 3.40GHz |
| GPU | Gigabyte | GeForce GT 730 | 1 GB |
| RAM | --- | DDR3 1133 MHz | 16 GB |

#### mgmt.cloud-4core.local Block devices

4 x SATA 3.0 Gb/s connectors

Three free drives to be used for Glance image service, for Manila NFS, and for Trove database service.

```bash
sda    128G     SSD disk (Glance)
sdb    931.5G   HDD disk (Manila - LVM)
sdc    128G     SSD disk (MongoDB)
sdd    119.2G   SSD disk (Root FS)
```

#### mgmt.cloud-4core.local Networking configuration

| Device  | MAC Address       | IPv4 Address   | Network Type |
| ------- | ----------------- | -------------- | ------------ |
| enp6s0  | 00:e0:4c:68:07:3a | 192.168.60.6   | Overlay      |
| enp7s0  | 00:e0:4c:68:07:3b |                | Provider     |
| enp10s0 | 00:e0:4c:68:07:3c |                | **unused**   |
| enp11s0 | 00:e0:4c:68:07:3d | 192.168.70.12  | Storage      |
| enp12s0 | 54:04:a6:c4:11:ca | 192.168.50.168 | Mgmt         |

### mgmt.cloud-eugene.local

#### mgmt.cloud-eugene.local Specs

| Component | Make | Model | Spec |
| --- | --- | --- | --- |
| Motherboard | Gigabyte | X570 GAMING X |1 x PCIe x16, 1 x PCIe x4@16, 3 x PCIe x1 (3 free)<br />Wake-on-LAN, PXE |
| CPU | AMD | Ryzen 5 2600X | 6C / 12T 3.60GHz |
| GPU | Gigabyte | GeForce GTX 1060 | 6GB |
| RAM | --- | DDR4 2400 MHz | 32 GB |

#### mgmt.cloud-eugene.local Block devices

- 6 x SATA 6Gb/s connectors
- 2 x M.2 Socket 3 connectors

```bash
nvme0n1    465.8G    NVMe PCIe v3 disk (Eugene's home drive)
sda        931.5G    HDD disk (Ephemeral)
sdb        111.8G    SATA NVMe disk (Root FS)
sdc        1.8T      HDD disk (Swift)
sdd        1.8T      HDD disk (Swift)
sde        476.9G    SSD disk (Cinder)
```

#### mgmt.cloud-eugene.local Networking configuration

| Device  | MAC Address       | IPv4 Address   | Network Type |
| ------- | ----------------- | -------------- | ------------ |
| enp7s0  | 00:e0:4c:68:1d:ed | 192.168.70.13  | Storage      |
| enp8s0  | 00:e0:4c:68:1d:ee | 192.168.60.13  | Overlay      |
| enp11s0 | 00:e0:4c:68:1d:ef |                | **unused**   |
| enp12s0 | 00:e0:4c:68:1d:f0 |                | Provider     |
| enp13s0 | b4:2e:99:3c:bc:40 | 192.168.50.234 | Mgmt         |

### mgmt.cloud-6core.local

#### mgmt.cloud-6core.local Specs

| Component | Make | Model | Spec |
| --- | --- | --- | --- |
| Motherboard | Gigabyte | H510M H V2 |1 x PCIe x16, 1 x PCIe x1 (0 free)<br />Wake-on-LAN, PXE |
| CPU | Intel | i5-10400F | 6C / 12T 2.90GHz |
| GPU | AMD | Radeon RX 560 | 6GB |
| RAM | --- | DDR4 2133 MHz | 32 GB |

#### mgmt.cloud-6core.local Block devices

```bash
sda    223.6G   SSD disk (Root FS)
sdb    931.5G   HDD disk (Ephemeral)
```

#### mgmt.cloud-6core.local Networking configuration

| Device  | MAC Address       | IPv4 Address   | Network Type |
| ------- | ----------------- | -------------- | ------------ |
| enp6s0  | c4:62:37:06:62:34 |                | Provider     |
| enp7s0  | c4:62:37:06:62:35 | 192.168.70.10  | Storage      |
| enp10s0 | 1c:fd:08:7f:fd:b4 |                | **unused**   |
| enp11s0 | c4:62:37:06:62:36 | 192.168.60.10  | Overlay      |
| enp16s0 | 10:ff:e0:6a:1a:d0 | 192.168.50.171 | Mgmt         |

### mgmt.cloud-celeron.local

#### mgmt.cloud-celeron.local Specs

| Component | Make | Model | Spec |
| --- | --- | --- | --- |
| Motherboard | ASUS | H81M-C |1 x PCIe x16, 2 x PCIe x1 (2 free)<br />Wake-on-LAN, PXE, PME Wake up |
| CPU | Intel | Pentium G3250 | 2C / 2T 3.20GHz |
| iGPU | Intel | Xeon E3-1200 | --- |
| RAM | --- | DDR3 1400 MHz | 8 GB |

#### mgmt.cloud-celeron.local Block devices

```bash
sdb    223,6G   HDD disk (Root FS)
sda    465,8G   HDD disk (Ephemeral)
```

#### mgmt.cloud-celeron.local Networking configuration

| Device  | MAC Address       | IPv4 Address   | Network Type |
| ------- | ----------------- | -------------- | ------------ |
| enp6s0  | 1c:fd:08:78:a2:71 | 192.168.60.11  | Overlay      |
| enp7s0  | 1c:fd:08:78:a2:72 |                | Provider     |
| enp10s0 | 1c:fd:08:78:a2:73 |                | **unused**   |
| enp11s0 | 1c:fd:08:78:a2:74 | 192.168.70.11  | Storage      |
| enp12s0 | f0:79:59:91:d2:cb | 192.168.50.178 | Mgmt         |

## Topology for Self Service Networks

![image-20250621034340176](/home/kevin/.config/Typora/typora-user-images/image-20250621034340176.png)

## Containers Running on `cloud-4core`

22 LXC containers (all control plane services). cloud-4core has 16 GB RAM, 8 threads (Xeon E31270).

| Container | Service | Memory | Purpose |
|---|---|---|---|
| neutron-server-container | Neutron API (16 uWSGI workers) | 3,628 MB | Network API + ML2/OVN plugin |
| nova-api-container | Nova API, conductor, scheduler, novncproxy | 1,772 MB | Compute API + orchestration |
| zun-api-container | Zun API + wsproxy | 1,555 MB | Container service API |
| octavia-server-container | Octavia API, worker, health-manager, housekeeping | 1,269 MB | Load Balancer as a Service |
| keystone-container | Keystone (uWSGI) | 836 MB | Identity / auth |
| heat-api-container | Heat API + engine | 771 MB | Orchestration |
| rabbit-mq-container | RabbitMQ (beam.smp) | 717 MB | Message broker (oslo.messaging RPC) |
| horizon-container | Horizon (Apache + mod_wsgi) | 674 MB | Web dashboard |
| placement-container | Placement API (uWSGI) | 595 MB | Resource tracking |
| designate-container | Designate API + central + worker + producer + mdns | 414 MB | DNS as a Service |
| trove-api-container | Trove API + conductor + taskmanager | 374 MB | Database as a Service |
| cinder-api-container | Cinder API + scheduler | 354 MB | Block Storage API |
| galera-container | MariaDB (Galera single-node) | 246 MB | Database for all services |
| glance-container | Glance API (uWSGI) | 204 MB | Image service |
| manila-container | Manila API + scheduler | 178 MB | Shared Filesystems API |
| zookeeper-container | Apache ZooKeeper (Java) | 175 MB | Designate coordination backend |
| barbican-container | Barbican API (uWSGI) | 72 MB | Key Manager |
| swift-proxy-container | Swift proxy-server | 62 MB | Object Storage proxy |
| repo-container | OSA package repository | 58 MB | Internal pip/apt repo for LXC builds |
| neutron-ovn-northd-container | OVN northd | 35 MB | OVN control plane daemon |
| memcached-container | Memcached | 29 MB | Caching (Keystone tokens, etc.) |
| utility-container | OSA utility (CLI tools) | 12 MB | Admin shell / openstack client |

## Resource Planning

Initial deployments had default number of uWSGI worker threads. Tuned to lower values for a home cloud.

| Service | Current | Recommended | Rationale |
|---|---|---|---|
| Heat | 16 | 4 | Two uWSGI apps (api + cfn) both get this. Heat is rarely active. Should save ~500 MB. |
| Keystone | 16 | 4 | Token validation is fast; 4 is plenty. Should save ~600 MB. |
| Neutron | 16 | 4 | Biggest hog. 4 workers easily handles your load. Should save ~2.4 GB. |
| Nova | 16 | 4 | Two uWSGI apps (compute + metadata) both get this. Should save ~1 GB. |
| Octavia | 8 | 2 | ~0.8 GB |
| Placement | 8 | 4 | Already lower; halving still saves ~300 MB. |
| Trove API | 8 | 2 | trove_api_workers	~0.1 GB |
| Trove conductor | 8 | 2 | trove_conductor_workers	~0.1 GB |
| Zun | 16 | 2 | ~1.1 GB |
