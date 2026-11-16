// <complete_code>
// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

// <imports>
use std::io::{self, Write};

use foundry_local_sdk::{
    ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Request, RequestOptions,
    SearchOptions, TextKind,
};
use tokio_stream::StreamExt;
// </imports>

const ALIAS: &str = "qwen2.5-0.5b";

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Native Chat Completions");
    println!("=======================\n");

    // ── 1. Initialise the manager ────────────────────────────────────────
    // <init>
    let manager = FoundryLocalManager::create(FoundryLocalConfig::new("foundry_local_samples"))?;
    // </init>

    // Download and register all execution providers.
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

    // ── 2. Pick a model and ensure it is downloaded ─────────────────────
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

    // ── 3. Create a stateful chat session ────────────────────────────────
    // <chat_client>
    let session = ChatSession::new(&model).await?;
    session
        .set_options(RequestOptions {
            search: SearchOptions {
                temperature: Some(0.7),
                max_output_tokens: Some(256),
                ..Default::default()
            },
            ..Default::default()
        })
        .await?;
    // </chat_client>

    // ── 4. Non-streaming chat completion ────────────────────────────────
    // <chat_completion>
    let request = Request::from_items(vec![
        Item::system_message(vec![Item::text("You are a helpful assistant.")]),
        Item::user_message(vec![Item::text("What is Rust's ownership model?")]),
    ]);

    println!("--- Non-streaming completion ---");
    let response = session.process_request(request).await?;
    print!("Assistant: ");
    for item in &response.items {
        if let Some(message) = item.as_message() {
            print!("{}", message.text());
        }
    }
    println!();
    // </chat_completion>

    // ── 5. Streaming chat completion ────────────────────────────────────
    // <streaming>
    let request = Request::from_items(vec![Item::user_message(vec![Item::text(
        "Explain the borrow checker in two sentences.",
    )])]);

    println!("\n--- Streaming completion ---");
    print!("Assistant: ");
    let mut stream = session.process_streaming_request(request);
    while let Some(item) = stream.next().await {
        if let Item::Text {
            text,
            kind: TextKind::Default,
        } = item?
        {
            print!("{text}");
            io::stdout().flush().ok();
        }
    }
    println!("\n");
    // </streaming>

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
