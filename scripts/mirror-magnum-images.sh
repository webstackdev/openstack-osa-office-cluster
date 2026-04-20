#!/bin/bash
# Mirror all images required by Magnum's k8s-calico cluster template
# to the local Docker Distribution registry at 192.168.50.168:5050.
#
# Magnum's container_infra_prefix is "192.168.50.168:5050/openstackmagnum/".
# The bootstrap scripts strip the upstream prefix and replace it with that value,
# so "quay.io/calico/node:v3.26.4" becomes
# "192.168.50.168:5050/openstackmagnum/node:v3.26.4".
#
# Run this on a host that can pull from the internet AND push to
# 192.168.50.168:5050 (e.g., cloud-4core itself, which has the registry
# as an insecure registry).
#
# MAINTENANCE NOTE: When Magnum code or cluster template labels change
# (e.g., kube_tag, calico_tag, cloud_provider_tag, etc.), update the
# image list below to match. The upstream source and local name for each
# image are derived from Magnum's driver shell scripts in:
#   magnum/drivers/common/templates/kubernetes/fragments/
#
# Usage:
#   sudo bash scripts/mirror-magnum-images.sh

set -euo pipefail

LOCAL_REGISTRY="192.168.50.168:5050"
LOCAL_PREFIX="${LOCAL_REGISTRY}/openstackmagnum"

# Image mappings: "upstream_image local_short_name"
# The local_short_name becomes ${LOCAL_PREFIX}/<local_short_name>
IMAGES=(
  # hyperkube (kubectl, kubelet, kube-apiserver, kube-proxy, etc.)
  "docker.io/rancher/hyperkube:v1.28.9-rancher1                hyperkube:v1.28.9-rancher1"

  # etcd
  "quay.io/coreos/etcd:v3.4.6                                  etcd:v3.4.6"

  # CoreDNS
  "docker.io/coredns/coredns:1.6.6                             coredns:1.6.6"

  # Calico v3.26.4
  "quay.io/calico/cni:v3.26.4                                  cni:v3.26.4"
  "quay.io/calico/node:v3.26.4                                 node:v3.26.4"
  "quay.io/calico/kube-controllers:v3.26.4                     kube-controllers:v3.26.4"

  # OpenStack Cloud Controller Manager
  "registry.k8s.io/provider-os/openstack-cloud-controller-manager:v1.28.3  openstack-cloud-controller-manager:v1.28.3"

  # Keystone auth
  "registry.k8s.io/provider-os/k8s-keystone-auth:v1.28.3      k8s-keystone-auth:v1.28.3"

  # Cinder CSI
  "registry.k8s.io/provider-os/cinder-csi-plugin:v1.28.3      cinder-csi-plugin:v1.28.3"
  "registry.k8s.io/sig-storage/csi-attacher:v3.3.0             csi-attacher:v3.3.0"
  "registry.k8s.io/sig-storage/csi-provisioner:v3.0.0          csi-provisioner:v3.0.0"
  "registry.k8s.io/sig-storage/csi-snapshotter:v4.2.1          csi-snapshotter:v4.2.1"
  "registry.k8s.io/sig-storage/csi-resizer:v1.3.0              csi-resizer:v1.3.0"
  "registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.4.0  csi-node-driver-registrar:v2.4.0"
  "registry.k8s.io/sig-storage/livenessprobe:v2.5.0            livenessprobe:v2.5.0"

  # Kubernetes Dashboard
  "docker.io/kubernetesui/dashboard:v2.0.0                     dashboard:v2.0.0"
  "docker.io/kubernetesui/metrics-scraper:v1.0.4               metrics-scraper:v1.0.4"

  # DNS autoscaler — upstream v1.1.2 is gone from gcr.io/k8s.gcr.io.
  # Pull v1.8.4 (stable, compatible) and tag as the old name Magnum expects.
  # The image was renamed from cluster-proportional-autoscaler-amd64 to
  # cluster-proportional-autoscaler (multi-arch) in newer releases.
  "registry.k8s.io/cpa/cluster-proportional-autoscaler:v1.8.4  cluster-proportional-autoscaler-amd64:1.1.2"

  # Pause container (pod infra)
  "registry.k8s.io/pause:3.1                                   pause:3.1"

  # Node Problem Detector
  "registry.k8s.io/node-problem-detector:v0.6.2                node-problem-detector:v0.6.2"

  # Heat container agent
  "docker.io/openstackmagnum/heat-container-agent:wallaby-stable-1  heat-container-agent:wallaby-stable-1"

  # Metrics server (Helm chart v3.7.0, appVersion v0.5.2)
  "registry.k8s.io/metrics-server/metrics-server:v0.5.2        metrics-server:v0.5.2"
)

echo "Mirroring ${#IMAGES[@]} images to ${LOCAL_REGISTRY}"
echo "=================================================="

FAILED=()
for entry in "${IMAGES[@]}"; do
  upstream=$(echo "$entry" | awk '{print $1}')
  local_name=$(echo "$entry" | awk '{print $2}')
  local_full="${LOCAL_PREFIX}/${local_name}"

  echo ""
  echo ">>> ${upstream} -> ${local_full}"

  if ! docker pull "$upstream"; then
    echo "FAILED to pull: $upstream"
    FAILED+=("$upstream")
    continue
  fi

  docker tag "$upstream" "$local_full"

  if ! docker push "$local_full"; then
    echo "FAILED to push: $local_full"
    FAILED+=("$local_full")
    continue
  fi

  # Clean up pulled images to save disk
  docker rmi "$upstream" "$local_full" 2>/dev/null || true

  echo "OK: $local_name"
done

echo ""
echo "=================================================="
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "FAILED images:"
  for f in "${FAILED[@]}"; do
    echo "  - $f"
  done
  exit 1
else
  echo "All ${#IMAGES[@]} images mirrored successfully."
fi
