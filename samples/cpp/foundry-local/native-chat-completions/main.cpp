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
      const ModelInfo info = variant->GetInfo();
      if (info.DeviceType() == FOUNDRY_LOCAL_DEVICE_CPU &&
          (info.Task() == "chat-completion" || info.Task() == "coding")) {
        model->SelectVariant(*variant);
        return model;
      }
    }
  }
  return nullptr;
}

void PrintMessages(const Response& response) {
  for (const Item& item : response.GetItems()) {
    if (item.GetType() != FOUNDRY_LOCAL_ITEM_MESSAGE) {
      continue;
    }
    for (const Item& part : item.GetMessage().parts) {
      if (part.GetType() == FOUNDRY_LOCAL_ITEM_TEXT &&
          part.GetText().type == FOUNDRY_LOCAL_TEXT_ITEM_TYPE_DEFAULT) {
        std::cout << part.GetText().text;
      }
    }
  }
  std::cout << "\n";
}

int main() {
  try {
    Configuration config("foundry_local_cpp_native_chat");
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

    {
      ChatSession session(*model);
      Request request{UserMessage("What is the capital of France?")};
      std::cout << "Assistant: ";
      PrintMessages(session.ProcessRequest(request));
    }

    {
      ChatSession session(*model);
      session.SetStreamingCallback([](Item item) {
        if (item.GetType() == FOUNDRY_LOCAL_ITEM_TEXT &&
            item.GetText().type == FOUNDRY_LOCAL_TEXT_ITEM_TYPE_DEFAULT) {
          std::cout << item.GetText().text << std::flush;
        }
        return 0;
      });
      Request request{UserMessage("Name two landmarks in Paris.")};
      std::cout << "Streaming assistant: ";
      session.ProcessRequest(request);
      std::cout << "\n";
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
