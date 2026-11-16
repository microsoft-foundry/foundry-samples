// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <iostream>
#include <string>

using namespace foundry_local;

constexpr const char* kWeatherSchema = R"({
  "type": "object",
  "properties": {
    "location": {"type": "string", "description": "City name"}
  },
  "required": ["location"]
})";

void PrintAssistantMessage(const Item& item) {
  for (const Item& part : item.GetMessage().parts) {
    if (part.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
      std::cout << part.GetText().text;
    }
  }
  std::cout << "\n";
}

int main() {
  try {
    Configuration config("foundry_local_cpp_tool_calling");
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

    {
      ChatSession session(*model);
      session.AddToolDefinition(ToolDefinition{
          "get_weather",
          "Get the current weather for a city.",
          kWeatherSchema,
      });

      Request request{UserMessage("What is the weather in Paris?")};
      request.SetOptions({
          .search = {.temperature = 0.0F, .max_output_tokens = 256, .seed = 42},
          .tool_choice = FOUNDRY_LOCAL_TOOL_CHOICE_REQUIRED,
      });

      Response response = session.ProcessRequest(request);
      for (int iteration = 0; iteration < 8; ++iteration) {
        bool handled_tool = false;
        for (const Item& item : response.GetItems()) {
          if (item.GetType() == FOUNDRY_LOCAL_ITEM_MESSAGE) {
            std::cout << "Assistant: ";
            PrintAssistantMessage(item);
            handled_tool = false;
            break;
          }
          if (item.GetType() == FOUNDRY_LOCAL_ITEM_TOOL_CALL) {
            const auto call = item.GetToolCall();
            std::cout << "Tool call: " << call.name << "(" << call.arguments << ")\n";
            Request result;
            result.AddItem(Item::ToolResult(
                std::string(call.call_id),
                R"({"temperature":22,"unit":"celsius","condition":"sunny"})"));
            result.SetOptions({
                .search = {.temperature = 0.0F, .max_output_tokens = 256, .seed = 42},
                .tool_choice = FOUNDRY_LOCAL_TOOL_CHOICE_NONE,
            });
            response = session.ProcessRequest(result);
            handled_tool = true;
            break;
          }
        }
        if (!handled_tool) {
          break;
        }
      }
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
