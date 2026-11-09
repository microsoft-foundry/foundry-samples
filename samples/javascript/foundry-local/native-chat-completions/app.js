// <complete_code>
// <imports>
import {
    ChatSession,
    FoundryLocalManager,
    Item,
    Request
} from 'foundry-local-sdk';
// </imports>

// Initialize the Foundry Local SDK
console.log('Initializing Foundry Local SDK...');

// <init>
const manager = FoundryLocalManager.create({
    appName: 'foundry_local_samples',
    logLevel: 'info'
});
// </init>
console.log('✓ SDK initialized successfully');

// Discover available execution providers and their registration status.
const eps = manager.discoverEps();
const maxNameLen = 30;
console.log('\nAvailable execution providers:');
console.log(`  ${'Name'.padEnd(maxNameLen)}  Registered`);
console.log(`  ${'─'.repeat(maxNameLen)}  ──────────`);
for (const ep of eps) {
    console.log(`  ${ep.name.padEnd(maxNameLen)}  ${ep.isRegistered}`);
}

// Download and register all execution providers with per-EP progress.
// EP packages include dependencies and may be large.
// Download is only required again if a new version of the EP is released.
console.log('\nDownloading execution providers:');
if (eps.length > 0) {
    let currentEp = '';
    await manager.downloadAndRegisterEps((epName, percent) => {
        if (epName !== currentEp) {
            if (currentEp !== '') {
                process.stdout.write('\n');
            }
            currentEp = epName;
        }
        process.stdout.write(`\r  ${epName.padEnd(maxNameLen)}  ${percent.toFixed(1).padStart(5)}%`);
    });
    process.stdout.write('\n');
} else {
    console.log('No execution providers to download.');
}

// <model_setup>
// Get the model object
const modelAlias = 'qwen2.5-0.5b'; // Using an available model from the list above
const model = await manager.catalog.getModel(modelAlias);

// Download the model
console.log(`\nDownloading model ${modelAlias}...`);
await model.download((progress) => {
    process.stdout.write(`\rDownloading... ${progress.toFixed(2)}%`);
});
console.log('\n✓ Model downloaded');

// Load the model
console.log(`\nLoading model ${modelAlias}...`);
await model.load();
console.log('✓ Model loaded');
// </model_setup>

// <chat_completion>
// Create a stateful native chat session
console.log('\nCreating chat session...');
const chatSession = new ChatSession(model);
chatSession.setOptions({
    search: { temperature: 0.7, maxOutputTokens: 256 }
});
console.log('✓ Chat session created');

// Example chat completion
console.log('\nTesting chat completion...');
const completion = await chatSession.processRequest(
    new Request().addItem(Item.userMessage('Why is the sky blue?'))
);

console.log('\nChat completion result:');
for (const item of completion.output) {
    if (item.type === 'message') {
        process.stdout.write(item.content ?? item.parts?.map((part) => part.text ?? '').join('') ?? '');
    } else if (item.type === 'text' && item.textType === 'default') {
        process.stdout.write(item.text);
    }
}
console.log();
// </chat_completion>

// <streaming>
// Example streaming completion
console.log('\nTesting streaming completion...');
const stream = chatSession.processStreamingRequest(
    new Request().addItem(Item.userMessage(
        'Write a short poem about programming.'
    ))
);
for await (const item of stream) {
    if (item.type === 'text' && item.textType === 'default') {
        process.stdout.write(item.text);
    }
}
await stream.response;
console.log('\n');
// </streaming>

// <cleanup>
// Unload the model
console.log('Unloading model...');
chatSession.dispose();
await model.unload();
console.log(`✓ Model unloaded`);
// </cleanup>
// </complete_code>
    