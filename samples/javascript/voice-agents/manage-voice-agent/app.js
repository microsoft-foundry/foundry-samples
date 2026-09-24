// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * This sample walks through the voice agent management lifecycle: create, read, update,
 * list, version history, enable/disable, and delete. See generate-voice-agent for
 * generating a voice agent definition from a natural-language goal instead of authoring
 * one directly, and configure-voice-agent for a closer look at a single version's fields.
 *
 * @summary Create, read, update, list, version, enable/disable, and delete a voice agent.
 */

import "dotenv/config";
import { AIProjectClient } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";

const projectEndpoint = getRequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
const modelName = getRequiredEnvironmentVariable("FOUNDRY_VOICE_AGENT_MODEL");
const agentName = process.env.FOUNDRY_VOICE_AGENT_NAME?.trim() || `voice-manage-${Date.now()}`;
const options = {
  requestOptions: { headers: { "foundry-features": "VoiceAgents=V1Preview" } },
  onResponse: (rawResponse) =>
    console.log(`  HTTP ${rawResponse.status} ${rawResponse.request.method} ${rawResponse.request.url}`),
};

async function main() {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

  console.log("Creating a voice agent...");
  let agent = await project.agents.create(
    agentName,
    {
      kind: "voice",
      model_type: "self_deployed",
      model: modelName,
      instructions: "Help callers find public transport information. Keep answers short.",
      output_modalities: ["audio"],
      store: false,
    },
    options,
  );
  const firstVersion = agent.versions.latest.version;
  console.log(`Created "${agent.name}", state: ${agent.state}, version: ${firstVersion}`);

  try {
    console.log("\nReading the agent back...");
    agent = await project.agents.get(agent.name, options);
    if ("instructions" in agent.versions.latest.definition) {
      console.log("Instructions:", agent.versions.latest.definition.instructions);
    }

    console.log("\nUpdating the agent's definition...");
    agent = await project.agents.update(
      agent.name,
      {
        kind: "voice",
        model_type: "self_deployed",
        model: modelName,
        instructions: "Help callers find public transport information. Always mention delays.",
        output_modalities: ["audio"],
        store: false,
      },
      options,
    );
    if ("instructions" in agent.versions.latest.definition) {
      console.log("Updated instructions:", agent.versions.latest.definition.instructions);
    }

    console.log("\nCreating a second version with a greeting...");
    const secondVersion = await project.agents.createVersion(
      agent.name,
      {
        kind: "voice",
        model_type: "self_deployed",
        model: modelName,
        instructions: "Help callers find public transport information. Always mention delays.",
        greeting: { type: "template", text: "Hi there! Where are you headed today?" },
        output_modalities: ["audio"],
        store: false,
      },
      options,
    );
    console.log(`Created version: ${secondVersion.version}`);

    console.log("\nListing every version of this agent...");
    for await (const version of project.agents.listVersions(agent.name, options)) {
      console.log(`  - version ${version.version}`);
    }

    console.log(`\nFetching version ${secondVersion.version} directly...`);
    const fetchedVersion = await project.agents.getVersion(agent.name, secondVersion.version, options);
    if ("greeting" in fetchedVersion.definition) {
      console.log("Greeting on that version:", fetchedVersion.definition.greeting);
    }

    console.log("\nListing voice agents in this project...");
    let voiceAgentCount = 0;
    let foundOurs = false;
    for await (const listed of project.agents.list({ ...options, kind: "voice" })) {
      voiceAgentCount++;
      foundOurs ||= listed.name === agent.name;
    }
    console.log(`Found ${voiceAgentCount} voice agent(s); ours is ${foundOurs ? "" : "not "}among them.`);

    console.log("\nDisabling the agent...");
    await project.agents.disable(agent.name, options);
    console.log(`State: ${(await project.agents.get(agent.name, options)).state}`);

    console.log("\nRe-enabling the agent...");
    await project.agents.enable(agent.name, options);
    console.log(`State: ${(await project.agents.get(agent.name, options)).state}`);

    console.log(`\nDeleting version ${firstVersion} (keeping the latest version)...`);
    const deletedVersion = await project.agents.deleteVersion(agent.name, firstVersion, options);
    console.log(`Deleted: ${deletedVersion.deleted}`);
  } finally {
    console.log("\nDeleting the agent...");
    const deletedAgent = await project.agents.delete(agent.name, options);
    console.log(`Deleted: ${deletedAgent.deleted}`);
  }
}

function getRequiredEnvironmentVariable(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Set ${name} before running this sample.`);
  }
  return value;
}

main().catch((err) => {
  console.error("Sample failed:", err);
  process.exitCode = 1;
});
