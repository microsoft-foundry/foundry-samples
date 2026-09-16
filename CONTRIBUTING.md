# Contributing to Microsoft Foundry Samples

This repository contains official Microsoft Foundry documentation samples. Changes are submitted as pull requests directly to this repository.

## Reporting Issues

If you find a bug, have a question, or want to suggest an improvement to an existing sample, please [open an issue](https://github.com/microsoft-foundry/foundry-samples/issues/new) on this repository. We welcome feedback from everyone!

Before starting a substantial change, check for an existing issue. Open one when discussion or design agreement would help avoid duplicate work.

## Contributing Changes

Sample contributions are currently limited to Microsoft Foundry teams with permission to create a branch in this repository. Fork pull requests cannot satisfy the intentionally failing `trusted` gate, so sample changes must use a same-repository branch.

Contributors should always submit publishable changes through a public same-repository pull request. Do not use a private staging repository or internal publication workflow as a contributor path. If you cannot create a branch in this repository, ask a repository maintainer for guidance.

1. **Create a branch in this repository.** Use a same-repository branch for all sample changes.
2. **Make a focused change.** Keep each pull request scoped to one sample, fix, or related set of updates. Follow the conventions in the surrounding sample.
3. **Respect file ownership.** Review [CODEOWNERS](.github/CODEOWNERS) before editing. The listed owners receive review requests when their files change; CODEOWNERS routing does not itself require an approving review.
4. **Validate locally.** Run the setup, build, test, or sample-specific validation documented by the affected sample. For metadata-bearing samples, start with the [quick guide to creating and validating samples](CREATE_SAMPLE.md); see the [per-sample validation contract](.github/scripts/validate-sample.README.md) for Build-readiness behavior, Live-service opt-in, substitutions, and available validation environment variables. Never commit credentials, local environment files, or generated secrets.
5. **Open a pull request against `main`.** In the pull request description, explain what changed, why it changed, and the local validation you ran. Link the relevant issue when one exists.

### Pull request checks

Pull requests run repository validation automatically:

- The required `trusted` check must pass.
- Review and address the other checks reported on the pull request.
- Contributor pull requests are not merged automatically; after required checks pass, a maintainer considers review feedback and triggers the merge.

The required check reports on the pull request. The separate
[daily validation cadence](.github/validation-pilot.README.md) publishes its
fleet report and diagnostic artifacts in GitHub Actions.

## Contributor License Agreement

This project requires a Contributor License Agreement (CLA). When you submit a pull request, a CLA bot will check whether you need to sign one and guide you through the process. You only need to do this once across all Microsoft repos. For details, visit <https://cla.opensource.microsoft.com>.

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information, see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com).
