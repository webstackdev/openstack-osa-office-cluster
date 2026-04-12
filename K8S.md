# Kubernetes

Here's what you need to know about managing a Calico-based k8s cluster:

What Calico gives you over Flannel:

- NetworkPolicy — the main reason to use it. You can write k8s-native rules that control which pods can talk to which, e.g. "only the frontend pods can reach the backend pods on port 8080." Flannel has zero policy enforcement.
- BGP-based routing — similar to flannel's host-gw, Calico programs routes directly between nodes. With calico_ipv4pool_ipip=Off (the Magnum default), there's no encapsulation overhead.

Key kubectl commands for Calico:

```bash
# Check Calico node status (runs as a DaemonSet)
kubectl get pods -n kube-system -l k8s-app=calico-node

# Check Calico controllers
kubectl get pods -n kube-system -l k8s-app=calico-kube-controllers

# View the IP pool configuration
kubectl get ippools -o yaml

# Create a NetworkPolicy (example: deny all ingress to a namespace)
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: default
spec:
  podSelector: {}
  policyTypes:
  - Ingress
EOF

# Allow specific traffic (e.g., only from pods with label app=frontend)
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: backend
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - port: 8080
EOF

# List all network policies
kubectl get networkpolicies --all-namespaces

# Debug: check if a node has Calico routes
kubectl exec -n kube-system <calico-node-pod> -- calico-node -bird-live
```

One thing to watch: Magnum's docs note `cgroup_driver=cgroupfs` should be used with Calico — this is already the default value, so no extra label is needed.

Cluster template snippet (for when you deploy):

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

### Label reference

| Label | Value | Why |
|---|---|---|
| `calico_ipv4pool` | `10.100.0.0/16` | Pod CIDR for Calico |
| `calico_ipv4pool_ipip` | `Off` | No IPIP encapsulation (BGP direct routing) |
| `calico_tag` | `v3.26.4` | Calico release (Dalmatian-tested) |
| `cgroup_driver` | `cgroupfs` | Required for Calico |
| `container_runtime` | `containerd` | CRI runtime |
| `kube_tag` | `v1.28.9-rancher1` | K8s version (rancher hyperkube image) |
| `containerd_version` | `1.7.25` | Must be ≥1.6 for CRI v1 (kubelet v1.28+ requires it) |
| `containerd_tarball_sha256` | `6b987a...` | SHA256 of the containerd GitHub release tarball |
| `cloud_provider_tag` | `v1.28.3` | openstack-cloud-controller-manager image tag |
| `cinder_csi_plugin_tag` | `v1.28.3` | cinder-csi-plugin image tag |
| `k8s_keystone_auth_tag` | `v1.28.3` | k8s-keystone-auth image tag |

> **Important:** The last three labels are critical. Magnum's Heat template defaults (`v1.23.1` / `v1.23.0` / `v1.18.0`) don't exist in `registry.k8s.io/provider-os/`. They must match the K8s minor version — for v1.28.x, use `v1.28.3`.

## Cluster lifecycle

### Prerequisites

Before creating any cluster, ensure the `volumev3` Keystone service alias exists (cinder-csi needs it):

```bash
# Check if it exists
openstack endpoint list --service volumev3

# If not, create it (one-time setup)
openstack service create --name cinderv3 \
  --description "Cinder Volume Service v3 (alias for cinder-csi compatibility)" volumev3
CINDER_URL="https://$(grep internal_lb_vip_address /etc/openstack_deploy/openstack_user_config.yml | awk '{print $2}'):8776/v3"
for iface in public internal admin; do
  openstack endpoint create --region RegionOne volumev3 $iface "$CINDER_URL"
done
```

### Create a cluster

```bash
openstack coe cluster create test-k8s \
  --cluster-template k8s-calico \
  --master-count 1 \
  --node-count 1
```

Monitor: `openstack coe cluster show test-k8s -c status -f value` — wait for `CREATE_COMPLETE`.

### Access the cluster

```bash
# Generate kubeconfig (writes to current dir)
eval $(openstack coe cluster config test-k8s)
kubectl get nodes
kubectl get pods -A
```

### Update template labels

The template can't be updated while a cluster references it. Delete the cluster first, then:

```bash
openstack coe cluster template update k8s-calico replace \
  labels='calico_ipv4pool=10.100.0.0/16,...,cloud_provider_tag=v1.28.3,...'
```

### Delete a cluster

```bash
openstack coe cluster delete test-k8s
# Wait for deletion:
openstack coe cluster list   # should be empty
openstack stack list          # Heat stack should be gone
```

### SSH into cluster VMs

Magnum VMs run Fedora CoreOS and are on a tenant network behind OVN. Access them via the OVN metadata namespace on the compute host:

```bash
# Find which compute host the VM is on
openstack server show <vm-name> -c OS-EXT-SRV-ATTR:host -f value

# On that compute host, find the metadata namespace
NETNS=$(sudo ip netns list | grep ovnmeta | head -1 | awk '{print $1}')

# SSH in (uses the keypair from the cluster template)
sudo ip netns exec "$NETNS" ssh -i /tmp/magnum_key core@<vm-fixed-ip>
```

## Known issues

1. **Podman image pulls stall inside FCOS VMs.** Pulls via podman (for etcd, heat-container-agent) can hang — `pigz -d` at 0% CPU for 10+ min. Kill the stalled pull, re-pull manually, restart the service.

2. **keystone-auth webhook chicken-and-egg.** If `k8s-keystone-auth` can't start, the kube-apiserver Webhook authorization blocks ALL API calls. Workaround: SSH into master, edit `/etc/kubernetes/apiserver` to remove `Webhook` from `--authorization-mode`, restart apiserver, fix the issue, restore from `apiserver.bak`.

## Why podman pull stalls

The network configuration is actually correct — Neutron sets the geneve tenant network MTU to 1442, the VM's ens3 gets MTU 1442, and TCP negotiates MSS 1390. There's no PMTUD black hole for TCP traffic (ping tests to 8.8.8.8 confirm the path works up to 1414-byte payloads, exactly 1442 with headers).

The stall is an intermittent Docker Hub pull issue through podman during early VM boot. The symptom is pigz -d (the decompressor) sitting at 0% CPU waiting for data that never arrives — meaning the HTTP/TLS stream from Docker Hub's CDN stalled mid-transfer. Killing the process and re-pulling works instantly (likely hits a different CDN edge or TCP connection).

**Contributing factors:**

- Network isn't instantly stable at boot (OVN flow rules still propagating)

- Podman's pull has poor timeout / retry for stalled connections

- Docker Hub CDN is flaky for long-distance pulls through tunnel networks

- The `heat-container-agent.service` has `TimeoutStartSec=10min` but no `Restart=on-failure`, so if the install eventually times out, the service just dies and never retries

**How to fix it**

The right fix is to stop pulling from Docker Hub during boot entirely. Magnum supports two labels for this:

1. `container_infra_prefix` — prefix for all container image pulls (heat-container-agent, hyperkube, calico, dashboard, etc.). Default: docker.io/openstackmagnum/ for heat-container-agent, various registries for others.

2. `heat_container_agent_tag` — tag for `heat-container-agent`. Default: `wallaby-stable-1`.

The approach: run a local Docker registry as a pull-through cache, then set `container_infra_prefix` to point to it. This means the first cluster creation fetches images from the internet and caches them locally; all subsequent creates are instant local pulls.

The systemd service in the ignition config looks like:

```bash
ExecStartPre=-/bin/podman pull __CONTAINER_INFRA_PREFIX__heat-container-agent:__HEAT_CONTAINER_AGENT_TAG__
ExecStart=/bin/podman run ... __CONTAINER_INFRA_PREFIX__heat-container-agent:__HEAT_CONTAINER_AGENT_TAG__ ...
```

So `container_infra_prefix=192.168.50.168:5000/openstackmagnum/` would redirect all pulls to a local registry on cloud-4core.

However, `container_infra_prefix` only controls some images (`heat-container-agent`, and images that use `$CONTAINER_INFRA_PREFIX` in the boot scripts). Rancher hyperkube, calico, registry.k8s.io images, etc. are controlled by separate labels or hardcoded. A pull-through cache would need to be configured as a containerd mirror, not just via this label.

The simplest practical approach for your home lab would be a local registry with pre-pushed images — Push all needed images (heat-container-agent, hyperkube, calico, etc.) to a local registry, set all the labels to point there.

**Registry server options**

| Registry | Description | Storage backends |
| --- | --- | --- |
| Docker Distribution (aka registry:2) | The reference implementation. Minimal, no UI. Most common for "just a local mirror." | Local filesystem, S3, Azure Blob, GCS, Swift, in-memory |
| Harbor | CNCF graduated project. Adds RBAC, vulnerability scanning (Trivy), replication, UI, audit logs. | Delegates to an underlying registry:2 instance; storage same as above (filesystem, S3, Swift, etc.) |

For your setup, `registry:2` (Docker Distribution) is the simplest choice. It's a single container, trivially runs on the deployment host or cloud-4core, and can back to local filesystem or Swift (which you already have on cloud-eugene). A basic deployment is:

```bash
podman run -d -p 5000:5000 \
  -v /srv/registry:/var/lib/registry \
  --name registry \
  docker.io/library/registry:2
```

Then you pre-push images:

```bash
podman pull quay.io/coreos/hyperkube:v1.28.x
podman tag quay.io/coreos/hyperkube:v1.28.x localhost:5000/hyperkube:v1.28.x
podman push localhost:5000/hyperkube:v1.28.x
```

And point your Magnum/Heat templates to `<registry-host>:5000/` instead of upstream registries.

Harbor would only be worth it if you want a UI, vulnerability scanning, or multi-user access control — probably overkill for a home lab.

Want me to implement one of these? Option A (local registry) is the most robust and eliminates the problem entirely. I can set up a Docker registry on cloud-4core (or the deployment host) and calculate the full set of labels needed.

## Pods on a Cluster Deploy

| Pod | What it does |
| --- | --- |
| `calico-node` (DaemonSet) | Programs BGP routes and network policy rules on each node |
| `calico-kube-controllers` | Syncs Calico datastore with k8s API (node/policy cleanup) |
| `coredns` (2 replicas) | Cluster DNS — resolves `service.namespace.svc.cluster.local` |
| `csi-cinder-controllerplugin` | Manages Cinder volume provisioning/attach/snapshot (6 containers: `csi-attacher`, `csi-provisioner`, `csi-snapshotter`, `csi-resizer`, `liveness-probe`, `cinder-csi-plugin`) |
| `csi-cinder-nodeplugin` (DaemonSet) | Mounts Cinder volumes into pods on each node |
| `k8s-keystone-auth` (DaemonSet) | Webhook that authenticates `kubectl` users against Keystone |
| `openstack-cloud-controller-manager` | Integrates k8s with OpenStack (floating IPs for LoadBalancer services, node labels from Nova metadata) |
| `kubernetes-dashboard` | Web UI for the cluster |
| `dashboard-metrics-scraper` | Scrapes metrics for the dashboard |
| `kube-dns-autoscaler` | Scales coredns replicas based on cluster size |
| `magnum-metrics-server` | Collects CPU/memory metrics (enables kubectl top) |
| `npd` (node-problem-detector) | Monitors for node issues (kernel panics, docker hangs, etc.) |

## `kubernetes-dashboard` Access

```bash
# From the master VM, proxy the dashboard:
kubectl proxy --address=0.0.0.0 --accept-hosts='.*'

# Then access: http://<master-floating-ip>:8001/api/v1/namespaces/kube-system/services/https:kubernetes-dashboard:/proxy/
```

But since your master is behind OVN on a tenant network (no direct browser access), the practical way is:

```bash
# On your workstation, after `eval $(openstack coe cluster config test-k8s)`:
kubectl port-forward -n kube-system svc/kubernetes-dashboard 8443:443
# Then open https://localhost:8443
```

You'll need a token to log in:

```bash
kubectl -n kube-system create token kubernetes-dashboard
```

## What defines the pod set?

Magnum's Heat templates define a base set of system pods that every cluster gets. These are baked into the FCOS driver templates we were reading on `cloud-4core` (`kubeminion.yaml`, `kubemaster.yaml`, and the boot scripts they invoke). The bootstrap scripts deploy:

- calico (from your network-driver calico choice)
- coredns (hardcoded)
- csi-cinder (from your volume-driver cinder choice)
- k8s-keystone-auth (enabled by default)
- openstack-cloud-controller-manager (enabled by default)
- kubernetes-dashboard (enabled by default)
- kube-dns-autoscaler, magnum-metrics-server, npd (enabled by default)

Some are toggleable via labels (e.g. npd_enabled, keystone_auth_enabled), but you don't define individual pods in your template — the template just picks the driver and labels that control feature flags. Once the cluster is running, you deploy your own pods on top with kubectl apply.

They're podman containers managed by systemd, not Kubernetes pods. That's why they don't show in kubectl get pods -A.

The control plane components are:

Component | Runs as | What it does |
| --- | --- | --- |
| `etcd` | podman container via etcd.service | Distributed key-value store — the cluster's database. All state (pods, services, secrets, configmaps) lives here |
| `kube-apiserver` | podman container via kube-apiserver.service | The front door — every kubectl command and every pod-to-API call goes through this |
| `kube-controller-manager` | podman container via kube-controller-manager.service | Runs control loops — watches desired state vs actual state and reconciles (e.g., "Deployment says 3 replicas but only 2 exist → create one more") |
| `kube-scheduler` | podman container via kube-scheduler.service | Decides which node a new pod runs on based on resource requests, affinity rules, taints/tolerations |
| `kubelet	podman` container via `kubelet.service` | The node agent — receives pod assignments from the API server and tells containerd to run the containers |
| `kube-proxy` | podman container via kube-proxy.service | Programs iptables / IPVS rules so that ClusterIP and NodePort services route to the right pods |

Magnum's FCOS driver runs these as systemd-managed podman containers rather than Kubernetes static pods (which is the kubeadm approach). This is a "chicken and egg" design choice — kubelet can't manage itself, and etcd + apiserver need to be up before Kubernetes can schedule anything. By running them in podman under systemd, they start independently and don't depend on the Kubernetes control plane being healthy. |

On EKS, you'd never see these at all — AWS runs etcd, apiserver, scheduler, and controller-manager for you on hidden infrastructure. You only see worker-side components.

They are containerized — they run as podman containers. But they're not managed by Kubernetes. There are two layers of containerization on the master VM:

Podman containers (systemd-managed): etcd, kube-apiserver, kube-controller-manager, kube-scheduler, kubelet, kube-proxy. These are started by systemd unit files (e.g. etcd.service, kube-apiserver.service). Systemd calls podman run ... to launch each one.

Containerd containers (Kubernetes-managed): calico, coredns, csi-cinder, k8s-keystone-auth, dashboard, etc. These are the pods you see in kubectl get pods -A. Kubelet tells containerd to run them.

So the stack on the master is:

```bash
VM (Fedora CoreOS)
├── systemd
│   ├── podman → etcd container
│   ├── podman → kube-apiserver container
│   ├── podman → kube-controller-manager container
│   ├── podman → kube-scheduler container
│   ├── podman → kubelet container ──→ talks to containerd
│   ├── podman → kube-proxy container
│   └── podman → heat-container-agent container
└── containerd (CRI)
    ├── calico-node pod
    ├── coredns pods
    ├── csi-cinder pods
    ├── k8s-keystone-auth pod
    ├── dashboard pod
    └── ... (your future workloads)
```

Podman and containerd are two separate container runtimes running side by side. Podman handles the "bootstrap" containers that need to exist before Kubernetes works. Containerd handles everything Kubernetes schedules. This is specific to Magnum's FCOS driver — the more common kubeadm approach uses static pods (YAML files in /etc/kubernetes/manifests/ that kubelet picks up directly) instead of podman, keeping everything in one runtime.
