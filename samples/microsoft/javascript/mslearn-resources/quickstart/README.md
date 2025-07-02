# JavaScript QuickStart

## Set up your environment

1. [Install Node.js (LTS is recommended) and the Azure CLI](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/install-cli-sdk).

1. Make sure to sign in using the CLI az login (or az login --use-device-code) command to authenticate before running your JavaScript scripts.

1. Download [`env.template`](https://github.com/azure-ai-foundry/foundry-samples/blob/main/samples/microsoft/javascript/mslearn-resources/quickstart/env.template) and rename it to `.env`. Place it in the root of your project directory.
1. Open the `.env` file and fill in the following variables based upon your AI Foundry resource and project names:

   - `MODEL_DEPLOYMENT_NAME`: Your deployed Azure OpenAI model. Defaults to `gpt-4o`.
   - `PROJECT_ENDPOINT`: The endpoint for your AI Foundry project. 

1. Download [`package.json`](https://github.com/azure-ai-foundry/foundry-samples/blob/main/samples/microsoft/javascript/mslearn-resources/quickstart/package.json).

1. Install packages with `npm install`.

## Run a chat completion and agent

Run `npm start` to start the application and trigger the chat completion and agent.
