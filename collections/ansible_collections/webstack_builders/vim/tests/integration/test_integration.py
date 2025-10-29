"""Integration tests for vim role using subprocess and ansible-playbook."""

from __future__ import absolute_import, division, print_function

import os
import subprocess
import pytest
import tempfile
import yaml
from pathlib import Path


@pytest.fixture(scope="session")
def collection_root():
    """Get the collection root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")  
def molecule_dir(collection_root):
    """Get the molecule directory path."""
    return collection_root / "roles" / "run" / "molecule" / "default"


class TestVimRoleIntegration:
    """Integration tests for vim role."""

    @pytest.mark.slow
    def test_molecule_syntax_check(self, molecule_dir):
        """Test molecule syntax check passes."""
        # Change to the molecule directory parent (roles/run) as that's where molecule should be run
        roles_run_dir = molecule_dir.parent
        result = subprocess.run(
            ["molecule", "syntax"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax check failed: {result.stderr}"

    @pytest.mark.slow
    def test_molecule_create_and_converge(self, molecule_dir):
        """Test molecule can create container and converge role."""
        roles_run_dir = molecule_dir.parent
        
        # Clean up any existing containers
        subprocess.run(["molecule", "destroy"], cwd=roles_run_dir, capture_output=True)
        
        # Create container
        result = subprocess.run(
            ["molecule", "create"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Create failed: {result.stderr}"
        
        # Prepare container
        result = subprocess.run(
            ["molecule", "prepare"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Prepare failed: {result.stderr}"

        # Run converge
        result = subprocess.run(
            ["molecule", "converge"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Converge failed: {result.stderr}"

    @pytest.mark.slow
    def test_molecule_verify(self, molecule_dir):
        """Test molecule verify step passes."""
        roles_run_dir = molecule_dir.parent
        result = subprocess.run(
            ["molecule", "verify"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Verify failed: {result.stderr}"

    @pytest.mark.slow
    def test_molecule_idempotence(self, molecule_dir):
        """Test role idempotence."""
        roles_run_dir = molecule_dir.parent
        result = subprocess.run(
            ["molecule", "idempotence"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Idempotence test failed: {result.stderr}"

    def test_molecule_cleanup(self, molecule_dir):
        """Test molecule cleanup and destroy."""
        roles_run_dir = molecule_dir.parent
        result = subprocess.run(
            ["molecule", "destroy"],
            cwd=roles_run_dir,
            capture_output=True,
            text=True
        )
        # Don't assert success here as container might not exist
        # This is just cleanup

    @pytest.mark.parametrize(
        "plugin_name",
        ["vim-airline", "nerdtree", "fzf-vim", "vim-gitgutter", "vim-fugitive"],
    )
    def test_vim_plugin_configuration(self, collection_root, plugin_name):
        """Test vim plugin configurations are valid."""
        defaults_file = collection_root / "roles" / "run" / "defaults" / "main.yml"
        
        # Read defaults file
        with open(defaults_file, 'r') as f:
            defaults = yaml.safe_load(f)
        
        # Check if plugin is in default configuration
        vim_plugins = defaults.get('vim_plugins', [])
        plugin_names = [plugin['name'] for plugin in vim_plugins]
        
        if plugin_name in plugin_names:
            # Find the plugin configuration
            plugin_config = next(p for p in vim_plugins if p['name'] == plugin_name)
            
            # Validate plugin configuration structure
            assert 'name' in plugin_config, f"Plugin {plugin_name} missing 'name' field"
            assert 'url' in plugin_config, f"Plugin {plugin_name} missing 'url' field"
            assert plugin_config['url'].startswith('https://'), f"Plugin {plugin_name} URL should use HTTPS"

    def test_ansible_playbook_syntax(self, collection_root):
        """Test that collection can be used in a playbook."""
        # Create a temporary playbook file
        playbook_content = """
---
- name: Test vim role
  hosts: localhost
  gather_facts: false
  collections:
    - webstack_builders.vim
  tasks:
    - name: Include vim role  
      ansible.builtin.include_role:
        name: run
      vars:
        vim_dir: /tmp/test-vim
        vim_rc: /tmp/test-vimrc
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(playbook_content)
            playbook_path = f.name
        
        try:
            # Test syntax check
            result = subprocess.run(
                ["ansible-playbook", "--syntax-check", playbook_path],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Playbook syntax check failed: {result.stderr}"
        finally:
            os.unlink(playbook_path)

    def test_role_argument_validation(self, collection_root):
        """Test role argument validation works."""
        # Test that we can import the argument specs
        arg_specs_file = collection_root / "roles" / "run" / "meta" / "argument_specs.yml"
        
        with open(arg_specs_file, 'r') as f:
            arg_specs = yaml.safe_load(f)
            
        # Validate basic structure
        assert 'argument_specs' in arg_specs
        assert 'main' in arg_specs['argument_specs']
        
        main_spec = arg_specs['argument_specs']['main']
        assert 'options' in main_spec
        
        # Check for key vim role options
        options = main_spec['options']
        expected_options = ['vim_dir', 'vim_rc', 'vim_plugins', 'vim_install_packages']
        
        for option in expected_options:
            assert option in options, f"Missing required option: {option}"