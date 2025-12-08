# Custom Code Interpreter with Session Pool MCP server

This provides example Bicep code for setting up a Container Apps dynamic session pool
with a custom code interpreter image, as well as Python client code demonstrating
how to use it with a Foundry Hosted Agent.

You will need the following installed to run the sample code:

- The `az` CLI
- Python3
- A Python3 package manager like `uv` or `pip` + `venv`
    - If you are using `pip`, make sure `ensurepip` is installed. On Debian/Ubuntu
      systems, this would mean running `apt install python3.12-venv`.

## Running code sample

### Enable MCP server for dynamic sessions

This is required to enable the preview feature.

```console
az feature register --namespace Microsoft.App --name SessionPoolsSupportMCP
az provider register -n Microsoft.App
```

### Create a dynamic session pool with a code interpreter image

Using the `az` CLI, deploy with the provided Bicep template file:

```console
az deployment group create \
    --name custom-code-interpreter \
    --subscription <your_subscription> \
    --resource-group <your_resource_group> \
    --template-file ./infra.bicep
```

> [!NOTE] This can take a while! Allocating the dynamic session pool
> can take up to 1 hour, depending on the number of standby instances
> requested.

### Use the custom code interpreter in an agent

Copy the [`.env.sample`](./.env.sample) file to `.env` and fill in the values with
the output of the above deployment, which you can find in the Web Portal under the
resource group.

Finally, install Python dependencies and run the script:

```console
# Using uv

uv sync
uv run ./main.py

# Using pip

python3 -m venv .venv
./.venv/bin/pip3 install -r requirements.txt
./.venv/bin/python3 ./main.py
```

## Limitations

File input/output and use of file stores are not directly supported in APIs, so you must use URLs (such as data URLs for small files and Azure Blob Service SAS URLs for large ones) to get data in and out.
