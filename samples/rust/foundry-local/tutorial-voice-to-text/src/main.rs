// <complete_code>
// <imports>
use foundry_local_sdk::{
    AudioSession, ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Request,
    RequestOptions, SearchOptions,
};
use std::io::{self, Write};
use url::Url;
// </imports>

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // <init>
    // Initialize the Foundry Local SDK
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

    // <transcription>
    let speech_model = manager.catalog().get_model("whisper-tiny").await?;

    if !speech_model.is_cached().await? {
        println!("Downloading speech model...");
        speech_model
            .download(Some(|progress: f64| {
                print!("\r  {progress:.1}%");
                io::stdout().flush().ok();
            }))
            .await?;
        println!();
    }

    speech_model.load().await?;
    println!("Speech model loaded.");

    let audio_session = AudioSession::new(&speech_model).await?;
    let audio_path = std::fs::canonicalize("meeting-notes.wav")?;
    let audio_uri = Url::from_file_path(&audio_path)
        .map_err(|_| format!("Could not convert {} to a file URI.", audio_path.display()))?;
    let audio = Item::audio_uri(audio_uri.as_str(), Some("wav"), 0, 0);
    let transcription = audio_session.transcribe(audio).await?;
    println!("\nTranscription:\n{transcription}");

    drop(audio_session);
    speech_model.unload().await?;
    // </transcription>

    // <summarization>
    let chat_model = manager.catalog().get_model("qwen2.5-0.5b").await?;

    if !chat_model.is_cached().await? {
        println!("Downloading chat model...");
        chat_model
            .download(Some(|progress: f64| {
                print!("\r  {progress:.1}%");
                io::stdout().flush().ok();
            }))
            .await?;
        println!();
    }

    chat_model.load().await?;
    println!("Chat model loaded.");

    let chat_session = ChatSession::new(&chat_model).await?;
    chat_session
        .set_options(RequestOptions {
            search: SearchOptions {
                temperature: Some(0.7),
                max_output_tokens: Some(512),
                ..Default::default()
            },
            ..Default::default()
        })
        .await?;

    let response = chat_session
        .process_request(Request::from_items(vec![
            Item::system_message(vec![Item::text(
                "You are a note-taking assistant. Summarize the following transcription into \
                 organized, concise notes with bullet points.",
            )]),
            Item::user_message(vec![Item::text(transcription)]),
        ]))
        .await?;

    println!("\nSummary:");
    for item in &response.items {
        if let Some(message) = item.as_message() {
            print!("{}", message.text());
        } else if let Some(text) = item.as_text() {
            print!("{text}");
        }
    }
    println!();

    drop(chat_session);
    chat_model.unload().await?;
    println!("\nDone. Models unloaded.");
    // </summarization>

    Ok(())
}
// </complete_code>
