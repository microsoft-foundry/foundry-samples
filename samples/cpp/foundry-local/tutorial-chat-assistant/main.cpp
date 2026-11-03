// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <iostream>
#include <memory>
#include <string>

using namespace foundry_local;

std::unique_ptr<IModel> SelectChatModel(ICatalog& catalog) {
  for (const std::string alias : {"qwen2.5-0.5b", "qwen3.5-0.8b"}) {
    auto model = catalog.GetModel(alias);
    if (!model) {
      continue;
    }
    for (const auto& variant : model->GetVariants()) {
      const auto info = variant->GetInfo();
      if (info.DeviceType() == FOUNDRY_LOCAL_DEVICE_CPU &&
          (info.Task() == "chat-completion" || info.Task() == "coding")) {
        model->SelectVariant(*variant);
        return model;
      }
    }
  }
  return nullptr;
}

void EnableStreaming(ChatSession& session);

int main() {
  try {
    // <init>
    Configuration config("foundry_local_cpp_tutorial_chat");
    Manager manager(std::move(config));
    auto model = SelectChatModel(manager.GetCatalog());
    if (!model) {
      throw std::runtime_error("No supported CPU chat model was found.");
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
      session.SetOptions({
          .search = {.temperature = 0.2F, .max_output_tokens = 512, .seed = 42},
      });

      // <system_prompt>
      Request system_prompt{
          SystemMessage(
              "You are a concise, friendly local assistant. State when you are unsure."),
      };
      session.ProcessRequest(system_prompt);
      // </system_prompt>

      // <conversation_loop>
      std::cout << "Enter a message, or type 'exit'.\n";
      for (std::string input; std::cout << "You: " && std::getline(std::cin, input);) {
        if (input == "exit" || input == "quit") {
          break;
        }
        if (input.empty()) {
          continue;
        }

        EnableStreaming(session);
        Request request{UserMessage(input)};
        std::cout << "Assistant: ";
        session.ProcessRequest(request);
        std::cout << "\n";
      }
      // </conversation_loop>
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

// <streaming>
void EnableStreaming(ChatSession& session) {
  session.SetStreamingCallback([](Item item) {
    if (item.GetType() == FOUNDRY_LOCAL_ITEM_TEXT &&
        item.GetText().type == FOUNDRY_LOCAL_TEXT_ITEM_TYPE_DEFAULT) {
      std::cout << item.GetText().text << std::flush;
    }
    return 0;
  });
}
// </streaming>
// </complete_code>
