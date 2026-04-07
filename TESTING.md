# Testing

## Test Swift

# Create a test container, upload a file, download it, compare

```bash
echo "Hello from Swift" > /tmp/swift-test.txt
openstack --os-cloud home-cloud container create test-container
openstack --os-cloud home-cloud object create test-container /tmp/swift-test.txt --name hello.txt
openstack --os-cloud home-cloud object list test-container
openstack --os-cloud home-cloud object save test-container hello.txt --file /tmp/swift-download.txt
echo "--- Uploaded ---" && cat /tmp/swift-test.txt
echo "--- Downloaded ---" && cat /tmp/swift-download.txt
diff /tmp/swift-test.txt /tmp/swift-download.txt && echo "OK: Files match"
```

## Create test server with CLI

### 1. Create provider (external) network

```bash
openstack network create --external --provider-network-type flat \
  --provider-physical-network physnet1 provider-net

openstack subnet create --network provider-net --subnet-range 192.168.2.0/24 \
  --gateway 192.168.2.1 --allocation-pool start=192.168.2.100,end=192.168.2.200 \
  --no-dhcp provider-subnet
```

### 2. Create self-service network, subnet, router

```bash
openstack network create test-net
openstack subnet create --network test-net --subnet-range 10.0.0.0/24 \
  --dns-nameserver 8.8.8.8 test-subnet
openstack router create test-router
openstack router set --external-gateway provider-net test-router
openstack router add subnet test-router test-subnet
```

### 3. Create flavor

```bash
openstack flavor create --ram 256 --disk 1 --vcpus 1 m1.tiny
```

### 4. Upload cirros image

```bash
curl -sL -o /tmp/cirros.img \
  http://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img

openstack image create --disk-format qcow2 --container-format bare \
  --public --file /tmp/cirros.img cirros
```

### 5. Add security group rules (ICMP + SSH)

```bash
openstack security group rule create --protocol icmp default
openstack security group rule create --protocol tcp --dst-port 22 default
```

### 6. Launch instance

```bash
openstack server create --flavor m1.tiny --image cirros --network test-net test-instance
```

### 7. Create and assign floating IP

```bash
openstack floating ip create provider-net
openstack server add floating ip test-instance <floating-ip>
```

## Teardown (CLI)

To destroy the test resources without Heat, run in reverse dependency order:

```bash
# Remove floating IP from instance and delete it
openstack server remove floating ip test-instance <floating-ip>
openstack floating ip delete <floating-ip>

# Delete instance
openstack server delete test-instance

# Remove subnet from router, remove gateway, delete router
openstack router remove subnet test-router test-subnet
openstack router unset --external-gateway test-router
openstack router delete test-router

# Delete subnet, network
openstack subnet delete test-subnet
openstack network delete test-net

# Optionally clean up flavor and image
openstack flavor delete m1.tiny
openstack image delete cirros
```

## Heat Orchestration Template for Test

Save as `test-stack.yml`:

```yaml
heat_template_version: 2021-04-16

description: Test stack — creates a self-service network, router, and cirros instance with a floating IP.

parameters:
  external_network:
    type: string
    default: provider-net
    description: Name of the external provider network
  image:
    type: string
    default: cirros
    description: Name of the image to use
  flavor:
    type: string
    default: m1.tiny
    description: Name of the flavor to use

resources:
  test_net:
    type: OS::Neutron::Net
    properties:
      name: test-net

  test_subnet:
    type: OS::Neutron::Subnet
    properties:
      name: test-subnet
      network: { get_resource: test_net }
      cidr: 10.0.0.0/24
      dns_nameservers:
        - 8.8.8.8

  test_router:
    type: OS::Neutron::Router
    properties:
      name: test-router
      external_gateway_info:
        network: { get_param: external_network }

  router_interface:
    type: OS::Neutron::RouterInterface
    properties:
      router: { get_resource: test_router }
      subnet: { get_resource: test_subnet }

  security_group:
    type: OS::Neutron::SecurityGroup
    properties:
      name: test-sg
      rules:
        - protocol: icmp
          direction: ingress
        - protocol: tcp
          port_range_min: 22
          port_range_max: 22
          direction: ingress

  test_port:
    type: OS::Neutron::Port
    properties:
      network: { get_resource: test_net }
      security_groups:
        - { get_resource: security_group }
    depends_on: router_interface

  test_instance:
    type: OS::Nova::Server
    properties:
      name: test-instance
      image: { get_param: image }
      flavor: { get_param: flavor }
      networks:
        - port: { get_resource: test_port }

  floating_ip:
    type: OS::Neutron::FloatingIP
    properties:
      floating_network: { get_param: external_network }

  floating_ip_assoc:
    type: OS::Neutron::FloatingIPAssociation
    properties:
      floatingip_id: { get_resource: floating_ip }
      port_id: { get_resource: test_port }

outputs:
  instance_ip:
    description: Private IP of the test instance
    value: { get_attr: [test_instance, first_address] }
  floating_ip_address:
    description: Floating IP assigned to the test instance
    value: { get_attr: [floating_ip, floating_ip_address] }
```

### Deploy with Heat

```bash
openstack stack create -t test-stack.yml test-stack
openstack stack show test-stack        # wait for CREATE_COMPLETE
openstack stack output show test-stack floating_ip_address
```

### Destroy with Heat

```bash
openstack stack delete -y test-stack
```

This deletes the instance, floating IP, port, router interface, router, subnet, and network in the correct dependency order.

## Terraform Deployment

This achieves the same test stack using the OpenStack Terraform provider. Like the Heat example, it assumes the provider network, flavor, and image already exist as shared infrastructure and looks them up via data sources.

### Prerequisites

Install the Terraform CLI: <https://developer.hashicorp.com/terraform/install>

Ensure you have a `clouds.yaml` (typically at `~/.config/openstack/clouds.yaml` or `/etc/openstack/clouds.yaml`) with credentials for your cloud. The provider network, flavor, and image must already exist (see the CLI steps above).

### Directory structure

```
terraform/test-stack/
├── main.tf
├── variables.tf
├── outputs.tf
└── versions.tf
```

### Deploy with Terraform

```bash
cd terraform/test-stack
terraform init      # download the OpenStack provider
terraform plan      # preview what will be created
terraform apply     # create all resources (confirm with 'yes')
```

### Destroy with Terraform

```bash
terraform destroy   # remove all resources (confirm with 'yes')
```

Terraform tracks the full dependency graph in its state file and deletes resources in the correct order. The cirros image uses hardcoded default credentials of username `cirros` with password `gocubsgo`. SSH to the floating IP:

```bash
ssh cirros@192.168.2.133
```
