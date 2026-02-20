output "api_url" {
  description = "URL of the Rosie API via ALB"
  value       = "http://${aws_lb.rosie.dns_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.rosie.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.rosie_api.name
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.rosie.dns_name
}
