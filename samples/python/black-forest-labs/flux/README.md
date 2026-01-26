# Image Generation with Black Forest Labs' FLUX models

This sample demonstrates how to use **FLUX** image-generation models from _Black Forest Labs_ in Azure AI Foundry. The provided Jupyter notebook showcases how to create high-quality images from textual prompts.

This demo utilises the `requests` library for direct API interaction and the `azure-identity` library for secure Azure Entra ID authentication.

## 📑 Table of Contents:
- [Part 1: Configuring Solution Environment](#part-1-configuring-solution-environment)
- [Part 2: Generating Images with FLUX Models](#part-2-generating-images-with-flux-models)
- [Part 3: Model Comparison - V1.1 Pro vs. V2 Pro](#part-3-model-comparison---v11-pro-vs-v2-pro)

## Part 1: Configuring Solution Environment
To use the notebook, set up your Azure AI Foundry environment and install the necessary Python packages.

### 1.1 Azure AI Foundry Setup
Ensure you have an Azure AI Foundry project with the FLUX-1.1-pro or FLUX-2-pro models deployed.

### 1.2 Authentication
This demo uses **Azure Entra ID** authentication via `DefaultAzureCredential` from `azure.identity`. This credential type automatically handles various authentication methods.

To make it work, ensure your environment is set up for Azure authentication, e.g., by logging in via `az login` (Azure CLI) or setting relevant environment variables for service principals.

> [!NOTE]
> More detailed information about supported credential types can be found [here](https://learn.microsoft.com/en-us/dotnet/api/azure.identity.defaultazurecredential).

### 1.3 Environment Variables
Set the following environment variables to point to your Azure AI Foundry endpoint and deployments:

| Environment Variable       |  Description                                                                               |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| AZURE_FOUNDRY_ENDPOINT_BFL | Your Azure AI Foundry endpoint URL (e.g., https://<YOUR_RESOURCE>.services.ai.azure.com/). |
| FLUX_v1_DEPLOYMENT         | The name of your FLUX 1.1 Pro deployment.                                                  |
| FLUX_v2_DEPLOYMENT         | The name of your FLUX 2 Pro deployment.                                                    |

### 1.4 Install Required Python packages

``` PowerShell
pip install requests pillow azure-identity
```

## Part 2: Generating Images with FLUX Models
The `AIFoundry_ImageGeneration_FLUX.ipynb` notebook groups the image generation logic into the following core blocks:

### 2.1 Model Configuration:
Maps model keys to specific Azure endpoints and API paths (e.g., `providers/blackforestlabs/v1/flux-pro-1.1`).

``` Python
FLUX_MODELS = {
    "flux-1.1-pro": {
        "endpoint": AZURE_FOUNDRY_ENDPOINT_BFL,
        "path": "providers/blackforestlabs/v1/flux-pro-1.1",
        "api_version": "preview",
        "model_name": FLUX_v1_DEPLOYMENT
    },
    "flux-2-pro": {
        "endpoint": AZURE_FOUNDRY_ENDPOINT_BFL,
        "path": "providers/blackforestlabs/v1/flux-2-pro",
        "api_version": "preview",
        "model_name": FLUX_v2_DEPLOYMENT
    }
}
```

> [!WARNING]
> Please, ensure that the name of your model deployment is passed in lower case.

### 2.2 Secure Authentication:
Obtains an Entra ID access token for the `cognitiveservices` scope.

``` Python
    credential = DefaultAzureCredential()
    token_response = credential.get_token("https://cognitiveservices.azure.com/.default")
```

### 2.3 API Request:
Sends a JSON POST request to the model's endpoint, incl. the `prompt` describing the desired image and parameters such as `width`, `height` and `output_format`.

``` Python
    url = f"{config['endpoint']}{config['path']}?api-version={config['api_version']}"
    body = {
        "prompt": prompt,
        "n": 1,
        "width": width,
        "height": height,
        "output_format": output_format,
        "model": config["model_name"]
    }
```

### 2.4 Response Processing:
Decodes the b64_json image data from the response and displays it using the PIL library.

``` Python
    data = response_data['data']
    b64_img = data[0]['b64_json']
    image = Image.open(BytesIO(base64.b64decode(b64_img)))
    display(image)
```

## Part 3: Model Comparison - V1.1 Pro vs. V2 Pro

### 3.1 Features Comparison
While both models are available via Azure AI Foundry, they differ in resolution capabilities and API compatibility:

|                       | FLUX 1.1 Pro                              | FLUX 2 Pro                              |
| --------------------- | ----------------------------------------- | --------------------------------------- |
| BFL API Path          | providers/blackforestlabs/v1/flux-pro-1.1 | providers/blackforestlabs/v1/flux-2-pro |
| Max Resolution        | Up to 1.6 MP                              | Up to 4 MP                              |
| OpenAI-Compatible API | Supported                                 | Not supported                           |
| BFL Native API        | Supported                                 | Supported                               |

### 3.2 Image Generation by FLUX-1.1-Pro

``` JSON
Portrait of a red panda in renaissance clothing in Rembrandt style, detailed, intricate, digital art
```

![IMAGE_REMBRANDT_FLUX1.1](images/Style_Rembrandt.png)

### 3.3 Image Generation by FLUX-2-Pro

``` JSON
Portrait of a red panda in renaissance clothing in Vermeer style, detailed, intricate, digital art
```

![IMAGE_VERMEER_FLUX2](images/Style_Vermeer.png)
