// <complete_code>
// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

// <imports>
use std::io::{self, Write};

use foundry_local_sdk::{
    ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Request, RequestOptions,
    SearchOptions, TextKind, ToolChoice, ToolDefinition,
};
use serde_json::{json, Value};
use tokio_stream::StreamExt;
// </imports>

const ALIAS: &str = "qwen2.5-0.5b";

// <tool_implementations>
fn multiply_numbers(first: f64, second: f64) -> f64 {
    first * second
}

fn invoke_tool(name: &str, args: &Value) -> String {
    match name {
        "multiply_numbers" => {
            let first = args.get("first").and_then(Value::as_f64).unwrap_or(0.0);
            let second = args.get("second").and_then(Value::as_f64).unwrap_or(0.0);
            multiply_numbers(first, second).to_string()
        }
        _ => format!("Unknown tool: {name}"),
    }
}
// </tool_implementations>

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("Tool Calling with Foundry Local");
    println!("===============================\n");

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

    // ── 2. Load a model ─────────────────────────────────────────────────
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

    let session = ChatSession::new(&model).await?;

    // <tool_definitions>
    let parameters = json!({
        "type": "object",
        "properties": {
            "first": {
                "type": "number",
                "description": "The first number in the operation"
            },
            "second": {
                "type": "number",
                "description": "The second number in the operation"
            }
        },
        "required": ["first", "second"]
    });
    session
        .add_tool_definition(
            ToolDefinition::new("multiply_numbers", parameters.to_string())
                .with_description("Multiply two numbers."),
        )
        .await?;
    // </tool_definitions>

    // <tool_loop>
    let request = Request::from_items(vec![
        Item::system_message(vec![Item::text(
            "You are a helpful assistant. Use the provided tool when multiplication is requested.",
        )]),
        Item::user_message(vec![Item::text("What is the answer to 7 multiplied by 6?")]),
    ])
    .with_options(RequestOptions {
        search: SearchOptions {
            max_output_tokens: Some(512),
            ..Default::default()
        },
        tool_choice: Some(ToolChoice::Required),
        ..Default::default()
    });

    println!("Chat completion response:");
    let mut tool_results = Vec::new();
    let mut stream = session.process_streaming_request(request);
    while let Some(item) = stream.next().await {
        let item = item?;
        if let Some(call) = item.as_tool_call() {
            let args: Value = serde_json::from_str(&call.arguments).unwrap_or_else(|_| json!({}));
            println!("\nInvoking tool: {} with arguments {args}", call.name);
            let result = invoke_tool(&call.name, &args);
            println!("Tool response: {result}");
            tool_results.push(Item::tool_result(call.call_id.clone(), result));
        } else if let Item::Text {
            text,
            kind: TextKind::Default,
        } = item
        {
            print!("{text}");
            io::stdout().flush().ok();
        }
    }

    if !tool_results.is_empty() {
        println!("\nTool calls completed. Prompting model to continue conversation...\n");
        let follow_up = Request::from_items(tool_results).with_options(RequestOptions {
            search: SearchOptions {
                max_output_tokens: Some(512),
                ..Default::default()
            },
            tool_choice: Some(ToolChoice::None),
            ..Default::default()
        });

        print!("Chat completion response: ");
        let mut stream = session.process_streaming_request(follow_up);
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
    }
    // </tool_loop>

    // ── 7. Clean up ─────────────────────────────────────────────────────
    // <cleanup>
    drop(session);
    println!("Unloading model...");
    model.unload().await?;
    println!("Done.");
    // </cleanup>

    Ok(())
}
// </complete_code>
