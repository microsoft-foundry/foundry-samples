#!/bin/bash

# PRE-REQUISITES
# 1. Set the CONNECTION_STRING environment variable to your Azure OpenAI connection string.
# 2. Set the FILE_PATH environment variable to the path of your agent/fdl file.
# 3. Make sure you have the Azure CLI installed and logged in.

# Example: Deploy a new/existing workflow
# CONNECTION_STRING="eastus.api.azureml.ms;921496dc-987f-410f-bd57-426eb2611356;rapida-eastus;rapida-3548" FILE_PATH="../CustomerSupport/CustomerSupport.fdl" ./deploy.sh

# Example: Deploy a new/existing agent
# CONNECTION_STRING="eastus.api.azureml.ms;921496dc-987f-410f-bd57-426eb2611356;rapida-eastus;rapida-3548" FILE_PATH="../CustomerSupport/agents/HumanEscalationAgent.agent"  ./deploy.sh

# Example: Delete an existing agent
# CONNECTION_STRING="eastus.api.azureml.ms;921496dc-987f-410f-bd57-426eb2611356;rapida-eastus;rapida-3548" FILE_PATH="../CustomerSupport/agents/HumanEscalationAgent.agent" OPERATION="delete" ./deploy.sh


# check if yq is installed. If not, install it.
if ! command -v yq &> /dev/null
then
    echo "yq could not be found. Installing yq..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo add-apt-repository ppa:rmescandon/yq
        sudo apt-get install -y yq
    else
        echo "Unsupported OS. Please install yq manually."
        exit 1
    fi
fi

# check if jq is installed. If not, install it.
if ! command -v jq &> /dev/null
then
    echo "jq could not be found. Installing jq..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get install -y jq
    else
        echo "Unsupported OS. Please install jq manually."
        exit 1
    fi
fi

# Check if CONNECTION_STRING is set
if [ -z "$CONNECTION_STRING" ]; then
  echo "Error: CONNECTION_STRING is not set. Please set it to your Azure OpenAI connection string. Format: <host>;<subscription_id>;<resource_group>;<project_name>"
  exit 1
fi

# Parse the connection string
IFS=';' read -r HOST SUBSCRIPTION_ID RESOURCE_GROUP PROJECT_NAME <<< "$CONNECTION_STRING"
# Check if HOST, SUBSCRIPTION_ID, RESOURCE_GROUP, and PROJECT_NAME are set
if [ -z "$HOST" ] || [ -z "$SUBSCRIPTION_ID" ] || [ -z "$RESOURCE_GROUP" ] || [ -z "$PROJECT_NAME" ]; then
  echo "Error: Invalid CONNECTION_STRING format. Please set it to <host>;<subscription_id>;<resource_group>;<project_name>"
  exit 1
fi

# Check if FDL_FILE_PATH is set
if [ -z "$FILE_PATH" ]; then
  echo "Error: FDL_FILE_PATH is not set. Please set it to the path of your FDL file."
  exit 1
fi

# check if the FDL file exists
if [ ! -f "$FILE_PATH" ]; then
  echo "Error: FDL file not found at $FILE_PATH. Please check the path."
  exit 1
fi

# Determine agent type
if [[ "$FILE_PATH" == *.agent ]]; then
  AGENT_TYPE="agent"
  URL_SUFFIX="assistants"
else
  AGENT_TYPE="workflow"
  URL_SUFFIX="agents"
fi

FILE_YAML="$(cat "$FILE_PATH")"  

# exract the ID from the yaml file if it exists
ID=$(echo "$FILE_YAML" | yq eval '.id' -)
 
# if ID is null, set it to empty string
if [ "$ID" == "null" ]; then
  ID=""
fi

# convert the yaml to json
FILE_JSON="$(echo "$FILE_YAML" | yq eval -o json)"

# check if the conversion was successful
if [ $? -ne 0 ]; then
  echo "Error: Failed to convert yaml to json. Please check the FDL file format."
  exit 1
fi

JSON="$(echo "$FILE_JSON")"

# remove the id field from the json
if [ -n "$ID" ]; then
  JSON="$(echo "$JSON" | jq 'del(.id)')"
fi

# if agent type is agent, remove the agent_type field from the json
if [[ "$AGENT_TYPE" == "agent" ]]; then
  JSON="$(echo "$JSON" | jq 'del(.events)')"
  JSON="$(echo "$JSON" | jq 'del(.inputs)')"
  JSON="$(echo "$JSON" | jq 'del(.outputs)')"
  JSON="$(echo "$JSON" | jq 'del(.system_prompts)')"
fi

# Get the Azure OpenAI auth token
AZURE_OPENAI_AUTH_TOKEN=$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)

# check if the az command is successful
if [ $? -ne 0 ]; then
  echo "Error: Failed to retrieve Azure OpenAI auth token. Please check your Azure CLI installation and login."
  exit 1
fi

# check if token is empty
if [ -z "$AZURE_OPENAI_AUTH_TOKEN" ]; then
  echo "Error: Failed to retrieve Azure OpenAI auth token. Please check your Azure CLI login."
  exit 1
fi

API_VERSION=${API_VERSION:-"2024-12-01-preview"}
OPERATION=${OPERATION:-"upsert"}
PROJECT_URL="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.MachineLearningServices/workspaces/${PROJECT_NAME}"

# check if ID is set and not empty
if [[ "$OPERATION" == "delete" ]]; then
  if [ -n "$ID" ]; then
    echo "Deleting the existing ${AGENT_TYPE} with id=${ID}..."
  else
    echo "Error: No id found in ${FILE_PATH}. Please set the id to delete the existing ${AGENT_TYPE}."
    exit 1
  fi

  # delete the existing agent
  echo "Deleting the existing ${AGENT_TYPE} with id=${ID}..."
  RESPONSE_FILE=$(mktemp)
  HTTP_STATUS=$(curl -v -X DELETE "https://${HOST}/${AGENT_TYPE}s/v1.0${PROJECT_URL}/${URL_SUFFIX}/${ID}?api-version=${API_VERSION}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AZURE_OPENAI_AUTH_TOKEN" \
    -o "${RESPONSE_FILE}" \
    -w "%{http_code}")

  # Check if status code is not 2XX
  if [[ ! "${HTTP_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "Error: Delete ${AGENT_TYPE} failed with status code ${HTTP_STATUS}"
    cat "${RESPONSE_FILE}"
    rm -f "${RESPONSE_FILE}"
    exit 1
  fi

  rm -f "${RESPONSE_FILE}"

  echo "Deleted ${AGENT_TYPE} successfully. Check the deleted ${AGENT_TYPE} in ${FILE_PATH}.json"
elif [ -n "$ID" ]; then
  # update the existing agent
  echo "Updating the existing ${AGENT_TYPE} with id=${ID}..."
  RESPONSE_FILE=$(mktemp)
  HTTP_STATUS=$(curl -v -X POST "https://${HOST}/${AGENT_TYPE}s/v1.0${PROJECT_URL}/${URL_SUFFIX}/${ID}?api-version=${API_VERSION}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AZURE_OPENAI_AUTH_TOKEN" \
    -d "${JSON}" \
    -o "${RESPONSE_FILE}" \
    -w "%{http_code}")

     # Check if status code is not 2XX
  if [[ ! "${HTTP_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "Error: Update ${AGENT_TYPE} failed with status code ${HTTP_STATUS}"
    cat "${RESPONSE_FILE}"
    rm -f "${RESPONSE_FILE}"
    exit 1
  fi

  rm -f "${RESPONSE_FILE}"

  echo "Updated ${AGENT_TYPE} successfully. Check the updated ${AGENT_TYPE} in ${FILE_PATH}.json"
else
  # create a new agent
  echo "Creating a new ${AGENT_TYPE}..."
  RESPONSE_FILE=$(mktemp)
  HTTP_STATUS=$(curl  -v -X POST "https://${HOST}/${AGENT_TYPE}s/v1.0${PROJECT_URL}/${URL_SUFFIX}?api-version=${API_VERSION}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AZURE_OPENAI_AUTH_TOKEN" \
    -d "${JSON}" \
    -o "${RESPONSE_FILE}" \
    -w "%{http_code}")

  # Check if status code is not 2XX
  if [[ ! "${HTTP_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "Error: Create ${AGENT_TYPE} failed with status code ${HTTP_STATUS}"
    cat "${RESPONSE_FILE}"
    rm -f "${RESPONSE_FILE}"
    exit 1
  fi

  # extract the id from the response
  ID=$(cat $RESPONSE_FILE | jq -r '.id')

  # Add the id to the yaml in the file
  if [ -n "$ID" ]; then
    yq eval -i ".id = \"$ID\"" "$FILE_PATH"
  else
    echo "Error: Failed to extract id for the created ${AGENT_TYPE}. Please check the response."
    cat "${RESPONSE_FILE}"
    rm -f "${RESPONSE_FILE}"
    exit 1
  fi

  rm -f "${RESPONSE_FILE}"
  echo "Created new ${AGENT_TYPE} with id=${ID} successfully."
fi

# if agent type is agent, then update the extensions
if [[ "$AGENT_TYPE" == "agent" ]]; then
  # extract events, inputs, outputs, and system_prompts from the yaml file
  EXT_JSON=$(echo "$FILE_JSON" | jq '{events: .events, inputs: .inputs, outputs: .outputs, system_prompts: .system_prompts}')

  # update the existing agent with extensions
  echo "Updating the ${AGENT_TYPE} extensions..."
  RESPONSE_FILE=$(mktemp)
  HTTP_STATUS=$(curl -v -X POST "https://${HOST}/workflows/v1.0${PROJECT_URL}/assistants/${ID}/extensions?api-version=${API_VERSION}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $AZURE_OPENAI_AUTH_TOKEN" \
    -d "${EXT_JSON}" \
    -o "${RESPONSE_FILE}" \
    -w "%{http_code}")

     # Check if status code is not 2XX
  if [[ ! "${HTTP_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "Error: Update ${AGENT_TYPE} extensions failed with status code ${HTTP_STATUS}"
    cat "${RESPONSE_FILE}"
    rm -f "${RESPONSE_FILE}"
    exit 1
  fi

  rm -f "${RESPONSE_FILE}"
  echo "Updated ${AGENT_TYPE} extensions successfully."
fi
 
