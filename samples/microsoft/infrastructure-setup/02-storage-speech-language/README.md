# Bring Your Own Azure Storage for Speech and Language capabailities

Conceptually speaking, this is a connection to another Azure resource, however, Foundry connections are control plane resources that are not tracked by Azure. That means that Foundry connections follow the `'Microsoft/CognitiveServices/accounts/connections'` API, while this (conceptual) connection to a Storage account uses the `userOwnedStorage` field in the Foundry resource JSON under `properties`.

Before running this template, please consider the limitations outlined by [this public documentation](LINK).