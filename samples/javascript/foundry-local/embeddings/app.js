// <complete_code>
// <imports>
import {
    EmbeddingsSession,
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

// <model_setup>
// Get an embedding model
const modelAlias = 'qwen3-embedding-0.6b';
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

// <single_embedding>
// Create a native embeddings session
console.log('\nCreating embeddings session...');
const embeddingsSession = new EmbeddingsSession(model);
console.log('✓ Embeddings session created');

// Generate a single embedding
console.log('\n--- Single Embedding ---');
const response = await embeddingsSession.processRequest(
    new Request().addItem(Item.text(
        'The quick brown fox jumps over the lazy dog'
    ))
);

const tensor = response.output.find((item) => item.type === 'tensor');
if (!tensor || tensor.dataType !== 'float') {
    throw new Error('The model returned no float embedding tensor.');
}
const embedding = new Float32Array(
    tensor.data.buffer,
    tensor.data.byteOffset,
    tensor.data.byteLength / Float32Array.BYTES_PER_ELEMENT
);
console.log(`Dimensions: ${embedding.length}`);
console.log(`First 5 values: [${Array.from(
    embedding.slice(0, 5),
    (value) => value.toFixed(6)
).join(', ')}]`);
// </single_embedding>

// <batch_embedding>
// Generate embeddings for multiple inputs
console.log('\n--- Batch Embeddings ---');
const batchRequest = new Request();
for (const input of [
    'Machine learning is a subset of artificial intelligence',
    'The capital of France is Paris',
    'JavaScript is a programming language'
]) {
    batchRequest.addItem(Item.text(input));
}
const batchResponse = await embeddingsSession.processRequest(batchRequest);
const tensors = batchResponse.output.filter((item) => item.type === 'tensor');

console.log(`Number of embeddings: ${tensors.length}`);
for (let i = 0; i < tensors.length; i++) {
    const dimensions = tensors[i].data.byteLength / Float32Array.BYTES_PER_ELEMENT;
    console.log(`  [${i}] Dimensions: ${dimensions}`);
}
// </batch_embedding>

// <cleanup>
// Unload the model
console.log('\nUnloading model...');
embeddingsSession.dispose();
await model.unload();
console.log('✓ Model unloaded');
// </cleanup>
// </complete_code>
