variable "subscription_id" {
  description = "Azure subscription ID (optional - uses current subscription if not specified)"
  type        = string
  default     = null
}

variable "location" {
  description = "The Azure region where resources will be created"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name (e.g., prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "sunbird-ai"
}

variable "acr_sku" {
  description = "SKU for Azure Container Registry"
  type        = string
  default     = "Basic"
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }
}

variable "log_analytics_retention_days" {
  description = "Number of days to retain logs in Log Analytics"
  type        = number
  default     = 30
  validation {
    condition     = var.log_analytics_retention_days >= 30 && var.log_analytics_retention_days <= 730
    error_message = "Retention days must be between 30 and 730."
  }
}

variable "container_app_min_replicas" {
  description = "Minimum number of container app replicas"
  type        = number
  default     = 1
}

variable "container_app_max_replicas" {
  description = "Maximum number of container app replicas"
  type        = number
  default     = 10
}

variable "container_cpu" {
  description = "CPU cores allocated to each container instance"
  type        = number
  default     = 0.5
}

variable "container_memory" {
  description = "Memory (in Gi) allocated to each container instance"
  type        = string
  default     = "1.0Gi"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8080
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Environment = "Production"
    Project     = "Sunbird-AI-API"
    ManagedBy   = "Terraform"
  }
}
