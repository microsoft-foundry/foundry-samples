#!/usr/bin/env sh
set -eu

if ! command -v sqlcmd >/dev/null 2>&1; then
  echo 'sqlcmd is required for the post-provision database permission grant.' >&2
  echo 'Install it from: https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-download-install' >&2
  exit 1
fi

sql_server_fqdn=$(azd env get-value SQL_SERVER_FQDN)
sql_server_name=$(azd env get-value SQL_SERVER_NAME)
sql_database_name=$(azd env get-value SQL_DATABASE_NAME)
namespace_name=$(azd env get-value CONNECTOR_NAMESPACE_NAME)
namespace_principal_id=$(azd env get-value CONNECTOR_NAMESPACE_PRINCIPAL_ID)
subscription_id=$(azd env get-value AZURE_SUBSCRIPTION_ID)
resource_group_name=$(azd env get-value AZURE_FOUNDRY_RESOURCE_GROUP)
deployer_ip_address=${DEPLOYER_IP_ADDRESS:-}

if [ -z "$sql_server_fqdn" ] || [ -z "$sql_server_name" ] || [ -z "$sql_database_name" ] || [ -z "$namespace_name" ] || [ -z "$namespace_principal_id" ] || [ -z "$subscription_id" ] || [ -z "$resource_group_name" ]; then
  echo 'Required SQL or Connector Namespace outputs are missing.' >&2
  exit 1
fi

firewall_rule_cleanup_required=false
cleanup() {
  exit_code=$?
  trap - EXIT
  trap '' INT TERM
  if [ "$firewall_rule_cleanup_required" = true ]; then
    if ! az sql server firewall-rule delete \
      --subscription "$subscription_id" \
      --resource-group "$resource_group_name" \
      --server "$sql_server_name" \
      --name AllowDeployerIp \
      --only-show-errors >/dev/null; then
      echo 'Failed to remove temporary Azure SQL firewall rule AllowDeployerIp.' >&2
      echo "Remove it manually: az sql server firewall-rule delete --subscription $subscription_id --resource-group $resource_group_name --server $sql_server_name --name AllowDeployerIp" >&2
      if [ "$exit_code" -eq 0 ]; then
        exit_code=1
      fi
    fi
  fi
  if [ "$exit_code" -eq 0 ]; then
    echo "AdventureWorksLT is ready with ${product_count} products."
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -z "$deployer_ip_address" ]; then
  if probe_output=$(sqlcmd -S "$sql_server_fqdn" -d "$sql_database_name" -G -b -Q 'SELECT 1;' 2>&1); then
    echo 'Local Azure SQL access is already allowed; no temporary firewall rule is needed.'
  else
    deployer_ip_address=$(printf '%s\n' "$probe_output" | sed -n "s/.*Client with IP address '\([0-9.]*\)'.*/\1/p" | head -n 1)
    if [ -z "$deployer_ip_address" ] || ! printf '%s\n' "$deployer_ip_address" | awk -F. '
      NF != 4 { exit 1 }
      { for (i = 1; i <= 4; i++) if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1 }
    '; then
      printf '%s\n' "$probe_output" >&2
      echo 'Could not determine the client IPv4 address from the Azure SQL firewall response.' >&2
      echo 'Set DEPLOYER_IP_ADDRESS or add your client IP in Azure SQL networking, then rerun azd up.' >&2
      exit 1
    fi
  fi
fi

if [ -n "$deployer_ip_address" ]; then
  firewall_rule_cleanup_required=true
  az sql server firewall-rule create \
    --subscription "$subscription_id" \
    --resource-group "$resource_group_name" \
    --server "$sql_server_name" \
    --name AllowDeployerIp \
    --start-ip-address "$deployer_ip_address" \
    --end-ip-address "$deployer_ip_address" \
    --only-show-errors >/dev/null
fi

grant_sql="
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'${namespace_name}')
BEGIN
  CREATE USER [${namespace_name}] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '${namespace_principal_id}';
END;
IF ISNULL(IS_ROLEMEMBER('db_datareader', '${namespace_name}'), 0) = 0
BEGIN
  ALTER ROLE db_datareader ADD MEMBER [${namespace_name}];
END;
GRANT VIEW DEFINITION TO [${namespace_name}];
"

if ! sqlcmd -S "$sql_server_fqdn" -d "$sql_database_name" -G -b -Q "$grant_sql"; then
  echo 'Local Azure SQL access failed.' >&2
  echo 'Set DEPLOYER_IP_ADDRESS in the azd environment or add your client IP in Azure SQL networking, then rerun azd up.' >&2
  exit 1
fi

if ! product_count_output=$(sqlcmd -S "$sql_server_fqdn" -d "$sql_database_name" -G -b -h -1 -W -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM SalesLT.Product;'); then
  echo 'Failed to verify AdventureWorksLT sample data.' >&2
  exit 1
fi
product_count=$(printf '%s' "$product_count_output" | tr -d '[:space:]')
