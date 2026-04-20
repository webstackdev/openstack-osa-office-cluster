# Session Notes

The magnum-key keypair was registered in OpenStack but the private key wasn't saved locally. Let me check if the id_ed25519 key was uploaded as magnum-key, or try directly with the workstation key since the nodes are on the provider network (which needs a route).

The server list shows floating IPs 192.168.2.197 (worker) and 192.168.2.179 (master) — different from what coe cluster show reported.
