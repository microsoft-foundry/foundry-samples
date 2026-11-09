// <complete_code>
// <imports>
use foundry_local_sdk::{
    ChatSession, FoundryLocalConfig, FoundryLocalManager, Item, Request, RequestOptions,
    SearchOptions, ToolChoice, ToolDefinition,
};
use serde_json::{json, Value};
use std::io::{self, BufRead, Write};
// </imports>

// <tool_implementations>
fn execute_tool(name: &str, arguments: &Value) -> Value {
    match name {
        "get_weather" => {
            let location = arguments["location"].as_str().unwrap_or("unknown");
            let unit = arguments["unit"].as_str().unwrap_or("celsius");
            let temp = if unit == "celsius" { 22 } else { 72 };
            json!({
                "location": location,
                "temperature": temp,
                "unit": unit,
                "condition": "Sunny"
            })
        }
        "calculate" => {
            let expression = arguments["expression"].as_str().unwrap_or("");
            let is_valid = expression
                .chars()
                .all(|character| "0123456789+-*/(). ".contains(character));
            if !is_valid {
                return json!({"error": "Invalid expression"});
            }
            match eval_expression(expression) {
                Ok(result) => json!({"expression": expression, "result": result}),
                Err(error) => json!({"error": error}),
            }
        }
        _ => json!({"error": format!("Unknown function: {name}")}),
    }
}

fn eval_expression(expr: &str) -> Result<f64, String> {
    let expr = expr.replace(' ', "");
    let chars: Vec<char> = expr.chars().collect();
    let mut pos = 0;
    let result = parse_add(&chars, &mut pos)?;
    if pos < chars.len() {
        return Err("Unexpected character".to_string());
    }
    Ok(result)
}

fn parse_add(chars: &[char], pos: &mut usize) -> Result<f64, String> {
    let mut result = parse_mul(chars, pos)?;
    while *pos < chars.len() && (chars[*pos] == '+' || chars[*pos] == '-') {
        let op = chars[*pos];
        *pos += 1;
        let right = parse_mul(chars, pos)?;
        result = if op == '+' {
            result + right
        } else {
            result - right
        };
    }
    Ok(result)
}

fn parse_mul(chars: &[char], pos: &mut usize) -> Result<f64, String> {
    let mut result = parse_atom(chars, pos)?;
    while *pos < chars.len() && (chars[*pos] == '*' || chars[*pos] == '/') {
        let op = chars[*pos];
        *pos += 1;
        let right = parse_atom(chars, pos)?;
        result = if op == '*' {
            result * right
        } else {
            result / right
        };
    }
    Ok(result)
}

fn parse_atom(chars: &[char], pos: &mut usize) -> Result<f64, String> {
    if *pos < chars.len() && chars[*pos] == '(' {
        *pos += 1;
        let result = parse_add(chars, pos)?;
        if *pos < chars.len() && chars[*pos] == ')' {
            *pos += 1;
        }
        return Ok(result);
    }
    let start = *pos;
    while *pos < chars.len() && (chars[*pos].is_ascii_digit() || chars[*pos] == '.') {
        *pos += 1;
    }
    if start == *pos {
        return Err("Expected number".to_string());
    }
    chars[start..*pos]
        .iter()
        .collect::<String>()
        .parse::<f64>()
        .map_err(|error| error.to_string())
}
// </tool_implementations>

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // <tool_definitions>
    let weather_schema = json!({
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "The city or location"},
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit"
            }
        },
        "required": ["location"]
    });
    let calculator_schema = json!({
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The math expression to evaluate"
            }
        },
        "required": ["expression"]
    });
    // </tool_definitions>

    // <init>
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
            tool_choice: Some(ToolChoice::Auto),
            ..Default::default()
        })
        .await?;
    session
        .add_tool_definition(
            ToolDefinition::new("get_weather", weather_schema.to_string())
                .with_description("Get the current weather for a location."),
        )
        .await?;
    session
        .add_tool_definition(
            ToolDefinition::new("calculate", calculator_schema.to_string())
                .with_description("Perform a math calculation."),
        )
        .await?;
    // </init>

    // <tool_loop>
    println!("\nTool-calling assistant ready! Type 'quit' to exit.\n");
    let stdin = io::stdin();
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
            items.push(Item::system_message(vec![Item::text(
                "You are a helpful assistant with access to tools. Use them when needed.",
            )]));
        }
        items.push(Item::user_message(vec![Item::text(input)]));

        loop {
            let response = session
                .process_request(Request::from_items(items).with_options(RequestOptions {
                    search: SearchOptions {
                        temperature: Some(0.7),
                        max_output_tokens: Some(512),
                        ..Default::default()
                    },
                    tool_choice: Some(ToolChoice::Auto),
                    ..Default::default()
                }))
                .await?;

            let mut tool_results = Vec::new();
            let mut answer = String::new();
            for item in &response.items {
                if let Some(call) = item.as_tool_call() {
                    let arguments: Value =
                        serde_json::from_str(&call.arguments).unwrap_or_else(|_| json!({}));
                    println!("  Tool call: {}({arguments})", call.name);
                    let result = execute_tool(&call.name, &arguments);
                    tool_results.push(Item::tool_result(call.call_id.clone(), result.to_string()));
                } else if let Some(message) = item.as_message() {
                    answer.push_str(&message.text());
                } else if let Some(text) = item.as_text() {
                    answer.push_str(text);
                }
            }

            if tool_results.is_empty() {
                println!("Assistant: {answer}\n");
                break;
            }
            items = tool_results;
        }
    }

    drop(session);
    model.unload().await?;
    println!("Model unloaded. Goodbye!");
    // </tool_loop>

    Ok(())
}
// </complete_code>
