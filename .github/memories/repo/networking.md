# Networking — Critical Notes

## STOP: Provider network (192.168.2.0/24) has NO IP on compute nodes

The provider NIC on each node (enp7s0, enp6s0, enp12s0, etc.) is a **raw L2 port** inside the OVS bridge `eth12`. It has **no IP address**. This is by design.

**DO NOT** attempt to:
- Ping 192.168.2.x from compute nodes
- Test provider network connectivity from compute nodes
- Diagnose "unreachable floating IPs" by pinging from compute nodes
- Conclude the provider network is broken because nodes can't reach it

**To test floating IP connectivity**, use:
- The workstation — it is connected to the RT-AC57U via **wifi** (`wlp7s0`, IP `192.168.2.25`)
- Or any device on the RT-AC57U's LAN (192.168.2.0/24)

**WARNING: Weak wifi signal!** The workstation's wifi connection to the RT-AC57U (provider router) is weak and has no wired alternative. When testing floating IPs and seeing high latency or packet loss, **check wifi signal first** before assuming an OpenStack issue:
```bash
# Check wifi signal strength
nmcli dev wifi list | grep AC57U
# Or:
iwconfig wlp7s0 | grep -i signal
# Check route is via wifi
ip route show | grep 192.168.2
```
Typical latency: first ping can spike to ~400ms, subsequent pings settle to ~7-80ms. This is normal for the weak wifi link.

## How provider networking works (OVN + flat physnet1)

1. The physical NIC is enslaved to an OVS bridge (`eth12` mapped to `physnet1`)
2. The NIC operates in L2/promiscuous mode — it forwards frames but has no IP
3. OVN creates logical router ports with floating IPs (192.168.2.x) as NAT rules
4. The OVN gateway chassis (typically cloud-eugene) handles the actual NAT
5. Traffic flow: external → RT-AC57U LAN → physical NIC → OVS bridge → OVN logical router → VM

The **overlay/Geneve tunnels** run on the **overlay network** (192.168.60.0/24), NOT on the provider network. Each node has an overlay IP (e.g., cloud-6core: 192.168.60.10).

## Networks summary

| Network | Subnet | Purpose | IPs on nodes? |
|---------|--------|---------|---------------|
| Management | 192.168.50.0/24 | SSH, API endpoints, LXC | Yes |
| Provider | 192.168.2.0/24 | Floating IPs, flat physnet1 | **NO** |
| Overlay | 192.168.60.0/24 | Geneve tunnels between nodes | Yes |
| Storage | 192.168.70.0/24 | Cinder/Swift traffic | Yes |
