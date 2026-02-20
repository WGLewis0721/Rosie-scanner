variable "region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "rosie"
}

variable "vpc_id" {
  description = "VPC ID for the ECS service"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the ECS service and ALB"
  type        = list(string)
}

variable "api_image" {
  description = "Docker image URI for the Rosie API"
  type        = string
  default     = "rosie:latest"
}

variable "task_cpu" {
  description = "CPU units for the ECS task"
  type        = string
  default     = "512"
}

variable "task_memory" {
  description = "Memory (MB) for the ECS task"
  type        = string
  default     = "1024"
}

variable "desired_count" {
  description = "Desired number of ECS task instances"
  type        = number
  default     = 1
}

variable "llm_provider" {
  description = "LLM provider to use (bedrock, ollama, openai)"
  type        = string
  default     = "bedrock"
}

variable "opensearch_host" {
  description = "OpenSearch host"
  type        = string
  default     = "localhost"
}

variable "internal_alb" {
  description = "Whether the ALB should be internal"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project   = "rosie"
    ManagedBy = "terraform"
  }
}
