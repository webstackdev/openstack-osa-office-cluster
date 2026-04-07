variable "cloud_name" {
  description = "Name of the cloud entry in clouds.yaml"
  type        = string
  default     = "home-cloud"
}

variable "external_network" {
  description = "Name of the existing external provider network"
  type        = string
  default     = "provider-net"
}

variable "image" {
  description = "Name of the image to use"
  type        = string
  default     = "cirros"
}

variable "flavor" {
  description = "Name of the flavor to use"
  type        = string
  default     = "m1.tiny"
}

variable "tenant_cidr" {
  description = "CIDR for the self-service tenant network"
  type        = string
  default     = "10.0.0.0/24"
}

variable "dns_nameservers" {
  description = "DNS servers for the tenant subnet"
  type        = list(string)
  default     = ["8.8.8.8"]
}
