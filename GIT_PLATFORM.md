# Self-Hosted Git Platform

## PostgreSQL Required for GitLab

OpenStack Trove does support PostgreSQL as a datastore. Technically, GitLab can use a Trove-managed PostgreSQL instance, but there are significant limitations you should consider before implementation.

**OpenStack Trove & PostgreSQL Support**

Trove is a Database-as-a-Service (DBaaS) for OpenStack that allows users to provision and manage various relational and non-relational databases.

Datastore Support: PostgreSQL is one of the supported engines, alongside MySQL, MariaDB, and others.

Version Compatibility: Historical support included versions like 9.3 and 9.4, though modern OpenStack releases (like Wallaby or Victoria) have updated these capabilities.

Maturity: While PostgreSQL is supported, Trove's development has historically prioritized MySQL and MariaDB. Some advanced PostgreSQL features, like incremental backups, have been documented as limited or "work in progress" in certain versions.

**Using Trove to Back GitLab**

GitLab supports connecting to any external PostgreSQL server. To use a Trove instance, you would treat it as a standard external database by providing its connection details (host, port, username, password) in GitLab's configuration (/etc/gitlab/gitlab.rb or Helm chart values).

**Critical Compatibility Requirements:**

PostgreSQL Version: GitLab requires specific versions of PostgreSQL (currently PostgreSQL 14 or 16 for recent releases). You must ensure your Trove environment can provision these specific versions.

Required Extensions: GitLab requires the pg_trgm, btree_gist, and amcheck extensions to be installed in the database. Some managed DBaaS environments restrict the ability to install extensions or require specific administrative roles (like rds_superuser on AWS or cloudsqlsuperuser on GCP). You must verify if your Trove guest agent allows the GitLab user enough privilege to manage these extensions.
Administrative Access: You must be able to create a dedicated user and database (typically gitlabhq_production) with full ownership.
