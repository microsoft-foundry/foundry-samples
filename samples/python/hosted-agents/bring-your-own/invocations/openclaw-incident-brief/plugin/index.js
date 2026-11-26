import { Type } from "typebox";
import { FoundryClient } from "./foundry-client.js";

const render = (details) => ({
  content: [{ type: "text", text: JSON.stringify(details) }],
  details,
});

export default {
  id: "foundry-incident-brief",
  name: "Foundry incident brief",
  description: "Delegate incident briefings to a Foundry Hosted Agent.",
  register(api) {
    api.registerTool(
      {
        name: "foundry_incident_brief_start",
        label: "Start incident brief",
        description:
          "Submit supplied incident updates for a prioritized brief. Use a stable requestId " +
          "for the incident and update revision; reuse it with identical updates after a retry. " +
          "Save the returned invocation_id for a later status check.",
        parameters: Type.Object({
          requestId: Type.String({
            description: "Stable incident-and-revision ID, using letters, digits, '.', '_', ':' or '-'.",
            minLength: 1,
            maxLength: 128,
          }),
          updates: Type.String({
            description: "The incident updates to summarize; include timestamps and reported impact.",
            minLength: 1,
            maxLength: 16000,
          }),
        }),
        async execute(_id, { requestId, updates }, signal) {
          return render(await new FoundryClient(api.pluginConfig).start(requestId, updates, signal));
        },
      },
      { name: "foundry_incident_brief_start", optional: true },
    );
    api.registerTool(
      {
        name: "foundry_incident_brief_status",
        label: "Get incident brief",
        description:
          "Get the status or completed incident brief for an invocation_id returned by " +
          "foundry_incident_brief_start. If pending, check again later rather than claiming completion.",
        parameters: Type.Object({
          invocationId: Type.String({ description: "The returned Foundry invocation_id.", minLength: 1 }),
        }),
        async execute(_id, { invocationId }, signal) {
          return render(await new FoundryClient(api.pluginConfig).status(invocationId, signal));
        },
      },
      { name: "foundry_incident_brief_status", optional: true },
    );
  },
};
