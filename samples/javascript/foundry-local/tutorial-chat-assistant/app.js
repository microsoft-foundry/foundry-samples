// <complete_code>
// <imports>
import {
    ChatSession,
    FoundryLocalManager,
    Item,
    Request
} from 'foundry-local-sdk';
import * as readline from 'readline';
// </imports>

// <init>
// Initialize the Foundry Local SDK
const manager = FoundryLocalManager.create({
    appName: 'foundry_local_samples',
    logLevel: 'info'
});

// Download and register all execution providers.
let currentEp = '';
await manager.downloadAndRegisterEps((epName, percent) => {
    if (epName !== currentEp) {
        if (currentEp !== '') process.stdout.write('\n');
        currentEp = epName;
    }
    process.stdout.write(`\r  ${epName.padEnd(30)}  ${percent.toFixed(1).padStart(5)}%`);
});
if (currentEp !== '') process.stdout.write('\n');

// Select and load a model from the catalog
const model = await manager.catalog.getModel('qwen2.5-0.5b');

await model.download((progress) => {
    process.stdout.write(`\rDownloading model: ${progress.toFixed(2)}%`);
});
console.log('\nModel downloaded.');

await model.load();
console.log('Model loaded and ready.');

// Create a stateful native chat session
const chatSession = new ChatSession(model);
chatSession.setOptions({
    search: { temperature: 0.7, maxOutputTokens: 512 }
});
// </init>

// <system_prompt>
// Start the conversation with a system prompt
const systemPrompt =
    'You are a helpful, friendly assistant. Keep your responses ' +
    'concise and conversational. If you don\'t know something, say so.';
let firstTurn = true;
// </system_prompt>

// Set up readline for console input
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

const askQuestion = (prompt) => new Promise((resolve) => {
    if (rl.closed) return resolve('quit');
    const onClose = () => resolve('quit');
    rl.once('close', onClose);
    try {
        rl.question(prompt, (answer) => {
            rl.off('close', onClose);
            resolve(answer);
        });
    } catch {
        rl.off('close', onClose);
        resolve('quit');
    }
});

console.log('\nChat assistant ready! Type \'quit\' to exit.\n');

// <conversation_loop>
while (true) {
    const userInput = await askQuestion('You: ');
    if (userInput.trim().toLowerCase() === 'quit' ||
        userInput.trim().toLowerCase() === 'exit') {
        break;
    }

    const request = new Request();
    if (firstTurn) {
        request.addItem(Item.systemMessage(systemPrompt));
        firstTurn = false;
    }
    request.addItem(Item.userMessage(userInput));

    // <streaming>
    // Stream the response token by token
    process.stdout.write('Assistant: ');
    const stream = chatSession.processStreamingRequest(request);
    for await (const item of stream) {
        if (item.type === 'text' && item.textType === 'default') {
            process.stdout.write(item.text);
        }
    }
    await stream.response;
    console.log('\n');
    // </streaming>
}
// </conversation_loop>

// Clean up - unload the model
chatSession.dispose();
await model.unload();
console.log('Model unloaded. Goodbye!');
rl.close();
// </complete_code>
