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

One thing to watch: Magnum's docs note cgroup_driver=cgroupfs should be used with Calico — this is already the default value, so no extra label is needed.

Cluster template snippet (for when you deploy):

```bash
openstack coe cluster template create k8s-template \
  --network-driver calico \
  --labels calico_tag=v3.26.4,calico_ipv4pool=10.100.0.0/16,cgroup_driver=cgroupfs,...
```
