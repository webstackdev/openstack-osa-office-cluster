output "instance_private_ip" {
  description = "Private IP of the test instance"
  value       = openstack_compute_instance_v2.test.access_ip_v4
}

output "floating_ip_address" {
  description = "Floating IP assigned to the test instance"
  value       = openstack_networking_floatingip_v2.test.address
}
