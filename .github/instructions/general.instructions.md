---
applyTo: "**"
---

# Home Cloud — General Instructions

## Project Goal

This repo is infrastructure-as-code for deploying OpenStack to a home cloud cluster using OpenStack-Ansible (OSA). The four cluster nodes are also workstations in a computer lab running desktop Ubuntu 24.04, close to the default install.

**Rule for changes to nodes:**

- If a change is a deviation from a default Ubuntu 24.04 desktop install (e.g., fixing something OSA broke, one-off container fixes), it's okay to apply directly via SSH.
- If a change would need to be made to any fresh default Ubuntu 24.04 desktop install (e.g., packages, kernel modules, sysctl, NTP, SSH config, storage), it must be codified in Ansible roles/playbooks in this repo.

## VS Code Terminal Escape Sequence Contamination

**Critical:** The VS Code integrated terminal injects OSC 633 shell integration escape sequences (binary `\x1b]633;...` codes) into command output. When redirecting command output to files via the VS Code terminal (e.g., `cat file > /tmp/output` or `sudo cat file > /tmp/output`), these invisible escape sequences get written into the file, corrupting it.

This has caused real production issues — an SSH `trusted_ca` file was silently corrupted, and `sshd` rejected it with "invalid format" because the file started with escape bytes instead of `ssh-rsa`.

**To avoid this:**

- Use Python (`subprocess.check_output` or `open()`) to read/write files that need to be byte-clean.
- Use Ansible `copy`, `template`, or `fetch` modules instead of shell redirects.
- If you must use shell redirects, pipe through `cat` to strip terminal control: `command | cat > file` (not always sufficient).
- When debugging file format issues, always check with `xxd file | head` for unexpected leading bytes.

## Cluster Overview

- **Deployment host:** This workstation (not a cluster node)
- **Infrastructure/controller:** cloud-4core (all control plane services in LXC containers)
- **Compute nodes:** cloud-6core, cloud-celeron, cloud-eugene
- **Storage:** cloud-eugene (Cinder LVM on `/dev/sde`, Swift on `/dev/sdc` + `/dev/sdd`)
- **OpenStack version:** 2025.2 (Flamingo), `stable/2025.2` branch
- **OSA location:** `/opt/openstack-ansible` on the deployment host
- **OSA config:** `/etc/openstack_deploy/` on the deployment host
- **Network manager:** All nodes use **NetworkManager** (Ubuntu 24.04 desktop default), **not** systemd-networkd. OSA assumes systemd-networkd in some roles (e.g., `lxc_hosts` masks `lxc-net` and creates bridge configs under `/etc/systemd/network/`), but since systemd-networkd is disabled on these nodes, those configs have no effect. NetworkManager manages all host networking including the `br-mgmt` bridge.

## Provider Network Topology

**Read "Network Topology" in `INVENTORY.md` before debugging any networking issue.**

Key facts that cause confusion:

- The **management network** is `192.168.50.0/24` (RT-AX58U router). The workstation and all cluster nodes have IPs here.
- The **provider network** (`physnet1`, flat) is `192.168.2.0/24`, served by a **separate physical router** (RT-AC57U) whose WAN port is at `192.168.50.111` on the management network.
- OpenStack floating IPs are allocated from `192.168.2.0/24`. They are **not directly reachable from the workstation** unless a static route exists (`ip route add 192.168.2.0/24 via 192.168.50.111`).
- The provider NIC on each compute node (e.g., `enp6s0` on cloud-6core, `enp7s0` on cloud-celeron, `enp12s0` on cloud-eugene) has **no IP address** — it is a raw L2 port inside the OVS bridge `eth12`.
- Do **not** conclude "floating IPs are broken" just because pings from the workstation fail — check routing first.

## Git Policy

- **Never run `git add`, `git commit`, `git push`, or `git amend` on behalf of the user.** The user handles all Git operations manually.

## SSH Environment

- All nodes use SSH certificate authentication (ed25519 user CA + host CA)
- OSA's `ssh_keypairs` role adds its own RSA CA to compute nodes — both CAs must coexist in `/etc/ssh/trusted_ca` (assembled from `/etc/ssh/trusted_ca.d/`)
- OSA adds `AuthorizedPrincipalsFile` — the `kevin_principals` file must exist alongside `nova_principals`
- The `prepare_target_host` role handles this coexistence automatically
