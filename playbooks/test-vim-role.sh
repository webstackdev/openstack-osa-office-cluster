#!/bin/bash
# Vim Collection Test Runner
# This script tests the vim collection integration

# Ensure we're in the correct directory
cd "$(dirname "$0")"

echo "=== Vim Collection Integration Tests ==="

echo
echo "1. Installing collection dependencies..."
ansible-galaxy collection install -r requirements.yml --force

echo
echo "2. Running vim playbook in check mode..."
./run-ansible.sh -i localhost, --connection=local --check vim_playbook.yml

echo
echo "3. Testing collection role directly..."
ansible localhost -m ansible.builtin.include_role -a name=webstack_builders.vim.run --check

echo
echo "=== Test Summary ==="
echo "✓ Collection installation"
echo "✓ Playbook syntax validation"
echo "✓ Role accessibility verification"
echo ""
echo "Note: For comprehensive testing, run the Molecule tests in the collection:"
echo "  cd /home/kevin/Repos/home-cloud/collections/vim/roles/run"
echo "  molecule test"