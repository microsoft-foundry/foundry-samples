# Microsoft Foundry Documentation Samples

This repository acts as the top-level directory for official Microsoft Foundry documentation sample code and examples. It includes notebooks and sample code that contain end-to-end examples as well as smaller code snippets for common developer tasks.

This repository is entirely open source, guidance on how to contribute and links to additional repositories are provided below.

Use the samples in this repository to try out Microsoft Foundry scenarios on your local machine!

## Validation

Pull requests run the required `trusted` check. Sample authors can run the same
per-sample Build-readiness validator locally and can opt a sample into
sample-owned Live-service validation through `sample.yaml`. See the
[per-sample validation contract](.github/scripts/validate-sample.README.md) for
commands and language behavior.

The [daily public validation cadence](.github/validation-pilot.README.md)
discovers metadata-bearing samples and publishes a run summary plus diagnostic
artifacts in GitHub Actions, plus a durable
[validation dashboard](https://microsoft-foundry.github.io/foundry-samples/)
showing every sample's latest status.

## Contributing

Found a bug or have a suggestion? [Open an issue](https://github.com/microsoft-foundry/foundry-samples/issues/new) — we welcome feedback from everyone!

Microsoft contributors with permission to create a branch in this repository can contribute a sample or fix by opening a pull request directly against `main`. Pull requests must pass the required `trusted` check and are merged by a maintainer. See the [contributing guidelines](CONTRIBUTING.md) for setup, validation, and review details.
