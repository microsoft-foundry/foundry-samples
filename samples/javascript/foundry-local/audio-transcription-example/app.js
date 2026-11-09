// <complete_code>
// <imports>
import {
    AudioSession,
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

// <model_setup>
// Get the model object
const modelAlias = 'whisper-tiny'; // Using an available model from the list above
let model = await manager.catalog.getModel(modelAlias);
console.log(`Using model: ${model.id}`);

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

// <transcription>
// Create a native audio session
console.log('\nCreating audio session...');
const audioSession = new AudioSession(model);
console.log('✓ Audio session created');

// Example audio transcription
const audioFile = process.argv[2] || './Recording.mp3';
console.log(`\nTranscribing ${audioFile}...`);
const response = await audioSession.processRequest(
    new Request().addItem(Item.audioFromUri(audioFile))
);
const transcription = response.output.find((item) => item.type === 'speechResult');

console.log('\nAudio transcription result:');
console.log(transcription?.text ?? 'No transcription returned.');
console.log('✓ Audio transcription completed');

// Same example but with streaming transcription using async iteration
console.log('\nTesting streaming audio transcription...');
const stream = audioSession.processStreamingRequest(
    new Request().addItem(Item.audioFromUri(audioFile))
);
for await (const item of stream) {
    if (item.type === 'speechSegment' && item.text) {
        process.stdout.write(item.text);
    }
}
await stream.response;
console.log('\n✓ Streaming transcription completed');
// </transcription>

// <cleanup>
// Unload the model
console.log('Unloading model...');
audioSession.dispose();
await model.unload();
console.log(`✓ Model unloaded`);
// </cleanup>
// </complete_code>
