// <complete_code>
// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

// <imports>
use std::env;
use std::io::{self, Write};
use std::path::Path;

use foundry_local_sdk::{
    AudioSession, FoundryLocalConfig, FoundryLocalManager, Item, Request, TextKind,
};
use tokio_stream::StreamExt;
// </imports>

const ALIAS: &str = "whisper-tiny";

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Audio Transcription Example");
    println!("===========================\n");

    let audio_path = env::args()
        .nth(1)
        .unwrap_or_else(|| "Recording.mp3".to_string());

    // ── 1. Initialise the manager ────────────────────────────────────────
    // <init>
    let manager = FoundryLocalManager::create(FoundryLocalConfig::new("foundry_local_samples"))?;
    // </init>

    manager
        .download_and_register_eps_with_progress(None, {
            let mut current_ep = String::new();
            move |ep_name: &str, percent: f64| {
                if ep_name != current_ep {
                    if !current_ep.is_empty() {
                        println!();
                    }
                    current_ep = ep_name.to_string();
                }
                print!("\r  {ep_name:<30}  {percent:5.1}%");
                io::stdout().flush().ok();
            }
        })
        .await?;
    println!();

    // ── 2. Pick the Whisper model and ensure it is downloaded ───────────
    // <model_setup>
    let model = manager.catalog().get_model(ALIAS).await?;
    println!("Model: {} (id: {})", model.alias(), model.id());

    if !model.is_cached().await? {
        println!("Downloading model...");
        model
            .download(Some(|progress: f64| {
                print!("\r  {progress:.1}%");
                io::stdout().flush().ok();
            }))
            .await?;
        println!();
    }

    println!("Loading model...");
    model.load().await?;
    println!("✓ Model loaded\n");
    // </model_setup>

    // <transcription>
    // ── 3. Create an audio session ──────────────────────────────────────
    let session = AudioSession::new(&model).await?;
    let bytes = std::fs::read(&audio_path)?;
    let format = Path::new(&audio_path)
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or("mp3")
        .to_string();
    let audio = Item::audio_data(bytes, Some(format), 0, 0);

    // ── 4. Non-streaming transcription ──────────────────────────────────
    println!("--- Non-streaming transcription ---");
    let result = session.transcribe(audio.clone()).await?;
    println!("Transcription: {result}");

    // ── 5. Streaming transcription ──────────────────────────────────────
    println!("--- Streaming transcription ---");
    print!("Transcription: ");
    let mut stream = session.process_streaming_request(Request::from_items(vec![audio]));
    while let Some(item) = stream.next().await {
        match item? {
            Item::SpeechResult(result) => print!("{}", result.text),
            Item::Text {
                text,
                kind: TextKind::Default,
            } => print!("{text}"),
            _ => {}
        }
        io::stdout().flush().ok();
    }
    println!("\n");
    // </transcription>

    // ── 6. Unload the model ─────────────────────────────────────────────
    // <cleanup>
    drop(session);
    println!("Unloading model...");
    model.unload().await?;
    println!("Done.");
    // </cleanup>

    Ok(())
}
// </complete_code>
