# Backend config for `terraform init -backend-config=envs/dev.backend.hcl`.
# The storage account name is printed by infra/bootstrap/bootstrap.sh.
resource_group_name  = "rg-deeptutor-tfstate"
storage_account_name = "REPLACE_WITH_BOOTSTRAP_OUTPUT"
container_name       = "tfstate"
key                  = "dev.terraform.tfstate"
use_azuread_auth     = true
