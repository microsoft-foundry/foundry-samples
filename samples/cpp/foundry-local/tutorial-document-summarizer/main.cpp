// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

using namespace foundry_local;

std::string ResponseText(const Response& response) {
  std::string text;
  for (const Item& item : response.GetItems()) {
    if (item.GetType() != FOUNDRY_LOCAL_ITEM_MESSAGE) {
      continue;
    }
    for (const Item& part : item.GetMessage().parts) {
      if (part.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
        text.append(part.GetText().text);
      }
    }
  }
  return text;
}

int main(int argc, char* argv[]) {
  try {
    Configuration config("foundry_local_cpp_document_summarizer");
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

    // <file_reading>
    const std::string path = argc > 1 ? argv[1] : "document.txt";
    std::ifstream input(path);
    if (!input) {
      throw std::runtime_error("Could not open document: " + path);
    }
    const std::string document{
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>(),
    };
    if (document.empty()) {
      throw std::runtime_error("The document is empty.");
    }
    // </file_reading>

    // <summarization>
    {
      ChatSession session(*model);
      Request request{
          SystemMessage(
              "Summarize the supplied document using a short overview and three bullet points."),
          UserMessage(document),
      };
      request.SetOptions({
          .search = {.temperature = 0.2F, .max_output_tokens = 512, .seed = 42},
      });
      std::cout << ResponseText(session.ProcessRequest(request)) << "\n";
    }
    // </summarization>

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
