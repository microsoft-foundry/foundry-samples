"""Compile-only RBAC contracts. Uses Bicep CLI; never authenticates or deploys."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


SCENARIO = Path(__file__).resolve().parents[1]
ENTRY_POINTS = ("main", "add-project", "add-existing-project")
STORAGE_OWNER = "b7e6dc6d-f1e8-4753-8033-0f276bb0955b"
COSMOS_CONTRIBUTOR = "00000000-0000-0000-0000-000000000002"
AZURE_ROLE = "Microsoft.Authorization/roleAssignments"
COSMOS_ROLE = "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments"


def without_generator_metadata(value):
    """Ignore compiler-version/hash metadata, never resource or parameter values."""
    value = deepcopy(value)

    def visit(node):
        if isinstance(node, dict):
            metadata = node.get("metadata")
            if isinstance(metadata, dict) and "_generator" in metadata:
                del metadata["_generator"]
                if not metadata:
                    del node["metadata"]
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return value


def resource_list(template):
    entries = template.get("resources", [])
    return entries.values() if isinstance(entries, dict) else entries


def resources(template):
    for resource in resource_list(template):
        yield resource
        nested = resource.get("properties", {}).get("template")
        if nested:
            yield from resources(nested)


def runtime_role_modules(template):
    """Select actual role resources, not module filenames or comments."""
    result = {}
    for module in template["resources"]:
        nested = module.get("properties", {}).get("template", {})
        for role in resource_list(nested):
            if (
                role["type"] == AZURE_ROLE
                and STORAGE_OWNER in role["properties"]["roleDefinitionId"]
            ):
                key = "storage"
            elif role["type"] == COSMOS_ROLE:
                key = "cosmos"
            else:
                continue
            if key in result:
                raise AssertionError(f"Duplicate {key} runtime grant")
            result[key] = (module, nested, role)
    return result


class RoleAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cli = os.environ.get("BICEP_CLI") or shutil.which("bicep")
        if not cli:
            candidate = (
                Path.home()
                / ".azure"
                / "bin"
                / ("bicep.exe" if os.name == "nt" else "bicep")
            )
            if candidate.is_file():
                cli = str(candidate)
        if not cli:
            raise RuntimeError(
                "Install Bicep CLI or set BICEP_CLI to its executable path"
            )

        def compile_file(command, path):
            result = subprocess.run(
                [cli, command, str(path), "--stdout"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=False,
            )
            if result.returncode:
                raise AssertionError(
                    f"Bicep compilation failed: {path.name}\n{result.stderr}"
                )
            return json.loads(result.stdout)

        cls.templates = {}
        cls.parameters = {}
        for entry in ENTRY_POINTS:
            cls.templates[entry] = compile_file("build", SCENARIO / f"{entry}.bicep")
            output = compile_file("build-params", SCENARIO / f"{entry}.bicepparam")
            cls.parameters[entry] = json.loads(output["parametersJson"])

    def test_every_entrypoint_enables_both_runtime_grants_by_default(self):
        for entry, template in self.templates.items():
            with self.subTest(entry=entry):
                flag = (
                    "assignRoles"
                    if entry == "add-existing-project"
                    else "assignContainerRoles"
                )
                self.assertIs(template["parameters"][flag]["defaultValue"], True)
                modules = runtime_role_modules(template)
                self.assertEqual(set(modules), {"storage", "cosmos"})
                for module, _, role in modules.values():
                    self.assertEqual(module["condition"], f"[parameters('{flag}')]")
                    self.assertNotIn("condition", role)

    def test_samples_do_not_disable_runtime_grants(self):
        for entry, template in self.templates.items():
            with self.subTest(entry=entry):
                flag = (
                    "assignRoles"
                    if entry == "add-existing-project"
                    else "assignContainerRoles"
                )
                configured = self.parameters[entry]["parameters"].get(flag, {})
                self.assertIs(
                    configured.get(
                        "value", template["parameters"][flag]["defaultValue"]
                    ),
                    True,
                )

    def test_runtime_grants_target_project_identity_after_project_deployment(self):
        for entry, template in self.templates.items():
            for kind, (module, _, role) in runtime_role_modules(template).items():
                with self.subTest(entry=entry, role=kind):
                    principal = (
                        "aiProjectPrincipalId"
                        if kind == "storage"
                        else "projectPrincipalId"
                    )
                    expression = module["properties"]["parameters"][principal]["value"]
                    self.assertTrue(
                        expression.startswith(
                            "[reference(resourceId('Microsoft.Resources/deployments',"
                        )
                    )
                    self.assertTrue(
                        expression.endswith(".outputs.projectPrincipalId.value]")
                    )
                    self.assertIn(
                        ".outputs.projectWorkspaceIdGuid.value]",
                        json.dumps(module["properties"]["parameters"]),
                    )
                    self.assertTrue(module["dependsOn"])
                    self.assertEqual(
                        role["properties"]["principalId"],
                        f"[parameters('{principal}')]",
                    )

    def test_storage_grant_preserves_account_scope_and_abac(self):
        for entry, template in self.templates.items():
            with self.subTest(entry=entry):
                module, nested, role = runtime_role_modules(template)["storage"]
                prefix = "azureStorage" if entry == "main" else "storage"
                source = "variables" if entry == "main" else "parameters"
                self.assertEqual(
                    module["subscriptionId"], f"[{source}('{prefix}SubscriptionId')]"
                )
                self.assertEqual(
                    module["resourceGroup"], f"[{source}('{prefix}ResourceGroupName')]"
                )
                self.assertEqual(
                    role["scope"],
                    "[resourceId('Microsoft.Storage/storageAccounts', parameters('storageName'))]",
                )
                self.assertEqual(
                    role["properties"]["principalType"], "ServicePrincipal"
                )
                self.assertEqual(role["properties"]["conditionVersion"], "2.0")
                self.assertEqual(
                    role["properties"]["condition"], "[variables('conditionStr')]"
                )
                self.assertIn(
                    "parameters('workspaceId')", nested["variables"]["conditionStr"]
                )
                self.assertIn("*-azureml-agent", nested["variables"]["conditionStr"])
                self.assertIn("guid(", role["name"])

    def test_cosmos_grant_preserves_database_scope(self):
        for entry, template in self.templates.items():
            with self.subTest(entry=entry):
                module, nested, role = runtime_role_modules(template)["cosmos"]
                source = "variables" if entry == "main" else "parameters"
                self.assertEqual(
                    module["subscriptionId"], f"[{source}('cosmosDBSubscriptionId')]"
                )
                self.assertEqual(
                    module["resourceGroup"], f"[{source}('cosmosDBResourceGroupName')]"
                )
                self.assertIn(
                    COSMOS_CONTRIBUTOR, nested["variables"]["roleDefinitionId"]
                )
                self.assertIn(
                    "/dbs/enterprise_memory", nested["variables"]["accountScope"]
                )
                self.assertEqual(
                    role["properties"]["scope"], "[variables('accountScope')]"
                )
                self.assertIn("guid(", role["name"])

    def test_roles_do_not_precreate_service_owned_hosts_or_containers(self):
        forbidden = {
            "microsoft.cognitiveservices/accounts/capabilityhosts",
            "microsoft.cognitiveservices/accounts/projects/capabilityhosts",
            "microsoft.storage/storageaccounts/blobservices/containers",
            "microsoft.documentdb/databaseaccounts/sqldatabases",
            "microsoft.documentdb/databaseaccounts/sqldatabases/containers",
        }
        for entry, template in self.templates.items():
            with self.subTest(entry=entry):
                self.assertFalse(
                    forbidden
                    & {resource["type"].lower() for resource in resources(template)}
                )
                for _, nested, _ in runtime_role_modules(template).values():
                    self.assertEqual(len(nested["resources"]), 1)

    def test_account_role_opt_out_does_not_disable_main_runtime_roles(self):
        template = self.templates["main"]
        self.assertIn(
            "assignProjectStorageAndCosmosAccountRoles", template["parameters"]
        )
        for module, _, _ in runtime_role_modules(template).values():
            self.assertEqual(
                module["condition"], "[parameters('assignContainerRoles')]"
            )

    def test_sample_includes_acr_dns_zone_when_registry_enabled(self):
        parameters = self.parameters["main"]["parameters"]
        zone_map = parameters["existingDnsZones"]["value"]
        self.assertIn("privatelink.azurecr.io", zone_map)
        self.assertIn(
            "privatelink.azurecr.io", parameters["dnsZoneNames"]["value"]
        )
        self.assertIn(
            "privatelink.azurecr.io",
            self.templates["main"]["variables"]["resolvedExistingDnsZones"],
        )

    def test_existing_vnet_is_non_destructive_and_rejects_cross_subscription(self):
        template = self.templates["main"]
        self.assertTrue(template["parameters"]["reuseExistingSubnets"]["defaultValue"])
        module = next(
            item
            for item in template["resources"]
            if "existingVnetMustBeInDeploymentSubscription"
            in item.get("properties", {}).get("parameters", {})
        )
        self.assertTrue(
            module["name"].startswith("[format('vnet-{0}-deployment', uniqueString(")
        )
        self.assertLessEqual(len("vnet-" + "x" * 13 + "-deployment"), 64)
        parameter = module["properties"]["parameters"][
            "existingVnetMustBeInDeploymentSubscription"
        ]
        self.assertIn("Cross-subscription VNets are not supported", parameter)
        self.assertEqual(
            module["properties"]["template"]["parameters"][
                "existingVnetMustBeInDeploymentSubscription"
            ]["allowedValues"],
            ["supported"],
        )
        self.assertTrue(
            any("validate-existing-resources" in item for item in module["dependsOn"])
        )

    def test_service_endpoint_names_and_dependent_dns_are_conditional(self):
        template = self.templates["main"]
        self.assertFalse(
            template["parameters"]["useLegacyNetworkResourceNames"]["defaultValue"]
        )
        module = next(
            item
            for item in template["resources"]
            if "createDependentResourcePrivateEndpoints"
            in item.get("properties", {}).get("parameters", {})
        )
        self.assertIn(
            ".outputs.virtualNetworkLocation.value]",
            module["properties"]["parameters"]["privateEndpointLocation"]["value"],
        )
        resources = module["properties"]["template"]["resources"]
        endpoints = [
            item for item in resources if item["type"] == "Microsoft.Network/privateEndpoints"
        ]
        self.assertEqual(len(endpoints), 4)
        for endpoint in endpoints:
            self.assertEqual(
                endpoint["location"], "[parameters('privateEndpointLocation')]"
            )
            self.assertIn("parameters('useLegacyNetworkResourceNames')", endpoint["name"])
            self.assertIn("uniqueString(", endpoint["name"])
            self.assertIn("parameters('vnetName')", endpoint["name"])
        self.assertEqual(
            sum("condition" in endpoint for endpoint in endpoints), 3
        )

        for resource_type in (
            "Microsoft.Network/privateDnsZones",
            "Microsoft.Network/privateDnsZones/virtualNetworkLinks",
            "Microsoft.Network/privateEndpoints/privateDnsZoneGroups",
        ):
            items = [item for item in resources if item["type"] == resource_type]
            gated = [
                item for item in items
                if "parameters('createDependentResourcePrivateEndpoints')"
                in item.get("condition", "")
            ]
            self.assertEqual(len(gated), 3, resource_type)
        links = [
            item for item in resources
            if item["type"] == "Microsoft.Network/privateDnsZones/virtualNetworkLinks"
        ]
        self.assertEqual(len(links), 6)
        for link in links:
            self.assertIn("parameters('useLegacyNetworkResourceNames')", link["name"])
            self.assertIn("uniqueString(", link["name"])

    def test_new_account_uses_resolved_backing_resource_ids(self):
        template = self.templates["main"]
        account_modules = [
            module
            for module in template["resources"]
            if any(
                resource["type"] == "Microsoft.CognitiveServices/accounts"
                for resource in resource_list(
                    module.get("properties", {}).get("template", {})
                )
            )
        ]
        self.assertEqual(len(account_modules), 1)
        module = account_modules[0]
        nested = module["properties"]["template"]
        account = next(
            resource
            for resource in nested["resources"]
            if resource["type"] == "Microsoft.CognitiveServices/accounts"
        )
        self.assertEqual(account["apiVersion"], "2026-09-01")
        self.assertEqual(
            account["condition"], "[not(variables('useExistingAccount'))]"
        )
        self.assertEqual(
            account["properties"]["capabilitySettings"],
            "[parameters('capabilitySettings')]",
        )
        settings = module["properties"]["parameters"]["capabilitySettings"]["value"]
        self.assertEqual(set(settings), {"documentStore", "vectorStore", "blobStore"})
        for setting, output in (
            ("documentStore", "cosmosDBId"),
            ("vectorStore", "aiSearchID"),
            ("blobStore", "azureStorageId"),
        ):
            with self.subTest(setting=setting):
                self.assertIn("dependencies-{0}-deployment", settings[setting])
                self.assertTrue(settings[setting].endswith(f".outputs.{output}.value]"))
        self.assertTrue(
            any(
                "dependencies-{0}-deployment" in dependency
                for dependency in module["dependsOn"]
            )
        )

        dependencies = next(
            item
            for item in template["resources"]
            if "cosmosDBId"
            in item.get("properties", {}).get("template", {}).get("outputs", {})
        )
        outputs = dependencies["properties"]["template"]["outputs"]
        for output, flag in (
            ("cosmosDBId", "cosmosDBExists"),
            ("aiSearchID", "aiSearchExists"),
            ("azureStorageId", "azureStorageExists"),
        ):
            with self.subTest(output=output):
                value = outputs[output]["value"]
                self.assertTrue(value.startswith(f"[if(parameters('{flag}'),"))
                self.assertIn("extensionResourceId(", value)
                self.assertIn("resourceId(", value)

    def test_generated_portal_artifacts_match_compiled_sources(self):
        saved = json.loads((SCENARIO / "azuredeploy.json").read_text(encoding="utf-8"))
        self.assertEqual(
            without_generator_metadata(saved),
            without_generator_metadata(self.templates["main"]),
        )
        saved_parameters = json.loads(
            (SCENARIO / "azuredeploy.parameters.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved_parameters, self.parameters["main"])


if __name__ == "__main__":
    unittest.main()
