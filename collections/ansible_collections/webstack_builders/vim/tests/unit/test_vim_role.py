"""Unit tests for vim role components."""

from __future__ import absolute_import, division, print_function

import pytest
import yaml
import os
from pathlib import Path


class TestVimRoleDefaults:
    """Test vim role default variables."""

    def test_default_vars_exist(self):
        """Test that default variables file exists and is valid."""
        defaults_file = Path("roles/run/defaults/main.yml")
        assert defaults_file.exists(), "Default variables file not found"

        with open(defaults_file, 'r') as f:
            defaults = yaml.safe_load(f)

        assert defaults is not None, "Defaults file is empty or invalid YAML"

    def test_vim_plugins_default_structure(self):
        """Test that default vim_plugins has correct structure."""
        defaults_file = Path("roles/run/defaults/main.yml")

        with open(defaults_file, 'r') as f:
            defaults = yaml.safe_load(f)

        assert 'vim_plugins' in defaults, "vim_plugins not defined in defaults"
        assert isinstance(defaults['vim_plugins'], list), "vim_plugins should be a list"

        for plugin in defaults['vim_plugins']:
            assert 'name' in plugin, f"Plugin {plugin} missing 'name' field"
            assert 'url' in plugin, f"Plugin {plugin} missing 'url' field"
            assert plugin['url'].startswith('https://'), f"Plugin {plugin['name']} URL should use HTTPS"

    def test_vim_install_packages_default(self):
        """Test that default vim_install_packages is properly defined."""
        defaults_file = Path("roles/run/defaults/main.yml")

        with open(defaults_file, 'r') as f:
            defaults = yaml.safe_load(f)

        if 'vim_install_packages' in defaults:
            assert isinstance(defaults['vim_install_packages'], list), "vim_install_packages should be a list"
            for package in defaults['vim_install_packages']:
                assert isinstance(package, str), f"Package {package} should be a string"


class TestVimRoleTasks:
    """Test vim role tasks structure."""

    def test_main_tasks_exist(self):
        """Test that main tasks file exists."""
        tasks_file = Path("roles/run/tasks/main.yml")
        assert tasks_file.exists(), "Main tasks file not found"

    def test_tasks_yaml_validity(self):
        """Test that tasks file is valid YAML."""
        tasks_file = Path("roles/run/tasks/main.yml")

        with open(tasks_file, 'r') as f:
            tasks = yaml.safe_load(f)

        assert tasks is not None, "Tasks file is empty or invalid YAML"
        assert isinstance(tasks, list), "Tasks should be a list"

    def test_validate_tasks_exist(self):
        """Test that validation tasks exist if referenced."""
        validate_file = Path("roles/run/tasks/validate.yml")
        if validate_file.exists():
            with open(validate_file, 'r') as f:
                validate_tasks = yaml.safe_load(f)

            assert validate_tasks is not None, "Validate tasks file is empty or invalid YAML"
            assert isinstance(validate_tasks, list), "Validate tasks should be a list"


class TestVimRoleMeta:
    """Test vim role metadata."""

    def test_meta_main_exists(self):
        """Test that meta/main.yml exists."""
        meta_file = Path("roles/run/meta/main.yml")
        assert meta_file.exists(), "Meta main file not found"

    def test_meta_yaml_validity(self):
        """Test that meta file is valid YAML."""
        meta_file = Path("roles/run/meta/main.yml")

        with open(meta_file, 'r') as f:
            meta = yaml.safe_load(f)

        assert meta is not None, "Meta file is empty or invalid YAML"

    def test_argument_specs_exist(self):
        """Test that argument specs exist if referenced."""
        arg_spec_file = Path("roles/run/meta/argument_specs.yml")
        if arg_spec_file.exists():
            with open(arg_spec_file, 'r') as f:
                arg_specs = yaml.safe_load(f)

            assert arg_specs is not None, "Argument specs file is empty or invalid YAML"


class TestVimRoleFiles:
    """Test vim role files and templates."""

    def test_vimrc_file_exists(self):
        """Test that vimrc file exists."""
        vimrc_file = Path("roles/run/files/vimrc")
        if vimrc_file.exists():
            # If vimrc file exists, verify it's not empty
            content = vimrc_file.read_text()
            assert len(content.strip()) > 0, "vimrc file should not be empty"

    def test_role_directory_structure(self):
        """Test that role has proper directory structure."""
        role_dir = Path("roles/run")

        # Required directories
        required_dirs = ['tasks', 'defaults', 'meta']
        for dir_name in required_dirs:
            dir_path = role_dir / dir_name
            assert dir_path.exists(), f"Required directory {dir_name} not found"
            assert dir_path.is_dir(), f"{dir_name} should be a directory"

        # Optional directories
        optional_dirs = ['files', 'templates', 'handlers', 'vars']
        for dir_name in optional_dirs:
            dir_path = role_dir / dir_name
            if dir_path.exists():
                assert dir_path.is_dir(), f"{dir_name} should be a directory if it exists"


class TestMoleculeConfiguration:
    """Test Molecule configuration."""

    def test_molecule_scenarios_exist(self):
        """Test that Molecule scenarios are properly configured."""
        molecule_dir = Path("roles/run/molecule")
        if molecule_dir.exists():
            # Check for default scenario
            default_scenario = molecule_dir / "default"
            assert default_scenario.exists(), "Default Molecule scenario not found"

            # Check for molecule.yml in default scenario
            molecule_yml = default_scenario / "molecule.yml"
            assert molecule_yml.exists(), "molecule.yml not found in default scenario"

    def test_molecule_playbooks_exist(self):
        """Test that required Molecule playbooks exist."""
        molecule_dir = Path("roles/run/molecule")
        if molecule_dir.exists():
            for scenario in molecule_dir.iterdir():
                if scenario.is_dir():
                    converge_yml = scenario / "converge.yml"
                    verify_yml = scenario / "verify.yml"

                    assert converge_yml.exists(), f"converge.yml not found in {scenario.name} scenario"
                    assert verify_yml.exists(), f"verify.yml not found in {scenario.name} scenario"

    def test_molecule_yaml_validity(self):
        """Test that Molecule YAML files are valid."""
        molecule_dir = Path("roles/run/molecule")
        if molecule_dir.exists():
            for scenario in molecule_dir.iterdir():
                if scenario.is_dir():
                    for yml_file in scenario.glob("*.yml"):
                        with open(yml_file, 'r') as f:
                            try:
                                yaml.safe_load(f)
                            except yaml.YAMLError as e:
                                pytest.fail(f"Invalid YAML in {yml_file}: {e}")


@pytest.mark.parametrize(
    "file_path,required_keys",
    [
        ("roles/run/defaults/main.yml", ["vim_plugins"]),
        ("roles/run/meta/main.yml", ["galaxy_info"]),
    ],
)
def test_required_yaml_keys(file_path, required_keys):
    """Test that required keys exist in YAML files.

    Args:
        file_path: Path to the YAML file to test
        required_keys: List of keys that must exist in the file
    """
    file_path = Path(file_path)
    if file_path.exists():
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        for key in required_keys:
            assert key in data, f"Required key '{key}' not found in {file_path}"


def test_vim_role_consistency():
    """Test overall vim role consistency and completeness."""
    role_dir = Path("roles/run")

    # Test that role directory exists
    assert role_dir.exists(), "Vim role directory not found"

    # Test that main.yml files exist in required directories
    required_files = [
        "tasks/main.yml",
        "defaults/main.yml",
        "meta/main.yml"
    ]

    for file_path in required_files:
        full_path = role_dir / file_path
        assert full_path.exists(), f"Required file {file_path} not found"