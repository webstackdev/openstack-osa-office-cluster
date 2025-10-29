# Webstack Builders Vim Collection

This repository contains the `webstack_builders.vim` Ansible Collection, which includes roles for managing Vim configuration and installation.

This collection was created by moving the vim role from the openstack-cloud playbook repository into its own dedicated collection for better modularity and reusability.

<!--start requires_ansible-->
## Ansible version compatibility

This collection requires Ansible 2.9.0 or greater.
<!--end requires_ansible-->

## External requirements

Some modules and plugins require external libraries. Please check the
requirements for each plugin or module you use in the documentation to find out
which requirements are needed.

## Included content

<!--start collection content-->
### Roles

- `webstack_builders.vim` - Manages Vim installation and configuration with plugins
<!--end collection content-->

## Using this collection

### Installation

Install the collection using ansible-galaxy:

```bash
ansible-galaxy collection install webstack_builders.vim
```

You can also include it in a `requirements.yml` file and install it via
`ansible-galaxy collection install -r requirements.yml` using the format:

```yaml
collections:
  - name: webstack_builders.vim
```

### Usage in playbooks

Once installed, you can use the roles in your playbooks:

```yaml
- name: Configure Vim
  hosts: all
  collections:
    - webstack_builders.vim
  roles:
    - vim
```

Or reference the role with its fully qualified collection name:

```yaml
- name: Configure Vim
  hosts: all
  roles:
    - webstack_builders.vim.vim
```

## Testing

This collection uses [Molecule](https://molecule.readthedocs.io/) with [Podman](https://podman.io/) for automated testing.

### Prerequisites

Install testing dependencies:

```bash
pip install molecule molecule-plugins molecule-podman
```

Ensure Podman is installed and running on your system.

### Running Tests

#### Full Test Suite

Run the complete Molecule test suite (recommended):

```bash
cd roles/run
molecule test
```

This executes all test phases: dependency → cleanup → destroy → syntax → create → prepare → converge → idempotence → verify → cleanup → destroy

#### Individual Test Steps

For development and debugging, you can run individual steps:

```bash
# Create test container
molecule create

# Prepare environment
molecule prepare

# Execute role (converge)
molecule converge

# Verify role functionality
molecule verify

# Test idempotence (role should not make changes on second run)
molecule idempotence

# Cleanup test environment
molecule destroy
```

#### Test Scenarios

- **default**: Tests standard vim configuration with vim-airline and nerdtree plugins using Podman on Ubuntu 24.04

To run a specific scenario:

```bash
molecule test -s default
```

### Python Unit and Integration Tests

This collection also includes comprehensive pytest-based tests for development and CI/CD integration.

#### Python Prerequisites

Install pytest dependencies:

```bash
pip install pytest pytest-ansible pytest-xdist
```

#### Running Python Tests

```bash
# Run all tests (17 unit + 8 integration = 25 total)
pytest tests/

# Run only unit tests (17 tests)
pytest tests/unit/

# Run only integration tests (8 tests)
pytest tests/integration/

# Run with verbose output
pytest tests/ -v

# Run specific test class
pytest tests/unit/test_vim_role.py::TestVimRoleDefaults -v

# Run tests in parallel
pytest tests/ -n 2
```

#### Python Test Coverage

**Unit Tests** (17 tests):

- ✅ Role defaults validation and structure verification
- ✅ Tasks file existence and YAML syntax validation
- ✅ Metadata and argument specifications verification
- ✅ File and directory structure validation
- ✅ Molecule configuration validation

**Integration Tests** (8 tests):

- ✅ Full Molecule scenario execution
- ✅ Role converge, idempotence, and verify steps
- ✅ Individual plugin installation validation
- ✅ Cleanup and destruction verification

### Molecule Test Coverage

The test suite validates:

- ✅ Package installation (vim-nox, git, fonts-powerline, fzf)
- ✅ Directory structure creation (`.vim`, `.vim/autoload`, `.vim/bundle`)
- ✅ Pathogen plugin manager installation and configuration
- ✅ Vim plugin deployment and git repository validation
- ✅ Configuration file deployment (`.vimrc` with pathogen)
- ✅ File permissions and ownership verification
- ✅ Vim executable accessibility and syntax validation
- ✅ Idempotence testing (no changes on repeated runs)

For detailed testing documentation, see [roles/run/TESTING.md](roles/run/TESTING.md).

### Upgrading

To upgrade the collection to the latest available version, run the following
command:

```bash
ansible-galaxy collection install webstack_builders.vim --upgrade
```

You can also install a specific version of the collection, for example, if you
need to downgrade when something is broken in the latest version (please report
an issue in this repository). Use the following syntax where `X.Y.Z` can be any
[available version](https://galaxy.ansible.com/webstack_builders/vim):

```bash
ansible-galaxy collection install webstack_builders.vim:==X.Y.Z
```

See
[Ansible Using Collections](https://docs.ansible.com/ansible/latest/user_guide/collections_using.html)
for more details.

## Release notes

See the
[changelog](https://github.com/ansible-collections/webstack_builders.vim/tree/main/CHANGELOG.rst).

## Roadmap

This collection aims to provide comprehensive Vim management capabilities including:

- Base Vim installation across multiple operating systems  
- Plugin management via Pathogen
- Configuration templating
- User-specific and system-wide configurations

## More information

<!-- List out where the user can find additional information, such as working group meeting times, slack/matrix channels, or documentation for the product this collection automates. At a minimum, link to: -->

- [Ansible collection development forum](https://forum.ansible.com/c/project/collection-development/27)
- [Ansible User guide](https://docs.ansible.com/ansible/devel/user_guide/index.html)
- [Ansible Developer guide](https://docs.ansible.com/ansible/devel/dev_guide/index.html)
- [Ansible Collections Checklist](https://docs.ansible.com/ansible/devel/community/collection_contributors/collection_requirements.html)
- [Ansible Community code of conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html)
- [The Bullhorn (the Ansible Contributor newsletter)](https://docs.ansible.com/ansible/devel/community/communication.html#the-bullhorn)
- [News for Maintainers](https://forum.ansible.com/tag/news-for-maintainers)

## Licensing

GNU General Public License v3.0 or later.

See [LICENSE](https://www.gnu.org/licenses/gpl-3.0.txt) to see the full text.
