// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

using namespace foundry_local;

// <tool_definitions>
constexpr const char* kTimeSchema = R"({
  "type": "object",
  "properties": {
    "timezone": {"type": "string", "description": "Requested timezone label"}
  },
  "required": ["timezone"]
})";

std::string GetLocalTime() {
  const auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
  std::tm local_time{};
#ifdef _WIN32
  localtime_s(&local_time, &now);
#else
  localtime_r(&now, &local_time);
#endif
  std::ostringstream output;
  output << std::put_time(&local_time, "%Y-%m-%d %H:%M:%S");
  return R"({"timezone":"local","time":")" + output.str() + R"("})";
}
// </tool_definitions>

void PrintAssistant(const Item& message) {
  for (const Item& part : message.GetMessage().parts) {
    if (part.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
      std::cout << part.GetText().text;
    }
  }
  std::cout << "\n";
}

int main() {
  try {
    // <init>
    Configuration config("foundry_local_cpp_tool_assistant");
    Manager manager(std::move(config));
    auto model = manager.GetCatalog().GetModel("qwen2.5-0.5b");
    if (!model) {
      throw std::runtime_error("Model 'qwen2.5-0.5b' was not found in the catalog.");
    }
    if (!model->IsCached()) {
      model->Download([](float progress) {
        std::cout << "\rDownloading model: " << static_cast<int>(progress) << "%" << std::flush;
        return 0;
      });
      std::cout << "\n";
    }
    model->Load();
    // </init>

    {
    ChatSession session(*model);
    session.AddToolDefinition(ToolDefinition{
        "get_current_time",
        "Get the current local date and time.",
        kTimeSchema,
    });

    // <tool_loop>
    Request request{
        SystemMessage("Use the available tool when current time is requested."),
        UserMessage("What time is it?"),
    };
    request.SetOptions({
        .search = {.temperature = 0.0F, .max_output_tokens = 256, .seed = 42},
        .tool_choice = FOUNDRY_LOCAL_TOOL_CHOICE_REQUIRED,
    });
    Response response = session.ProcessRequest(request);

    for (int iteration = 0; iteration < 8; ++iteration) {
      bool called_tool = false;
      for (const Item& item : response.GetItems()) {
        if (item.GetType() == FOUNDRY_LOCAL_ITEM_MESSAGE) {
          std::cout << "Assistant: ";
          PrintAssistant(item);
          continue;
        }
        if (item.GetType() != FOUNDRY_LOCAL_ITEM_TOOL_CALL) {
          continue;
        }

        const auto call = item.GetToolCall();
        if (call.name != "get_current_time") {
          throw std::runtime_error("The model requested an unknown tool.");
        }
        Request tool_result;
        tool_result.AddItem(Item::ToolResult(std::string(call.call_id), GetLocalTime()));
        tool_result.SetOptions({
            .search = {.temperature = 0.0F, .max_output_tokens = 256, .seed = 42},
            .tool_choice = FOUNDRY_LOCAL_TOOL_CHOICE_NONE,
        });
        response = session.ProcessRequest(tool_result);
        called_tool = true;
        break;
      }
      if (!called_tool) {
        break;
      }
    }
    // </tool_loop>
    }

    model->Unload();
    manager.Shutdown();
  } catch (const Error& error) {
    std::cerr << "Foundry Local error [" << error.Code() << "]: " << error.what() << "\n";
    return 1;
  } catch (const std::exception& error) {
    std::cerr << "Error: " << error.what() << "\n";
    return 1;
  }

  return 0;
}
// </complete_code>
