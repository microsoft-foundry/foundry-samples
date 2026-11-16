// <complete_code>
// <imports>
import {
    ChatSession,
    FoundryLocalManager,
    Item,
    Request
} from 'foundry-local-sdk';
import { readFileSync, readdirSync, statSync } from 'fs';
import { join, basename } from 'path';
// </imports>

async function summarizeFile(chatSession, filePath, systemPrompt) {
    const content = readFileSync(filePath, 'utf-8');
    const request = new Request()
        .addItem(Item.systemMessage(systemPrompt))
        .addItem(Item.userMessage(content));
    const response = await chatSession.processRequest(request);
    const text = response.output
        .map((item) => item.type === 'message'
            ? item.content ?? item.parts?.map((part) => part.text ?? '').join('') ?? ''
            : item.type === 'text' ? item.text : '')
        .join('');
    console.log(text);
}

async function summarizeDirectory(model, directory, systemPrompt) {
    const txtFiles = readdirSync(directory)
        .filter(f => f.endsWith('.txt'))
        .sort();

    if (txtFiles.length === 0) {
        console.log(`No .txt files found in ${directory}`);
        return;
    }

    for (const fileName of txtFiles) {
        console.log(`--- ${fileName} ---`);
        const session = new ChatSession(model);
        await summarizeFile(session, join(directory, fileName), systemPrompt);
        session.dispose();
        console.log();
    }
}

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
console.log('Model loaded and ready.\n');

// </init>

// <summarization>
const systemPrompt =
    'Summarize the following document into concise bullet points. ' +
    'Focus on the key points and main ideas.';

// <file_reading>
const target = process.argv[2] || 'document.txt';
// </file_reading>

try {
    const stats = statSync(target);
    if (stats.isDirectory()) {
        await summarizeDirectory(model, target, systemPrompt);
    } else {
        console.log(`--- ${basename(target)} ---`);
        const session = new ChatSession(model);
        await summarizeFile(session, target, systemPrompt);
        session.dispose();
    }
} catch {
    console.log(`--- ${basename(target)} ---`);
    const session = new ChatSession(model);
    await summarizeFile(session, target, systemPrompt);
    session.dispose();
}
// </summarization>

// Clean up
await model.unload();
console.log('\nModel unloaded. Done!');
// </complete_code>
