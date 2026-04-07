# ---------------------------------------------------------------------------
# Data sources — look up existing shared resources
# ---------------------------------------------------------------------------
data "openstack_networking_network_v2" "provider" {
  name     = var.external_network
  external = true
}

data "openstack_compute_flavor_v2" "flavor" {
  name = var.flavor
}

data "openstack_images_image_v2" "image" {
  name        = var.image
  most_recent = true
}

# ---------------------------------------------------------------------------
# Self-service (tenant) network
# ---------------------------------------------------------------------------
resource "openstack_networking_network_v2" "tenant" {
  name           = "test-net"
  admin_state_up = true
}

resource "openstack_networking_subnet_v2" "tenant" {
  name            = "test-subnet"
  network_id      = openstack_networking_network_v2.tenant.id
  cidr            = var.tenant_cidr
  dns_nameservers = var.dns_nameservers
}

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
resource "openstack_networking_router_v2" "router" {
  name                = "test-router"
  external_network_id = data.openstack_networking_network_v2.provider.id
}

resource "openstack_networking_router_interface_v2" "router_if" {
  router_id = openstack_networking_router_v2.router.id
  subnet_id = openstack_networking_subnet_v2.tenant.id
}

# ---------------------------------------------------------------------------
# Security group
# ---------------------------------------------------------------------------
resource "openstack_networking_secgroup_v2" "test" {
  name        = "test-sg"
  description = "Allow ICMP and SSH"
}

resource "openstack_networking_secgroup_rule_v2" "icmp" {
  security_group_id = openstack_networking_secgroup_v2.test.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "icmp"
}

resource "openstack_networking_secgroup_rule_v2" "ssh" {
  security_group_id = openstack_networking_secgroup_v2.test.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
}

# ---------------------------------------------------------------------------
# Port, instance, floating IP
# ---------------------------------------------------------------------------
resource "openstack_networking_port_v2" "test" {
  name       = "test-port"
  network_id = openstack_networking_network_v2.tenant.id

  security_group_ids = [openstack_networking_secgroup_v2.test.id]

  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.tenant.id
  }

  depends_on = [openstack_networking_router_interface_v2.router_if]
}

resource "openstack_compute_instance_v2" "test" {
  name      = "test-instance"
  image_id  = data.openstack_images_image_v2.image.id
  flavor_id = data.openstack_compute_flavor_v2.flavor.id

  network {
    port = openstack_networking_port_v2.test.id
  }
}

resource "openstack_networking_floatingip_v2" "test" {
  pool = data.openstack_networking_network_v2.provider.name
}

resource "openstack_networking_floatingip_associate_v2" "test" {
  floating_ip = openstack_networking_floatingip_v2.test.address
  port_id     = openstack_networking_port_v2.test.id
}
