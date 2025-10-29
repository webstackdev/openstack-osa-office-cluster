# Ansible Collection - webstack_builders.openstack_new_node

Documentation for the collection.

## Shell into a container running by Podman

```bash
podman exec ubuntu2404-test python3 --version
```

## Run Molecule test

```bash
cd /home/kevin/Repos/home-cloud/collections/ansible_collections/webstack_builders/setup_node/roles/install_packages

# Individual test stages:
molecule converge   # ✅ Passed - Role applied successfully
molecule verify     # ✅ Passed - All verifications successful

# Other commands:
molecule login      # Access container shell
molecule list       # Show test instances
molecule destroy    # Clean up when done
```
