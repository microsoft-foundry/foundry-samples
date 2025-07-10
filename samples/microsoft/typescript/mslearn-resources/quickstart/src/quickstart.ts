import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { DefaultAzureCredential } from '@azure/identity';
import { ToolUtility, DoneEvent, ErrorEvent, ThreadMessage } from '@azure/ai-agents';
import { AIProjectClient } from '@azure/ai-projects';
import { config } from 'dotenv';
config();

// Run Azure AI Foundry chat completion using the Azure OpenAI model
await chatCompletion().catch(console.error);
// Run Azure AI Foundry agents (poem agent and file agent)
await runAgents().catch(console.error);

async function chatCompletion() {
    // <chat_completion>
    // Get the Azure AI endpoint and deployment name from environment variables
    const endpoint = process.env.PROJECT_ENDPOINT as string;
    const deployment = process.env.MODEL_DEPLOYMENT_NAME || 'gpt-4o';

    // Create an Azure OpenAI Client
    const project = new AIProjectClient(endpoint, new DefaultAzureCredential());
    const client = await project.inference.azureOpenAI({
        // The API version should match the version of the Azure OpenAI resource
        apiVersion: "2024-12-01-preview"
    });

    // Create a chat completion
    const chatCompletion = await client.chat.completions.create({
        model: deployment,
        messages: [
            { role: "system", content: "You are a helpful writing assistant" },
            { role: "user", content: "Write me a poem about flowers" },
        ],
    });
    console.log(`\n==================== 🌷 COMPLETIONS POEM ====================\n`);
    console.log(chatCompletion.choices[0].message.content);
    // </chat_completion>
}

async function runAgents() {
    // <create_and_run_agent>
    const endpoint = process.env.PROJECT_ENDPOINT as string;
    const deployment = process.env.MODEL_DEPLOYMENT_NAME || 'gpt-4o';
    const client = new AIProjectClient(endpoint, new DefaultAzureCredential());

    // Create an Agent
    const agent = await client.agents.createAgent(deployment, {
        name: 'my-agent',
        instructions: 'You are a helpful agent'
    });
    console.log(`\n==================== 🕵️  POEM AGENT ====================`);

    // Create a thread and message
    const thread = await client.agents.threads.create();
    const prompt = 'Write me a poem about flowers';
    console.log(`\n---------------- 📝 User Prompt ---------------- \n${prompt}`);
    await client.agents.messages.create(thread.id, 'user', prompt);

    // Create run
    let run = await client.agents.runs.create(thread.id, agent.id);

    // Wait for run to complete
    console.log(`\n---------------- 🚦 Run Status ----------------`);
    while (['queued', 'in_progress', 'requires_action'].includes(run.status)) {
        // Avoid adding a lot of messages to the console
        await new Promise((resolve) => setTimeout(resolve, 1000));
        run = await client.agents.runs.get(thread.id, run.id);
        console.log(`Run status: ${run.status}`);
    }

    console.log('\n---------------- 📊 Token Usage ----------------');
    console.table([run.usage]);

    const messagesIterator = await client.agents.messages.list(thread.id);
    const assistantMessage = await getAssistantMessage(messagesIterator);
    console.log('\n---------------- 💬 Response ----------------');
    printAssistantMessage(assistantMessage);

    // Clean up
    console.log(`\n---------------- 🧹 Clean Up Poem Agent ----------------`);
    await client.agents.deleteAgent(agent.id);
    console.log(`Deleted Agent, Agent ID: ${agent.id}`);
    // </create_and_run_agent>

    // <create_filesearch_agent> 
    // Upload a file named product_info_1.md
    console.log(`\n==================== 🕵️  FILE AGENT ====================`);
    const __dirname = path.dirname(fileURLToPath(import.meta.url));
    const filePath = path.join(__dirname, '../data/product_info_1.md');
    const fileStream = fs.createReadStream(filePath);
    fileStream.on('data', (chunk: string | Buffer) => {
        console.log(`Read ${chunk.length} bytes of data.`);
    });
    const file = await client.agents.files.upload(fileStream, 'assistants', {
        fileName: 'product_info_1.md'
    });
    console.log(`Uploaded file, ID: ${file.id}`);
    const vectorStore = await client.agents.vectorStores.create({
        fileIds: [file.id],
        name: 'my_vectorstore'
    });
    console.log('\n---------------- 🗃️ Vector Store Info ----------------');
    console.table([
        {
            'Vector Store ID': vectorStore.id,
            'Usage (bytes)': vectorStore.usageBytes,
            'File Count': vectorStore.fileCounts?.total ?? 'N/A'
        }
    ]);

    // Create an Agent and a FileSearch tool
    const fileSearchTool = ToolUtility.createFileSearchTool([vectorStore.id]);
    const fileAgent = await client.agents.createAgent(deployment, {
        name: 'my-file-agent',
        instructions: 'You are a helpful assistant and can search information from uploaded files',
        tools: [fileSearchTool.definition],
        toolResources: fileSearchTool.resources
    });

    // Create a thread and message
    const fileSearchThread = await client.agents.threads.create({ toolResources: fileSearchTool.resources });
    const filePrompt = 'What are the steps to setup the TrailMaster X4 Tent?';
    console.log(`\n---------------- 📝 User Prompt ---------------- \n${filePrompt}`);
    await client.agents.messages.create(fileSearchThread.id, 'user', filePrompt);

    // Create run
    let fileSearchRun = await client.agents.runs.create(fileSearchThread.id, fileAgent.id).stream();

    for await (const eventMessage of fileSearchRun) {
        if (eventMessage.event === DoneEvent.Done) {
            console.log(`Run completed: ${eventMessage.data}`);
        }
        if (eventMessage.event === ErrorEvent.Error) {
            console.log(`An error occurred. ${eventMessage.data}`);
        }
    }

    const fileSearchMessagesIterator = await client.agents.messages.list(fileSearchThread.id);
    const fileAssistantMessage = await getAssistantMessage(fileSearchMessagesIterator);
    console.log(`\n---------------- 💬 Response ---------------- \n`);
    printAssistantMessage(fileAssistantMessage);

    // Clean up
    console.log(`\n---------------- 🧹 Clean Up File Agent ----------------`);
    client.agents.vectorStores.delete(vectorStore.id);
    client.agents.files.delete(file.id);
    client.agents.deleteAgent(fileAgent.id);
    console.log(`Deleted VectorStore, File, and FileAgent. FileAgent ID: ${fileAgent.id}`);
    // </create_filesearch_agent>
}

// Helper functions
async function getAssistantMessage(messagesIterator: AsyncIterable<ThreadMessage>): Promise<ThreadMessage | null>  {
    for await (const m of messagesIterator) {
        if (m.role === 'assistant') {
            return m;
        }
    }
    return null;
}

// Print assistant message content nicely
function printAssistantMessage(message: ThreadMessage | null) {
    if (!message || !Array.isArray(message.content)) {
        console.log('No assistant message found or content is not in expected format.');
        return;
    }
    
    const output = message.content.map((c: any) => {
        if (typeof c.text === 'object' && c.text.value) {
            return c.text.value;
        } else if (typeof c.text === 'string') {
            return c.text;
        } else {
            return JSON.stringify(c);
        }
    }).join('');
    
    if (typeof output !== 'string') {
        console.log('Value is not a string:', output);
        return;
    }
    
    output.split('\n').forEach(line => console.log(line));
}

