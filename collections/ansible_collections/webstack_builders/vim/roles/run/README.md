# Vim Configuration Role

This Ansible role installs and configures Vim with a curated set of plugins using the Pathogen plugin manager. It provides a consistent, feature-rich Vim environment across multiple systems.

## Features

- ✅ Installs Vim and required dependencies
- ✅ Sets up Vim directory structure (`~/.vim/{autoload,bundle}`)
- ✅ Installs Pathogen plugin manager automatically
- ✅ Downloads and installs popular Vim plugins via Git
- ✅ Deploys custom `.vimrc` configuration
- ✅ Comprehensive argument validation
- ✅ Idempotent operations

## Requirements

- **Operating System**: Ubuntu/Debian (uses `apt` package manager)
- **Ansible**: >= 2.9
- **Python**: 3.6+
- **Network Access**: Required for downloading plugins from GitHub

## Role Variables

All role variables are validated using argument specifications. Invalid types or missing required fields will cause the playbook to fail with clear error messages.

### Default Variables (can be overridden)

#### `vim_plugins` (list of dicts)

List of Vim plugins to install via Git repositories.

**Default:**

```yaml
vim_plugins:
  - name: vim-airline
    url: https://github.com/vim-airline/vim-airline
  - name: nerdtree
    url: https://github.com/preservim/nerdtree
  - name: fzf-vim
    url: https://github.com/junegunn/fzf.vim
  - name: vim-gitgutter
    url: https://github.com/airblade/vim-gitgutter
  - name: vim-fugitive
    url: https://github.com/tpope/vim-fugitive
```

**Plugin Structure:**

- `name` (string, required): Plugin directory name in `~/.vim/bundle/`
- `url` (string, required): Git repository URL

#### `vim_dir` (path)

Directory where Vim configuration and plugins are stored.

- **Default**: `{{ lookup('env', 'HOME') }}/.vim`
- **Type**: path

#### `vim_rc` (path)

Path to the `.vimrc` configuration file.

- **Default**: `{{ lookup('env', 'HOME') }}/.vimrc`
- **Type**: path

#### `vim_install_packages` (list of strings)

System packages required for Vim functionality.

- **Default**: `['vim-nox', 'git', 'fonts-powerline', 'fzf']`
- **Type**: list of strings

## Dependencies

None. This role is self-contained.

## Example Playbooks

### Basic Usage (Default Configuration)

```yaml
- name: Install and configure Vim
  hosts: workstations
  become: true
  collections:
    - webstack_builders.vim
  roles:
    - vim
```

### Using Fully Qualified Collection Name

```yaml
- name: Install and configure Vim
  hosts: workstations
  become: true
  roles:
    - webstack_builders.vim.vim
```

### Custom Plugin Configuration

```yaml
- name: Install Vim with custom plugins
  hosts: developers
  become: true
  collections:
    - webstack_builders.vim
  roles:
    - role: vim
      vars:
        vim_plugins:
          - name: vim-sensible
            url: https://github.com/tpope/vim-sensible
          - name: vim-surround
            url: https://github.com/tpope/vim-surround
```

### Using include_role

```yaml
- name: Configure development environment
  hosts: localhost
  tasks:
    - name: Setup Vim configuration
      include_role:
        name: webstack_builders.vim.vim
      vars:
        vim_plugins:
          - name: YouCompleteMe
            url: https://github.com/ycm-core/YouCompleteMe
```

## Role Idempotency

**✅ True** - This role is fully idempotent. Running it multiple times will not change the system state unnecessarily.

## Testing

### Run All Tests

```bash
# Comprehensive test suite
./test-vim-role.sh
```

### Individual Tests

```bash
# Basic functionality test
ansible-playbook -i localhost, --connection=local --check collections/vim/roles/vim/tests/test.yml

# Argument validation tests
ansible-playbook -i localhost, --connection=local --check collections/vim/roles/vim/tests/argument_validation_test.yml
```

## Included Plugins (Default)

| Plugin | Description | Repository |
|--------|-------------|------------|
| **vim-airline** | Status/tabline | [vim-airline/vim-airline](https://github.com/vim-airline/vim-airline) |
| **nerdtree** | File explorer | [preservim/nerdtree](https://github.com/preservim/nerdtree) |
| **fzf-vim** | Fuzzy finder | [junegunn/fzf.vim](https://github.com/junegunn/fzf.vim) |
| **vim-gitgutter** | Git diff gutter | [airblade/vim-gitgutter](https://github.com/airblade/vim-gitgutter) |
| **vim-fugitive** | Git wrapper | [tpope/vim-fugitive](https://github.com/tpope/vim-fugitive) |

## License

MIT

## Author Information

This role was originally created as part of the home-cloud infrastructure automation project and moved to the `webstack_builders.vim` collection for better modularity.

**Maintainer**: Kevin Brown  
**Collection**: [webstack_builders.vim](https://github.com/ansible-collections/webstack_builders.vim)  
**Original Repository**: [home-cloud/openstack-cloud](https://github.com/home-cloud/openstack-cloud)

**Maintainer**: Kevin Brown
**Repository**: [home-cloud/openstack-cloud](https://github.com/home-cloud/openstack-cloud)  
**Role Path**: `roles/vim/`
