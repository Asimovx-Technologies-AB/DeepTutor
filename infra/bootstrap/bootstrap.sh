#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-time Terraform remote-state bootstrap.
#
# Creates the storage account that holds Terraform state. This lives in its own
# resource group on purpose: if it sat in rg-deeptutor-dev, a `terraform
# destroy` would delete the state file mid-run and orphan every resource.
#
# Run once per subscription:
#   ./bootstrap.sh <subscription-id> [location]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SUBSCRIPTION_ID="${1:-}"
LOCATION="${2:-swedencentral}"
PROJECT="deeptutor"

STATE_RG="rg-${PROJECT}-tfstate"
STATE_CONTAINER="tfstate"

if [[ -z "$SUBSCRIPTION_ID" ]]; then
  echo "usage: $0 <subscription-id> [location]" >&2
  exit 1
fi

az account set --subscription "$SUBSCRIPTION_ID"

# Deterministic, globally unique, and stable across re-runs.
SUFFIX="$(printf '%s' "${SUBSCRIPTION_ID}-${PROJECT}-tfstate" | sha1sum | cut -c1-8)"
STATE_SA="st${PROJECT}tf${SUFFIX}"

echo "==> Resource group: ${STATE_RG} (${LOCATION})"
az group create \
  --name "$STATE_RG" \
  --location "$LOCATION" \
  --tags project="$PROJECT" purpose=terraform-state managed_by=bootstrap \
  --output none

echo "==> Storage account: ${STATE_SA}"
az storage account create \
  --name "$STATE_SA" \
  --resource-group "$STATE_RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --output none

# Versioning turns a corrupted or truncated state push into a two-minute
# recovery instead of a rebuild-from-scratch.
echo "==> Enabling blob versioning and soft delete"
az storage account blob-service-properties update \
  --account-name "$STATE_SA" \
  --resource-group "$STATE_RG" \
  --enable-versioning true \
  --enable-delete-retention true \
  --delete-retention-days 30 \
  --output none

echo "==> Container: ${STATE_CONTAINER}"
az storage container create \
  --name "$STATE_CONTAINER" \
  --account-name "$STATE_SA" \
  --auth-mode login \
  --output none

cat <<EOF

─────────────────────────────────────────────────────────────────────────────
Bootstrap complete.

Write this into infra/terraform/envs/dev.backend.hcl:

  resource_group_name  = "${STATE_RG}"
  storage_account_name = "${STATE_SA}"
  container_name       = "${STATE_CONTAINER}"
  key                  = "dev.terraform.tfstate"
  use_azuread_auth     = true

And set these GitHub repository variables:

  AZURE_SUBSCRIPTION_ID   = ${SUBSCRIPTION_ID}
  TFSTATE_RESOURCE_GROUP  = ${STATE_RG}
  TFSTATE_STORAGE_ACCOUNT = ${STATE_SA}
  TFSTATE_CONTAINER       = ${STATE_CONTAINER}

Next: create the GitHub OIDC identity — see infra/README.md, "CI identity".
─────────────────────────────────────────────────────────────────────────────
EOF
