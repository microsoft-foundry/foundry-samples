"""Offline resource-group ownership tests for the opt-in prompt provisioning scripts."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
SUB = "11111111-2222-3333-4444-555555555555"
FAKE = r'''
import json
import os
from pathlib import Path
import shutil
import sys

p = Path(os.environ['FAKE_STATE'])
s = json.loads(p.read_text())
args = sys.argv[1:]
s['commands'].append(args)
def save(): p.write_text(json.dumps(s))
def value(key):
    if key not in s['env']: sys.exit(1)
    print(s['env'][key])
def group():
    return {'id': f"/subscriptions/{s['subscription']}/resourceGroups/{s['rg']}",
            'tags': {s['tag_kind']: s['tag']}}

if args[:2] == ['az', 'group']:
    op = args[2]
    if op == 'exists': print('true' if s['exists'] else 'false')
    elif op == 'show':
        if not s['exists']: sys.exit(1)
        print(json.dumps(group()))
    elif op == 'update':
        s['tag'] = args[args.index('--set') + 1].split('=', 1)[1]
    else: raise AssertionError(args)
elif args[:2] == ['az', 'rest']:
    assert args[args.index('--headers') + 1] == 'If-None-Match=*'
    if s['exists']: sys.exit(1)
    s['exists'] = True
    s['tag'] = json.loads(args[args.index('--body') + 1])['tags']['ciPromptOwner']
    s['tag_kind'] = 'ciPromptOwner'
elif args[:3] == ['az', 'resource', 'show']:
    assert args[args.index('--ids') + 1] == s['env']['AZURE_AI_PROJECT_ID']
    if s.get('arm_unavailable'): sys.exit(1)
    print(s['endpoint'])
elif args[:4] == ['az', 'cognitiveservices', 'account', 'deployment']:
    assert args[4] == 'show'
    assert args[args.index('--deployment-name') + 1] == 'test-model'
    if s['mode'] == 'model_missing': sys.exit(1)
    print('{}')
elif args[:3] == ['azd', 'env', 'set']:
    s['env'][args[3]] = args[4]
elif args[:3] == ['azd', 'env', 'get-value']:
    value(args[3])
elif args[:4] == ['azd', 'ai', 'agent', 'init']:
    assert os.environ['AZURE_SUBSCRIPTION_ID'] == s['subscription']
    assert os.environ['AZURE_LOCATION'] == 'eastus2'
    assert not s['env']
    target = Path(args[args.index('--src') + 1])
    assert args[args.index('--src') + 1] == 'project'
    target.mkdir()
    shutil.copyfile(args[args.index('-m') + 1], target / 'azure.yaml')
    s['env'] = {'AZURE_ENV_NAME': args[args.index('--environment') + 1],
                'AZURE_SUBSCRIPTION_ID': os.environ['AZURE_SUBSCRIPTION_ID'],
                'AZURE_LOCATION': os.environ['AZURE_LOCATION']}
    s['rg'] = 'rg-' + s['env']['AZURE_ENV_NAME']
    (target / '.azure' / s['env']['AZURE_ENV_NAME']).mkdir(parents=True)
    if s['mode'] == 'init_binding': s['env']['AZURE_AI_PROJECT_ENDPOINT'] = 'https://foreign.invalid'
    if s['mode'] == 'init_manifest_binding':
        manifest = target / 'azure.yaml'
        manifest.write_text(manifest.read_text().replace('    project: .\n',
            '    project: .\n    endpoint: https://foreign.invalid\n'))
elif args[:2] == ['azd', 'provision']:
    s['exists'] = True
    if s['mode'] != 'provision_fail':
        s['env']['AZURE_AI_PROJECT_ID'] = (f"/subscriptions/{s['subscription']}/resourceGroups/{s['rg']}"
             '/providers/Microsoft.CognitiveServices/accounts/test-account/projects/test-project')
        s['env']['FOUNDRY_PROJECT_ENDPOINT'] = s['endpoint']
    if s['mode'] != 'provision_untag':
        s['tag_kind'] = 'azd-env-name'
        s['tag'] = s['env']['AZURE_ENV_NAME']
    if s['mode'] in ('provision_fail', 'provision_partial'):
        save()
        sys.exit(1)
    if s['mode'] == 'legacy_endpoint':
        del s['env']['FOUNDRY_PROJECT_ENDPOINT']
        s['env']['AZURE_AI_PROJECT_ENDPOINT'] = s['endpoint']
    if s['mode'] == 'prefer_canonical': s['env']['AZURE_AI_PROJECT_ENDPOINT'] = 'https://stale.invalid'
    if s['mode'] == 'missing_endpoint': del s['env']['FOUNDRY_PROJECT_ENDPOINT']
    if s['mode'] == 'endpoint_mismatch': s['env']['FOUNDRY_PROJECT_ENDPOINT'] = 'https://other.invalid'
    if s['mode'] == 'foreign_project':
        s['env']['AZURE_AI_PROJECT_ID'] = s['env']['AZURE_AI_PROJECT_ID'].replace(s['rg'], 'foreign-rg')
    if s['mode'] == 'provision_untag': s['tag'] = 'somebody-else'
    if s['mode'] == 'provision_manifest_binding':
        manifest = Path('azure.yaml')
        manifest.write_text(manifest.read_text().replace('    project: .\n',
            '    project: .\n    endpoint: https://foreign.invalid\n'))
elif args[:2] == ['azd', 'down']:
    if s['mode'] != 'down_stuck': s['exists'] = False
else: raise AssertionError(args)
save()
'''


class ProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = os.environ.get('PROMPT_AGENT_TEST_BASH') or (
            'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash'))
        if not cls.bash or subprocess.run([cls.bash, '-c', 'command -v jq && command -v realpath'],
                                          capture_output=True).returncode:
            raise unittest.SkipTest('Bash, jq and realpath required')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='prompt provision ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sample = self.root / 'sample'
        self.sample.mkdir()
        (self.sample / 'azure.yaml').write_text('''name: test
services:
  ai-project:
    host: azure.ai.project
    deployments:
      - name: test-model
        model: {name: test-model, format: OpenAI}
  agent:
    host: azure.ai.agent
    kind: prompt
    project: .
    uses: [ai-project]
    model: test-model
infra:
  provider: microsoft.foundry
''')
        self.artifacts = self.root / 'artifacts'
        self.artifacts.mkdir()
        self.work = self.root / 'work'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        fake = self.root / 'fake.py'
        fake.write_text(FAKE)
        for name in ('az', 'azd'):
            stub = self.bin / name
            stub.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                            shlex.quote(str(fake)) + ' ' + name + ' "$@"\n')
            stub.chmod(0o755)
        self.state_path = self.root / 'state.json'
        self.state = {'commands': [], 'subscription': SUB, 'env': {}, 'exists': False,
                      'rg': '', 'tag': '', 'tag_kind': 'ciPromptOwner',
                      'endpoint': 'https://test.invalid/api/projects/test-project', 'mode': ''}
        self.save()

    def save(self):
        self.state_path.write_text(json.dumps(self.state))

    def run_script(self, name, *args):
        env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
               'FAKE_STATE': str(self.state_path), 'PYTHON': sys.executable}
        env.pop('BASH_ENV', None)
        result = subprocess.run([self.bash, str(SCRIPTS / name), *map(str, args)],
                                env=env, capture_output=True, text=True, timeout=40)
        self.state = json.loads(self.state_path.read_text())
        return result

    def provision(self):
        return self.run_script('provision-prompt-agent.sh', '--sample', self.sample, '--artifacts',
                               self.artifacts, '--work', self.work, '--subscription-id', SUB,
                               '--location', 'eastus2')

    def teardown(self):
        return self.run_script('teardown-prompt-agent.sh', '--artifacts', self.artifacts,
                               '--work', self.work, '--subscription-id', SUB)

    def operations(self, *prefix):
        return [c for c in self.state['commands'] if c[:len(prefix)] == list(prefix)]

    def test_success_and_verified_down(self):
        result = self.provision()
        self.assertEqual(result.returncode, 0, result.stderr)
        ledger = json.loads((self.artifacts / 'provision-ledger.json').read_text())
        self.assertTrue(ledger['tagged'])
        self.assertEqual(ledger['project_endpoint'], self.state['endpoint'])
        self.assertIn(['azd', 'env', 'get-value', 'FOUNDRY_PROJECT_ENDPOINT', '-e', ledger['environment']],
                      self.state['commands'])
        self.assertIn('##vso[task.setvariable variable=PROJECT_ID]', result.stdout)
        self.assertLess(self.state['commands'].index(self.operations('az', 'group', 'exists')[0]),
                        self.state['commands'].index(self.operations('azd', 'ai', 'agent', 'init')[0]))
        result = self.teardown()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.operations('azd', 'down')), 1)
        self.assertFalse(self.state['exists'])
        self.assertEqual(json.loads((self.artifacts / 'teardown-result.json').read_text()), {'status': 'passed'})

    def test_legacy_endpoint_fallback(self):
        self.state['mode'] = 'legacy_endpoint'
        self.save()
        self.assertEqual(self.provision().returncode, 0)
        self.assertEqual(self.teardown().returncode, 0)

    def test_canonical_endpoint_wins_over_legacy(self):
        self.state['mode'] = 'prefer_canonical'
        self.save()
        self.assertEqual(self.provision().returncode, 0)
        self.assertEqual(self.teardown().returncode, 0)

    def test_missing_endpoint_refuses_provision(self):
        self.state['mode'] = 'missing_endpoint'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)

    def test_project_endpoint_must_match_arm(self):
        self.state['mode'] = 'endpoint_mismatch'
        self.save()
        result = self.provision()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARM project endpoint mismatch', result.stderr)

    def test_project_must_belong_to_owned_group(self):
        self.state['mode'] = 'foreign_project'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)

    def test_missing_model_refuses_provision(self):
        self.state['mode'] = 'model_missing'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertNotIn('project_id', json.loads((self.artifacts / 'provision-ledger.json').read_text()))

    def test_provision_cannot_replace_group_tag(self):
        self.state['mode'] = 'provision_untag'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertEqual(len(self.operations('az', 'group', 'show')), 2)
        self.assertNotIn('project_id', json.loads((self.artifacts / 'provision-ledger.json').read_text()))

    def test_provision_cannot_introduce_manifest_binding(self):
        self.state['mode'] = 'provision_manifest_binding'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)

    def test_existing_group_refuses_cloud_creation(self):
        self.state['exists'] = True
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.operations('azd', 'ai', 'agent', 'init'))
        self.assertFalse(self.operations('azd', 'provision'))

    def test_init_binding_refuses_provision(self):
        self.state['mode'] = 'init_binding'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.operations('azd', 'provision'))

    def test_init_manifest_binding_refuses_provision(self):
        self.state['mode'] = 'init_manifest_binding'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.operations('azd', 'provision'))

    def test_partial_provision_cleans_only_tagged_group(self):
        self.state['mode'] = 'provision_fail'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertTrue((self.artifacts / 'provision-ledger.json').exists())
        self.assertEqual(self.teardown().returncode, 0)
        self.assertEqual(len(self.operations('azd', 'down')), 1)
        self.assertFalse(self.state['exists'])
        self.assertEqual(json.loads((self.artifacts / 'teardown-result.json').read_text()), {'status': 'passed'})

    def test_failed_provision_with_partial_outputs_and_replaced_tag_cleans(self):
        self.state['mode'] = 'provision_partial'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertNotIn('project_id', json.loads((self.artifacts / 'provision-ledger.json').read_text()))
        self.assertEqual(self.state['tag_kind'], 'azd-env-name')
        self.assertEqual(self.teardown().returncode, 0)
        self.assertEqual(len(self.operations('azd', 'down')), 1)
        self.assertFalse(self.state['exists'])

    def test_partial_outputs_refuse_foreign_identity_and_endpoint(self):
        self.state['mode'] = 'provision_partial'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        owned_id = self.state['env']['AZURE_AI_PROJECT_ID']
        for change in ({'AZURE_AI_PROJECT_ID': owned_id.replace(self.state['rg'], 'foreign')},
                       {'AZURE_AI_PROJECT_ID': owned_id + '/extra'},
                       {'FOUNDRY_PROJECT_ENDPOINT': 'https://foreign.invalid'},
                       {'AZURE_AI_PROJECT_ENDPOINT': 'https://foreign.invalid'}):
            with self.subTest(change=change):
                original = self.state['env'].copy()
                self.state['env'].update(change)
                self.save()
                self.assertNotEqual(self.teardown().returncode, 0)
                self.assertFalse(self.operations('azd', 'down'))
                self.state['env'] = original

    def test_partial_endpoint_requires_arm_verification(self):
        self.state['mode'] = 'provision_partial'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.state['arm_unavailable'] = True
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))

    def test_failed_before_group_creation_is_safe(self):
        self.state['mode'] = 'init_binding'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.state['exists'])
        self.assertEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))

    def test_sample_existing_binding_refuses_before_group_creation(self):
        manifest = self.sample / 'azure.yaml'
        manifest.write_text(manifest.read_text().replace('    project: .\n',
            '    project: .\n    endpoint: https://foreign.invalid\n'))
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.state['exists'])
        self.assertFalse(self.operations('azd', 'ai', 'agent', 'init'))
        self.assertEqual(self.teardown().returncode, 0)

    def test_sample_custom_infrastructure_refuses_before_group_creation(self):
        manifest = self.sample / 'azure.yaml'
        manifest.write_text(manifest.read_text().replace('provider: microsoft.foundry', 'provider: bicep'))
        self.assertNotEqual(self.provision().returncode, 0)
        self.assertFalse(self.state['exists'])
        self.assertFalse(self.operations('azd', 'ai', 'agent', 'init'))

    def test_unrecorded_canonical_binding_refuses_partial_teardown(self):
        self.state['mode'] = 'provision_fail'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.state['env']['FOUNDRY_PROJECT_ENDPOINT'] = self.state['endpoint']
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))
        self.assertEqual(json.loads((self.artifacts / 'teardown-result.json').read_text()), {'status': 'failed'})

    def test_untagged_group_after_create_failure_refuses_down(self):
        self.state['mode'] = 'init_binding'
        self.save()
        self.assertNotEqual(self.provision().returncode, 0)
        self.state['exists'] = True
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))
        self.assertEqual(json.loads((self.artifacts / 'teardown-result.json').read_text()), {'status': 'failed'})

    def test_foreign_group_and_changed_env_refuse_down(self):
        self.assertEqual(self.provision().returncode, 0)
        self.state['tag'] = 'somebody-else'
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))
        self.state['tag'] = json.loads((self.artifacts / 'provision-ledger.json').read_text())['environment']
        self.state['env']['AZURE_RESOURCE_GROUP'] = 'foreign'
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))

    def test_changed_canonical_endpoint_refuses_down(self):
        self.assertEqual(self.provision().returncode, 0)
        self.state['env']['FOUNDRY_PROJECT_ENDPOINT'] = 'https://foreign.invalid'
        self.save()
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))

    def test_down_without_absence_fails_loud(self):
        self.assertEqual(self.provision().returncode, 0)
        self.state['mode'] = 'down_stuck'
        self.save()
        result = self.teardown()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('deletion not verified', result.stderr)
        self.assertEqual(json.loads((self.artifacts / 'teardown-result.json').read_text()), {'status': 'failed'})

    def test_missing_ledger_has_no_teardown_status(self):
        self.assertEqual(self.teardown().returncode, 0)
        self.assertFalse((self.artifacts / 'teardown-result.json').exists())

    def test_changed_manifest_refuses_down(self):
        self.assertEqual(self.provision().returncode, 0)
        with (self.work / 'project' / 'azure.yaml').open('a') as manifest:
            manifest.write('\n# altered\n')
        self.assertNotEqual(self.teardown().returncode, 0)
        self.assertFalse(self.operations('azd', 'down'))


if __name__ == '__main__':
    unittest.main()
