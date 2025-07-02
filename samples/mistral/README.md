# Mistral AI models on Azure Foundry

This subdirectory contains code samples to get started with Mistral AI models on
the Azure Foundry platform.

## Getting started

The recommended way to set up your environment is to leverage [uv](). Otherwise you
can rely on the auto-generated `requirements.txt` file with the package manager of
your choice (e.g. pip, poetry, etc.)

To install the required dependencies and start a notebook server, run the following
commands in your terminal:

```bash
uv sync # Installs/updates the required dependencies
uv run jupyter notebook # Starts a notebook server
```

From there you can open the Jupyter notebook UI in your web browser following the URL
that the previous command will output.

You can also run the notebooks from Visual Studio Code, please refer to the
[VSCode documentation](https://code.visualstudio.com/docs/datascience/jupyter-notebooks)
for more details.
