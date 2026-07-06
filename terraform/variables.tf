variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-central-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.micro is free-tier eligible)"
  type        = string
  default     = "t3.micro"
}

variable "app_image" {
  description = "Docker image for the API (published by CI to GHCR)"
  type        = string
  default     = "ghcr.io/YOUR_GITHUB/taskflow-api:latest"
}

variable "domain_name" {
  description = "Domain for the API (e.g. api.example.com). Empty = HTTP-only ALB without ACM."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for domain_name. Required when domain_name is set."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email for CloudWatch alarm + budget notifications. Empty = alarms exist but notify nobody."
  type        = string
  default     = ""
}

variable "ssh_key_name" {
  description = "EC2 key pair name for SSH access. Empty = no SSH."
  type        = string
  default     = ""
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH to the instance (e.g. your-ip/32). Empty = no SSH rule."
  type        = string
  default     = ""
}
