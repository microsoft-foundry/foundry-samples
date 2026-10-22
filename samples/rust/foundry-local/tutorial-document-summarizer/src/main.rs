// <complete_code>
// <imports>
use foundry_local_sdk::{
    ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Model, Request, RequestOptions,
    SearchOptions,
};
use std::io::{self, Write};
use std::path::Path;
use std::{env, fs};
// </imports>

async fn summarize_file(
    model: &Model,
    file_path: &Path,
    system_prompt: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let content = fs::read_to_string(file_path)?;
    let session = ChatSession::new(model).await?;
    session
        .set_options(RequestOptions {
            search: SearchOptions {
                temperature: Some(0.7),
                max_output_tokens: Some(512),
                ..Default::default()
            },
            ..Default::default()
        })
        .await?;

    let response = session
        .process_request(Request::from_items(vec![
            Item::system_message(vec![Item::text(system_prompt)]),
            Item::user_message(vec![Item::text(content)]),
        ]))
        .await?;

    for item in &response.items {
        if let Some(message) = item.as_message() {
            print!("{}", message.text());
        } else if let Some(text) = item.as_text() {
            print!("{text}");
        }
    }
    println!();
    drop(session);
    Ok(())
}

async fn summarize_directory(
    model: &Model,
    directory: &Path,
    system_prompt: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut txt_files: Vec<_> = fs::read_dir(directory)?
        .filter_map(Result::ok)
        .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "txt"))
        .collect();

    txt_files.sort_by_key(|entry| entry.path());

    if txt_files.is_empty() {
        println!("No .txt files found in {}", directory.display());
        return Ok(());
    }

    for entry in &txt_files {
        println!("--- {} ---", entry.file_name().to_string_lossy());
        summarize_file(model, &entry.path(), system_prompt).await?;
        println!();
    }

    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // <init>
    // Initialize the Foundry Local SDK
    let manager = FoundryLocalManager::create(FoundryLocalConfig::new("foundry_local_samples"))?;

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

    let model = manager.catalog().get_model("qwen2.5-0.5b").await?;
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

    model.load().await?;
    println!("Model loaded and ready.\n");
    // </init>

    // <summarization>
    let system_prompt = "Summarize the following document into concise bullet points. Focus on \
                         the key points and main ideas.";

    // <file_reading>
    let target = env::args()
        .nth(1)
        .unwrap_or_else(|| "document.txt".to_string());
    let target_path = Path::new(&target);
    // </file_reading>

    if target_path.is_dir() {
        summarize_directory(&model, target_path, system_prompt).await?;
    } else {
        let file_name = target_path
            .file_name()
            .map(|name| name.to_string_lossy().to_string())
            .unwrap_or_else(|| target.clone());
        println!("--- {file_name} ---");
        summarize_file(&model, target_path, system_prompt).await?;
    }
    // </summarization>

    model.unload().await?;
    println!("\nModel unloaded. Done!");

    Ok(())
}
// </complete_code>
