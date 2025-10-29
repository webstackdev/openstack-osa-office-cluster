# Testing Documentation for webstack_builders.vim Collection

## Overview

This document outlines the comprehensive testing approach for the vim role within the webstack_builders.vim collection, utilizing Molecule with Podman containers.

## Testing Framework

### Molecule Configuration

- **Driver**: Podman (containerized testing)
- **Platform**: Ubuntu 24.04
- **Python Interpreter**: System python3 (`/usr/bin/python3`)
- **Container Build**: Custom Dockerfile with pre-installed dependencies

### Test Scenarios

The Molecule test suite includes the following phases:

1. **Dependency** - Install collection dependencies
2. **Cleanup** - Clean up any previous test artifacts
3. **Destroy** - Remove existing containers
4. **Syntax** - Validate Ansible playbook syntax
5. **Create** - Build and start test containers
6. **Prepare** - Initialize container environment
7. **Converge** - Execute the vim role
8. **Idempotence** - Verify role runs without changes
9. **Side Effect** - Check for unintended side effects
10. **Verify** - Validate role implementation
11. **Cleanup** - Final cleanup
12. **Destroy** - Remove test containers

## Running Tests

### Full Test Suite

```bash
cd /home/kevin/Repos/home-cloud/collections/vim/roles/run
molecule test
```

### Individual Test Steps

```bash
# Create and prepare environment
molecule create
molecule prepare

# Run role and verify
molecule converge
molecule verify

# Test idempotence
molecule idempotence

# Cleanup
molecule destroy
```

## Verification Tests

The verify playbook runs 15 comprehensive tests:

### Package Installation

- ✅ vim-nox package installed
- ✅ git package installed  
- ✅ fonts-powerline package installed
- ✅ fzf package installed

### Directory Structure

- ✅ ~/.vim directory exists
- ✅ ~/.vim/autoload directory exists
- ✅ ~/.vim/bundle directory exists

### Pathogen Plugin Manager

- ✅ pathogen.vim file present
- ✅ pathogen.vim contains expected content

### Plugin Installation

- ✅ vim-airline plugin installed
- ✅ nerdtree plugin installed
- ✅ Plugin directories contain vim scripts
- ✅ Plugin git repositories are valid

### Configuration

- ✅ .vimrc file exists
- ✅ .vimrc contains pathogen execute command
- ✅ vim configuration syntax is valid
- ✅ vim executable is accessible

### Permissions & Ownership

- ✅ File ownership is correct (testuser)
- ✅ Directory permissions are appropriate

## Test Results Summary

**SUCCESS**: All 15 verification tests pass consistently

- No failed tasks
- Idempotence verified (no changes on second run)
- Container environment properly configured
- Role execution completes successfully

## Python Unit and Integration Testing

### Overview

The collection includes comprehensive pytest-based tests that complement Molecule testing:
- **Unit Tests**: Validate role components, configuration, and structure
- **Integration Tests**: Test complete role scenarios and plugin installations

### Prerequisites

```bash
pip install pytest pytest-ansible pytest-xdist
```

### Running Python Tests

```bash
# From collection root directory
cd /home/kevin/Repos/home-cloud/collections/vim

# Run all tests (17 unit + 8 integration = 25 total)
pytest tests/ -v

# Run only unit tests (17 tests)
pytest tests/unit/ -v

# Run only integration tests (8 tests)
pytest tests/integration/ -v

# Run tests in parallel for faster execution
pytest tests/ -n 2 -v

# Run specific test class
pytest tests/unit/test_vim_role.py::TestVimRoleDefaults -v
```

### Test Coverage

#### Unit Tests (17 tests)
- ✅ **TestVimRoleDefaults**: Default variables validation and structure verification
- ✅ **TestVimRoleTasks**: Tasks file existence and YAML syntax validation  
- ✅ **TestVimRoleMeta**: Metadata and argument specifications verification
- ✅ **TestVimRoleFiles**: File and directory structure validation
- ✅ **TestMoleculeConfiguration**: Molecule configuration validation
- ✅ **Parametrized Tests**: Required YAML keys and role consistency validation

#### Integration Tests (8 tests)
- ✅ **test_vim_role_default_scenario**: Full Molecule scenario execution
- ✅ **test_vim_role_converge**: Role converge step validation
- ✅ **test_vim_role_idempotence**: Idempotence verification
- ✅ **test_vim_role_verify**: Verification step validation
- ✅ **test_vim_plugins_installation**: Individual plugin installation tests (parameterized)
- ✅ **test_vim_role_cleanup**: Cleanup and destruction verification

### CI/CD Integration

The pytest tests are automatically executed in GitHub Actions across multiple Python versions:
- Python 3.9, 3.10, 3.11, 3.12
- Parallel execution with matrix strategy
- Integration with existing Ansible-native testing workflows

## Container Environment

### Base Image

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y \
    python3 \
    sudo \
    systemctl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

### Test User

- Username: `testuser`
- Home Directory: `/home/testuser`
- Privileges: Can sudo for package installation
- Vim Configuration: Isolated to user directory

## Troubleshooting

### Common Issues

1. **Container Build Failures**
   - Verify Podman is installed and running
   - Check network connectivity for package downloads

2. **Permission Errors**
   - Ensure test runs with proper user context
   - Verify sudo access for package installation

3. **Plugin Installation Issues**
   - Check git connectivity
   - Verify plugin URLs are accessible

### Debug Commands

```bash
# Check container status
podman ps -a

# View container logs
molecule --debug converge

# Interactive container access
podman exec -it molecule_local_instance_default /bin/bash
```

## Integration with CI/CD

This test suite is designed for automated testing and can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Molecule Tests
  run: |
    cd collections/vim/roles/run
    molecule test
```

## Best Practices

1. **Always run full test suite** before committing changes
2. **Test idempotence** to ensure role stability
3. **Verify on clean environment** to catch missing dependencies
4. **Check all validation tests** pass consistently
5. **Use containerized testing** for reproducible results

---

*Last Updated*: January 2025  
*Framework*: Molecule with Podman  
*Platform*: Ubuntu 24.04  
*Status*: ✅ All tests passing
