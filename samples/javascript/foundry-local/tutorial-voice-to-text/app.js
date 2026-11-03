// <complete_code>
// <imports>
import {
    AudioSession,
    ChatSession,
    FoundryLocalManager,
    Item,
    Request
} from 'foundry-local-sdk';
import { fileURLToPath } from 'url';
import path from 'path';
// </imports>

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// <init>
// Initialize the Foundry Local SDK
const manager = FoundryLocalManager.create({
    appName: 'foundry_local_samples',
    logLevel: 'info'
});
// </init>

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

// <transcription>
// Load the speech-to-text model
const speechModel = await manager.catalog.getModel('whisper-tiny');
await speechModel.download((progress) => {
    process.stdout.write(
        `\rDownloading speech model: ${progress.toFixed(2)}%`
    );
});
console.log('\nSpeech model downloaded.');

await speechModel.load();
console.log('Speech model loaded.');

// Transcribe the audio file
const audioSession = new AudioSession(speechModel);
const audioFile = path.join(__dirname, 'meeting-notes.wav');
const transcriptionResponse = await audioSession.processRequest(
    new Request().addItem(Item.audioFromUri(audioFile))
);
const transcription = transcriptionResponse.output.find(
    (item) => item.type === 'speechResult'
);
if (!transcription) {
    throw new Error('The speech model returned no transcription.');
}
console.log(`\nTranscription:\n${transcription.text}`);

// Unload the speech model to free memory
audioSession.dispose();
await speechModel.unload();
// </transcription>

// <summarization>
// Load the chat model for summarization
const chatModel = await manager.catalog.getModel('qwen2.5-0.5b');
await chatModel.download((progress) => {
    process.stdout.write(
        `\rDownloading chat model: ${progress.toFixed(2)}%`
    );
});
console.log('\nChat model downloaded.');

await chatModel.load();
console.log('Chat model loaded.');

// Summarize the transcription into organized notes
const chatSession = new ChatSession(chatModel);
const request = new Request()
    .addItem(Item.systemMessage(
        'You are a note-taking assistant. Summarize ' +
        'the following transcription into organized, ' +
        'concise notes with bullet points.'
    ))
    .addItem(Item.userMessage(transcription.text));

const response = await chatSession.processRequest(request);
const summary = response.output
    .map((item) => item.type === 'message'
        ? item.content ?? item.parts?.map((part) => part.text ?? '').join('') ?? ''
        : item.type === 'text' ? item.text : '')
    .join('');
console.log(`\nSummary:\n${summary}`);

// Clean up
chatSession.dispose();
await chatModel.unload();
console.log('\nDone. Models unloaded.');
// </summarization>
// </complete_code>
