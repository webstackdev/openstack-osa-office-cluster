# Home Cloud Todos

## Trove Databases

Add Prebuilt FOCA images:

- Cassandra
- CouchDB / Couchbase
- MongoDB
- PostgreSQL
- Redis

| Feature | MySQL / MariaDB | Redis | Cassandra | Couchbase |
| --- | --- | --- | --- | --- |
| Basic Provisioning | Full Support | Full Support | Full Support | Full Support |
| Backup & Restore | Mature | Supported | Supported | Supported |
| Replication | Master/Slave | Supported | Native Clustering | Supported |
| Clustering | Galera Support | Supported | Supported | Supported |

## OIDC Identity (Keycloak)

Usually if you are using keycloak with Openstack you would look at using openidconnect as the protocol for authentication.

Authorization can happen a few ways, but I expect you would want to use group mappings (or at least OIDC attributes) to map the users to groups in Openstack.

There's documentation of doing this with [kolla-ansible here](https://docs.openstack.org/kolla-ansible/latest/reference/shared-services/keystone-guide.html).

You would have to look at the [Federated Identity part](https://docs.openstack.org/kolla-ansible/latest/reference/shared-services/keystone-guide.html#federated-identity) which requires some additional configuration files and folders for OpenID. `https://docs.openstack.org/keystone/2024.1/admin/federation/configure_federation.html`

The atmosphere project includes Keycloak integration. While you aren't using this deployment method, you might be able to find something from the [specific role](https://github.com/vexxhost/atmosphere/tree/main/roles/keycloak).

## Add GitLab cluster

## Add Docs

- Create a documentation directory
- Add files for each service installed and copy PLANNING.md notes into it, rewrite
