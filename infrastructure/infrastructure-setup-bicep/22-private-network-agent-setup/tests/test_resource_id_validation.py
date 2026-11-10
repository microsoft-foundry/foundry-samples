"""Exercise the compiled preflight expressions without deploying to Azure.

The small interpreter implements only the ARM expression functions emitted by
this module. It is not an ARM emulator; an actual deployment is still needed to
verify Azure's scheduling and error presentation.
"""

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


SCENARIO = Path(__file__).resolve().parents[1]
SUBSCRIPTION = "12345678-1234-1234-abcd-1234567890ab"
KINDS = {
    "storage": ("azureStorageAccountResourceId", "Microsoft.Storage/storageAccounts", "validatedStorageResourceId"),
    "search": ("aiSearchResourceId", "Microsoft.Search/searchServices", "validatedSearchResourceId"),
    "cosmos": ("azureCosmosDBAccountResourceId", "Microsoft.DocumentDB/databaseAccounts", "validatedCosmosResourceId"),
    "vnet": ("existingVnetResourceId", "Microsoft.Network/virtualNetworks", "validatedVnetResourceId"),
    "account": ("existingAiFoundryAccountResourceId", "Microsoft.CognitiveServices/accounts", "validatedAccountResourceId"),
}
STATUSES = {
    "storage": "storageStatus",
    "search": "searchStatus",
    "cosmos": "cosmosStatus",
    "vnet": "vnetStatus",
    "account": "accountStatus",
}
TOKEN = re.compile(r"\s*(?:('(?:[^']|'')*')|([A-Za-z_][A-Za-z_0-9]*)|(\d+)|(.))", re.DOTALL)


def resource_id(resource_type, name="example"):
    return f"/subscriptions/{SUBSCRIPTION}/resourceGroups/example-rg/providers/{resource_type}/{name}"


@lru_cache(maxsize=None)
def parse(expression):
    """Parse function calls, member access and indexing in a generated ARM expression."""
    assert expression.startswith("[") and expression.endswith("]")
    text = expression[1:-1]
    tokens = []
    position = 0
    while position < len(text):
        match = TOKEN.match(text, position)
        if not match:
            raise ValueError(f"Invalid ARM expression at {text[position:]!r}")
        position = match.end()
        literal, name, number, punctuation = match.groups()
        tokens.append(("literal", literal[1:-1].replace("''", "'")) if literal else
                      ("name", name) if name else
                      ("literal", int(number)) if number else
                      (punctuation, punctuation))
    cursor = 0

    def consume(kind):
        nonlocal cursor
        if cursor >= len(tokens) or tokens[cursor][0] != kind:
            raise ValueError(f"Expected {kind} in {expression!r}, at {cursor}")
        value = tokens[cursor][1]
        cursor += 1
        return value

    def node():
        nonlocal cursor
        if tokens[cursor][0] == "literal":
            result = ("literal", consume("literal"))
        else:
            name = consume("name")
            consume("(")
            arguments = []
            if tokens[cursor][0] != ")":
                while True:
                    arguments.append(node())
                    if tokens[cursor][0] != ",":
                        break
                    consume(",")
            consume(")")
            result = ("call", name.lower(), arguments)
        while cursor < len(tokens) and tokens[cursor][0] in ("[", "."):
            if tokens[cursor][0] == "[":
                consume("[")
                index = node()
                consume("]")
            else:
                consume(".")
                index = ("literal", consume("name"))
            result = ("get", result, index)
        return result

    result = node()
    if cursor != len(tokens):
        raise ValueError(f"Unexpected tokens in {expression!r}: {tokens[cursor:]}")
    return result


class ArmSubset:
    def __init__(self, template, parameters, guard_ids=None):
        self.template = template
        self.parameters = parameters
        self.guard_ids = guard_ids
        self.variables = {}
        self.indices = {}
        self.lambda_vars = {}

    def value(self, value):
        if isinstance(value, str) and value.startswith("["):
            return self.evaluate(parse(value))
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            if set(value) == {"copy"}:
                copy = value["copy"][0]
                return {copy["name"]: self.copy(copy)}
            return {key: self.value(item) for key, item in value.items()}
        return value

    def copy(self, definition):
        name = definition.get("name", "")
        previous = self.indices.get(name)
        result = []
        for index in range(self.value(definition["count"])):
            self.indices[name] = index
            result.append(self.value(definition["input"]))
        if previous is None:
            self.indices.pop(name, None)
        else:
            self.indices[name] = previous
        return result

    def variable(self, name):
        if name not in self.variables:
            variables = self.template["variables"]
            if name in variables:
                self.variables[name] = self.value(variables[name])
            else:
                copy = next(item for item in variables["copy"] if item["name"] == name)
                self.variables[name] = self.copy(copy)
        return self.variables[name]

    def evaluate(self, node):
        kind = node[0]
        if kind == "literal":
            return node[1]
        if kind == "get":
            return self.evaluate(node[1])[self.evaluate(node[2])]
        _, name, args = node
        if name == "if":
            return self.evaluate(args[1] if self.evaluate(args[0]) else args[2])
        if name == "reduce":
            values, result = self.evaluate(args[0]), self.evaluate(args[1])
            assert args[2][0:2] == ("call", "lambda")
            accumulator, item, body = args[2][2]
            for value in values:
                self.lambda_vars[self.evaluate(accumulator)] = result
                self.lambda_vars[self.evaluate(item)] = value
                result = self.evaluate(body)
            return result
        values = [self.evaluate(arg) for arg in args]
        if name == "parameters":
            return self.parameters[values[0]]
        if name == "variables":
            return self.variable(values[0])
        if name == "copyindex":
            return self.indices[values[0] if values else ""]
        if name == "lambdavariables":
            return self.lambda_vars[values[0]]
        if name == "reference":
            if values != ["idGuard"] or self.guard_ids is None:
                raise AssertionError(f"Unexpected resource reference: {values}")
            return {"outputs": {"resourceIds": {"value": self.guard_ids}}}
        if name == "subscription":
            return {"subscriptionId": SUBSCRIPTION}
        if name == "resourcegroup":
            return {"name": "deployment-rg"}
        functions = {
            "true": lambda: True,
            "false": lambda: False,
            "length": len,
            "empty": lambda value: not value,
            "equals": lambda a, b: a == b,
            "and": lambda a, b: a and b,
            "or": lambda a, b: a or b,
            "not": lambda value: not value,
            "tolower": str.lower,
            "trim": str.strip,
            "split": lambda value, separator: value.split(separator),
            "contains": lambda value, item: item in value,
            "substring": lambda value, start, length: value[start:start + length],
            "range": lambda start, count: list(range(start, start + count)),
            "createarray": lambda *items: list(items),
            "createobject": lambda *items: dict(zip(items[::2], items[1::2])),
            "tryget": lambda obj, key: obj.get(key),
            "coalesce": lambda *items: next((item for item in items if item is not None), None),
        }
        if name not in functions:
            raise AssertionError(f"Unsupported ARM function {name}")
        return functions[name](*values)


def resources(template):
    values = template["resources"]
    return list(values.values()) if isinstance(values, dict) else values


class ResourceIdValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cli = os.environ.get("BICEP_CLI") or shutil.which("bicep")
        if not cli:
            candidate = Path.home() / ".azure" / "bin" / ("bicep.exe" if os.name == "nt" else "bicep")
            if candidate.is_file():
                cli = str(candidate)
        if not cli:
            raise RuntimeError("Install Bicep CLI or set BICEP_CLI")
        result = subprocess.run(
            [cli, "build", str(SCENARIO / "modules-network-secured" / "validate-existing-resources.bicep"), "--stdout"],
            capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
        )
        if result.returncode:
            raise AssertionError(f"Bicep compilation failed:\n{result.stderr}")
        cls.template = json.loads(result.stdout)
        modules = resources(cls.template)
        if len(modules) != 1:
            raise AssertionError("Preflight should contain only the parameter guard deployment")
        cls.guard = modules[0]
        cls.guard_template = cls.guard["properties"]["template"]

    def evaluate_ids(self, **ids):
        parameters = {entry[0]: "" for entry in KINDS.values()}
        parameters.update({KINDS[kind][0]: value for kind, value in ids.items()})
        parameters.update({"existingDnsZones": {}, "dnsZoneNames": [], "dnsZonesSubscriptionId": SUBSCRIPTION})
        arm = ArmSubset(self.template, parameters)
        guard_parameters = self.guard["properties"]["parameters"]
        statuses = {}
        for kind, parameter in STATUSES.items():
            resolved = arm.value(guard_parameters[parameter])
            statuses[kind] = resolved["value"]
        return arm, statuses

    def guard_output(self, arm, statuses):
        guard_parameters = self.guard["properties"]["parameters"]
        values = {STATUSES[kind]: status for kind, status in statuses.items()}
        for name, value in values.items():
            if value not in self.guard_template["parameters"][name]["allowedValues"]:
                raise ValueError(f"{name}: {value}")
        values["resourceIds"] = arm.value(guard_parameters["resourceIds"])["value"]
        guard_arm = ArmSubset(self.guard_template, values)
        return guard_arm.value(self.guard_template["outputs"]["resourceIds"]["value"])

    def test_optional_ids_and_guard_output_contract(self):
        arm, statuses = self.evaluate_ids()
        self.assertEqual(set(statuses.values()), {"valid"})
        for kind, status in statuses.items():
            with self.subTest(kind=kind):
                allowed = self.guard_template["parameters"][STATUSES[kind]]["allowedValues"]
                self.assertEqual(allowed, ["valid"])
                self.assertIn(status, allowed)
        output_arm = ArmSubset(self.template, arm.parameters, guard_ids=self.guard_output(arm, statuses))
        for _, _, output in KINDS.values():
            self.assertEqual(output_arm.value(self.template["outputs"][output]["value"]), "")
        for output in ("azureStorageExists", "aiSearchExists", "cosmosDBExists"):
            self.assertFalse(output_arm.value(self.template["outputs"][output]["value"]))

    def test_correct_types_accept_case_insensitive_arm_paths(self):
        ids = {kind: resource_id(entry[1]) for kind, entry in KINDS.items()}
        ids["vnet"] = ids["vnet"].upper()
        arm, statuses = self.evaluate_ids(**ids)
        self.assertEqual(set(statuses.values()), {"valid"})
        output_arm = ArmSubset(self.template, {}, guard_ids=self.guard_output(arm, statuses))
        for kind, (_, _, output) in KINDS.items():
            with self.subTest(kind=kind):
                self.assertEqual(output_arm.value(self.template["outputs"][output]["value"]), ids[kind])

    def test_wrong_provider_and_type_rejected_for_each_kind(self):
        for kind, (_, expected, _) in KINDS.items():
            provider = expected.split("/")[0]
            _, statuses = self.evaluate_ids(**{kind: resource_id(f"{provider}/wrongType")})
            self.assertNotIn(statuses[kind], self.guard_template["parameters"][STATUSES[kind]]["allowedValues"])
            self.assertIn(expected, statuses[kind])
            for other, (_, wrong, _) in KINDS.items():
                if kind == other:
                    continue
                with self.subTest(kind=kind, wrong=other):
                    arm, statuses = self.evaluate_ids(**{kind: resource_id(wrong)})
                    message = statuses[kind]
                    self.assertNotIn(message, self.guard_template["parameters"][STATUSES[kind]]["allowedValues"])
                    self.assertIn(expected, message)
                    with self.assertRaisesRegex(ValueError, "Invalid"):
                        self.guard_output(arm, statuses)
                    self.assertTrue(all(value == "valid" for key, value in statuses.items() if key != kind))

    def test_malformed_paths_rejected_for_every_kind(self):
        for kind, (_, resource_type, _) in KINDS.items():
            valid = resource_id(resource_type)
            bad_paths = {
                "short": "/subscriptions",
                "missing-leading-slash": valid[1:],
                "trailing-slash": valid + "/",
                "child-resource": valid + "/children/example",
                "empty-group": valid.replace("/example-rg/", "//"),
                "empty-name": valid.rsplit("/", 1)[0] + "/",
                "bad-guid": valid.replace(SUBSCRIPTION, "not-a-guid"),
                "bad-guid-hex": valid.replace(SUBSCRIPTION, "z" + SUBSCRIPTION[1:]),
                "bad-guid-separator": valid.replace(SUBSCRIPTION, SUBSCRIPTION[:8] + "a" + SUBSCRIPTION[9:]),
                "wrong-prefix": valid.replace("/subscriptions/", "/subscription/"),
                "wrong-resource-group": valid.replace("/resourceGroups/", "/resourceGroup/"),
                "wrong-providers": valid.replace("/providers/", "/provider/"),
                "query": valid + "?x=y",
                "fragment": valid + "#fragment",
                "encoded-slash": valid + "%2fchild",
                "space": valid + " name",
                "backslash": valid + "\\child",
            }
            for case, invalid in bad_paths.items():
                with self.subTest(kind=kind, case=case):
                    _, statuses = self.evaluate_ids(**{kind: invalid})
                    self.assertNotIn(statuses[kind], self.guard_template["parameters"][STATUSES[kind]]["allowedValues"])
                    self.assertIn(resource_type, statuses[kind])

    def test_no_resource_existence_probe_is_emitted(self):
        self.assertEqual(self.guard["type"], "Microsoft.Resources/deployments")
        self.assertEqual(resources(self.guard_template), [])
        for kind, output in (("storage", "azureStorageExists"), ("search", "aiSearchExists"), ("cosmos", "cosmosDBExists")):
            ids = {name: "" for name in KINDS}
            ids[kind] = resource_id(KINDS[kind][1], "not-checked-for-existence")
            arm, statuses = self.evaluate_ids(**ids)
            self.assertEqual(statuses[kind], "valid")
            arm = ArmSubset(self.template, {}, guard_ids=self.guard_output(arm, statuses))
            self.assertTrue(arm.value(self.template["outputs"][output]["value"]))

    def test_partial_dns_map_treats_missing_zone_as_not_supplied(self):
        arm, _ = self.evaluate_ids()
        arm.parameters["existingDnsZones"] = {"zone-a": "dns-rg"}
        arm.parameters["dnsZoneNames"] = ["zone-a", "zone-b"]
        dns = self.template["outputs"]["dnsZoneExists"]["copy"]
        self.assertEqual(arm.copy(dns), [{"name": "zone-a", "exists": True}, {"name": "zone-b", "exists": False}])


if __name__ == "__main__":
    unittest.main()
