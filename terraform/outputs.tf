output "api_url" {
  description = "Where the API answers"
  value       = local.has_domain ? "https://${var.domain_name}" : "http://${aws_lb.main.dns_name}"
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "instance_public_ip" {
  description = "For SSH (if a key was configured)"
  value       = aws_instance.api.public_ip
}

output "log_group" {
  description = "CloudWatch log group with the structured JSON logs"
  value       = aws_cloudwatch_log_group.api.name
}
