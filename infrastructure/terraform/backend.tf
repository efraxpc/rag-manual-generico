terraform {
  # Estado local para comenzar. Migra a un backend "azurerm" antes de trabajar
  # en equipo o ejecutar Terraform desde CI/CD.
  backend "local" {}
}
