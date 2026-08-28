# Remote state lives in the bootstrap resource group (created once by
# infra/bootstrap/bootstrap.sh, NOT managed by this configuration — otherwise
# `terraform destroy` would delete the state it is writing to).
#
# Initialise with:
#   terraform init -backend-config=envs/dev.backend.hcl
terraform {
  backend "azurerm" {}
}
