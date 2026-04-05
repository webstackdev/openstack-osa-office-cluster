# Hardware Specifications

Nova, Neutron, Keystone, Cinder, Swift

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
- 192.168.60.12  overlay.cloud-4core.local
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
sdb    931.5G   HDD disk (Manila)
sdc    128G     SSD disk (Trove)
sdd    119.2G   SSD disk (Root FS)
```

#### mgmt.cloud-4core.local Networking configuration

| Device  | MAC Address       | IPv4 Address   | Network Type |
| ------- | ----------------- | -------------- | ------------ |
| enp6s0  | 00:e0:4c:68:07:3a | 192.168.60.12  | Overlay      |
| enp7s0  | 00:e0:4c:68:07:3b |                | Provider     |
| enp10s0 | 00:e0:4c:68:07:3c |                | **unused**   |
| enp11s0 | 00:e0:4c:68:07:3d | 192.168.70.12  | Storage      |
| enp12s0 | 54:04:a6:c4:11:ca | 192.168.50.168 | Mgmt         |

### mgmt.cloud-eugene.local

#### mgmt.cloud-eugene.local Specs

| Component | Make | Model | Spec |
| --- | --- | --- | --- |
| Motherboard | Gigabyte | X570 GAMING X |1 x PCIe x16, 1 x PCIe x4@16, 3 x PCIe x1 (3 free)<br />Wake-on-LAN, PXE|
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
| Motherboard | Gigabyte | H510M H V2 |1 x PCIe x16, 1 x PCIe x1 (0 free)<br />Wake-on-LAN, PXE|
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
| Motherboard | ASUS | H81M-C |1 x PCIe x16, 2 x PCIe x1 (2 free)<br />Wake-on-LAN, PXE, PME Wake up|
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
