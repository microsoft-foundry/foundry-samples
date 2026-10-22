// <complete_code>
// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

// <imports>
use foundry_local_sdk::{EmbeddingsSession, FoundryLocalConfig, FoundryLocalManager};
// </imports>

const ALIAS: &str = "qwen3-embedding-0.6b";

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Native Embeddings");
    println!("=================\n");

    // ── 1. Initialise the manager ────────────────────────────────────────
    // <init>
    let manager = FoundryLocalManager::create(FoundryLocalConfig::new("foundry_local_samples"))?;
    // </init>

    // ── 2. Pick a model and ensure it is downloaded ─────────────────────
    // <model_setup>
    let model = manager.catalog().get_model(ALIAS).await?;
    println!("Model: {} (id: {})", model.alias(), model.id());

    if !model.is_cached().await? {
        println!("Downloading model...");
        model
            .download(Some(|progress: f64| {
                print!("\r  {progress:.1}%");
                std::io::Write::flush(&mut std::io::stdout()).ok();
            }))
            .await?;
        println!();
    }

    println!("Loading model...");
    model.load().await?;
    println!("✓ Model loaded\n");
    // </model_setup>

    // ── 3. Create an embedding session ──────────────────────────────────
    // <embedding_client>
    let session = EmbeddingsSession::new(&model).await?;
    // </embedding_client>

    // ── 4. Single embedding ─────────────────────────────────────────────
    // <single_embedding>
    println!("--- Single Embedding ---");
    let embedding = session
        .embed("The quick brown fox jumps over the lazy dog")
        .await?;

    println!("Dimensions: {}", embedding.len());
    println!("First 5 values: {:?}", &embedding[..embedding.len().min(5)]);
    // </single_embedding>

    // ── 5. Batch embeddings ─────────────────────────────────────────────
    // <batch_embedding>
    println!("\n--- Batch Embeddings ---");
    let embeddings = session
        .embed_batch(vec![
            "Machine learning is a subset of artificial intelligence".into(),
            "The capital of France is Paris".into(),
            "Rust is a systems programming language".into(),
        ])
        .await?;

    println!("Number of embeddings: {}", embeddings.len());
    for (i, embedding) in embeddings.iter().enumerate() {
        println!("  [{i}] Dimensions: {}", embedding.len());
    }
    // </batch_embedding>

    // ── 6. Unload the model ─────────────────────────────────────────────
    // <cleanup>
    drop(session);
    println!("\nUnloading model...");
    model.unload().await?;
    println!("Done.");
    // </cleanup>

    Ok(())
}
// </complete_code>
