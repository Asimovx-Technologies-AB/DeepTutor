<#
.SYNOPSIS
  One-time Terraform remote-state bootstrap (PowerShell equivalent of bootstrap.sh).

.DESCRIPTION
  Creates the storage account that holds Terraform state, in its own resource
  group. Keeping it out of rg-deeptutor-dev means `terraform destroy` cannot
  delete the state file it is writing to.

.EXAMPLE
  ./bootstrap.ps1 -SubscriptionId 00000000-0000-0000-0000-000000000000
#>
param(
    [Parameter(Mandatory = $true)][string]$SubscriptionId,
    [string]$Location = "centralindia"
)

$ErrorActionPreference = "Stop"

$Project        = "deeptutor"
$StateRg        = "rg-$Project-tfstate"
$StateContainer = "tfstate"

az account set --subscription $SubscriptionId

# Deterministic, globally unique, stable across re-runs.
$sha    = [System.Security.Cryptography.SHA1]::Create()
$bytes  = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("$SubscriptionId-$Project-tfstate"))
$suffix = (($bytes | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 8)
$StateSa = "st${Project}tf${suffix}"

Write-Host "==> Resource group: $StateRg ($Location)"
az group create --name $StateRg --location $Location `
    --tags project=$Project purpose=terraform-state managed_by=bootstrap --output none

Write-Host "==> Storage account: $StateSa"
az storage account create --name $StateSa --resource-group $StateRg --location $Location `
    --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 `
    --allow-blob-public-access false --output none

Write-Host "==> Enabling blob versioning and soft delete"
az storage account blob-service-properties update --account-name $StateSa `
    --resource-group $StateRg --enable-versioning true --enable-delete-retention true `
    --delete-retention-days 30 --output none

Write-Host "==> Container: $StateContainer"
az storage container create --name $StateContainer --account-name $StateSa `
    --auth-mode login --output none

Write-Host @"

─────────────────────────────────────────────────────────────────────────────
Bootstrap complete.

Write this into infra/terraform/envs/dev.backend.hcl:

  resource_group_name  = "$StateRg"
  storage_account_name = "$StateSa"
  container_name       = "$StateContainer"
  key                  = "dev.terraform.tfstate"
  use_azuread_auth     = true

And set these GitHub repository variables:

  AZURE_SUBSCRIPTION_ID   = $SubscriptionId
  TFSTATE_RESOURCE_GROUP  = $StateRg
  TFSTATE_STORAGE_ACCOUNT = $StateSa
  TFSTATE_CONTAINER       = $StateContainer

Next: create the GitHub OIDC identity — see infra/README.md, "CI identity".
─────────────────────────────────────────────────────────────────────────────
"@
