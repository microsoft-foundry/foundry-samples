// <complete_code>
// <imports>
use foundry_local_sdk::{
    ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Request, RequestOptions,
    SearchOptions, TextKind,
};
use std::io::{self, BufRead, Write};
use tokio_stream::StreamExt;
// </imports>

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
    let session = ChatSession::new(&model).await?;
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
    println!("Model loaded and ready.");
    // </init>

    // <system_prompt>
    let system_prompt = "You are a helpful, friendly assistant. Keep your responses concise and \
                         conversational. If you don't know something, say so.";
    // </system_prompt>

    println!("\nChat assistant ready! Type 'quit' to exit.\n");

    let stdin = io::stdin();
    // <conversation_loop>
    loop {
        print!("You: ");
        io::stdout().flush()?;

        let mut input = String::new();
        stdin.lock().read_line(&mut input)?;
        let input = input.trim();

        if input.eq_ignore_ascii_case("quit") || input.eq_ignore_ascii_case("exit") {
            break;
        }
        if input.is_empty() {
            continue;
        }

        let mut items = Vec::new();
        if session.turn_count() == 0 {
            items.push(Item::system_message(vec![Item::text(system_prompt)]));
        }
        items.push(Item::user_message(vec![Item::text(input)]));

        // <streaming>
        print!("Assistant: ");
        io::stdout().flush()?;
        let mut stream = session.process_streaming_request(Request::from_items(items));
        while let Some(item) = stream.next().await {
            if let Item::Text {
                text,
                kind: TextKind::Default,
            } = item?
            {
                print!("{text}");
                io::stdout().flush()?;
            }
        }
        println!("\n");
        // </streaming>
    }
    // </conversation_loop>

    drop(session);
    model.unload().await?;
    println!("Model unloaded. Goodbye!");

    Ok(())
}
// </complete_code>
