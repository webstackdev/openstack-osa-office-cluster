# Home_cloud Example_playbook Ansible Project

## Run a Playbook

The run-ansible.sh script clears environmental vars being set by OpenStack-Ansible somewhere.

```bash
./run-ansible.sh --extra-vars @group_vars/all/vault.yml --vault-password-file ~/.ansible.pass <playbook_name.yml>
```

## Collection Dependencies

This project uses external Ansible collections. Install them with:

```bash
ansible-galaxy collection install -r requirements.yml
```

The `requirements.yml` file includes:
- **webstack_builders.vim**: Vim configuration and plugin management collection

## no-changed-when

```yaml
tasks:
  - name: Example task requiring become
    ansible.builtin.command: whoami
    # Registers the command output.
    register: whoami_result
    # Uses the return code to define when the task has changed.
    changed_when: whoami_result.rc != 0
```

## Included content/ Directory Structure

```text
├── changelogs
│   └── config.yaml
├── docs
│   └── docsite
│       └── links.yml
├── inventory
│   ├── group_vars
│   │   ├── all.yml
│   │   ├── db_servers.yml
│   │   ├── production.yml
│   │   ├── test.yml
│   │   └── web_servers.yml
│   ├── host_vars
│   │   ├── server1.yml
│   │   └── switch1.yml
│   ├── argspec_validation_inventory.yml
│   └── hosts.yml
├── roles
│   └── common
│       ├── defaults
│       │   └── main.yml      # default lower priority variables for this role
│       ├── files
│       │   ├── bar.txt       # files for use with the copy resource
│       │   └── foo.sh        # script files for use with the script resource
│       ├── handlers
│       │   └── main.yml      # executed at the end of a play, like restarting a service
│       ├── meta
│       │   ├── argument_specs.yml
│       │   └── main.yml      # role dependencies and optional Galaxy info
│       ├── tasks
│       │   └── main.yml      # tasks file can include smaller files if warranted
│       ├── templates
│       │   └── ntp.conf.j2   # templates end in .j2
│       ├── tests
│       │   └── inventory
│       ├── vars
│       │   └── main.yml      # variables associated with this role
│       └── README.md
├── tests
│   ├── integration
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-312.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── test_integration.cpython-312-pytest-8.4.2.pyc
│   │   │   └── test_integration.cpython-313-pytest-8.4.2.pyc
│   │   ├── targets
│   │   │   └── hello_world
│   │   │       └── tasks
│   │   │           └── main.yml
│   │   ├── __init__.py
│   │   └── test_integration.py
│   └── unit
│       ├── __pycache__
│       │   ├── __init__.cpython-312.pyc
│       │   ├── __init__.cpython-313.pyc
│       │   ├── test_basic.cpython-312-pytest-8.4.2.pyc
│       │   └── test_basic.cpython-313-pytest-8.4.2.pyc
│       ├── __init__.py
│       └── test_basic.py
├── ansible.cfg
├── ansible-navigator.yml
├── argspec_validation_plays.meta.yml    #
├── argspec_validation_plays.yml         # Argument validation
├── devfile.yaml
├── example_playbook.yml
├── linux_playbook.yml
├── network_playbook.yml
├── README.md
└── site.yml
```

## Compatible with Ansible-lint

Tested with ansible-lint >=24.2.0 releases and the current development version
of ansible-core.
