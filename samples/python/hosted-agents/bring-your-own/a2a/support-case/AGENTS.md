# Support Case Agent

Keep this a small, independent native A2A sample using Copilot SDK tools and
FoundryStateStore. No Toolbox or real ticketing integration is needed.
Application case IDs and A2A Task IDs are different; explain both.
Start a fresh SDK session per request; persistent facts must come from the store.
Bind the trusted incoming Foundry call ID to item operations across SDK callbacks.
Keep user_isolation=True and verify the existing store descriptor; never accept
a user-supplied identity or bypass missing context.
Use ETags for read-modify-write and the read version for summary saves.
Do not silently retry conflicting writes or invent a saved state on tool failure.
Preserve history when findings invalidate a summary. Keep actual operation
receipts separate from model prose. No shell/file tools, destructive store tools,
sample tests folder, test client or dedicated test workflow.
Use only synthetic cases. Persistence does not mean interrupted execution resumes.
Do not claim cloud cross-user isolation or forced-restart recovery without evidence.
