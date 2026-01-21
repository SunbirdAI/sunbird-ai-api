terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.49.0"
    }
  }
}

provider "azurerm" {
  features {}

  # Optional: Specify subscription ID explicitly
  # If not provided, uses the current Azure CLI subscription
  subscription_id = var.subscription_id
}
