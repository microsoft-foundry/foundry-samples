// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <iostream>
#include <string>

using namespace foundry_local;

void DownloadIfNeeded(IModel& model, const std::string& label) {
  if (model.IsCached()) {
    std::cout << "Using cached " << label << " model.\n";
    return;
  }
  model.Download([&label](float progress) {
    std::cout << "\rDownloading " << label << " model: " << static_cast<int>(progress) << "%"
              << std::flush;
    return 0;
  });
  std::cout << "\n";
}

std::string ResponseText(const Response& response) {
  std::string text;
  for (const Item& item : response.GetItems()) {
    if (item.GetType() == FOUNDRY_LOCAL_ITEM_SPEECH_RESULT) {
      text.append(item.GetSpeechResult().text);
    } else if (item.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
      text.append(item.GetText().text);
    } else if (item.GetType() == FOUNDRY_LOCAL_ITEM_MESSAGE) {
      for (const Item& part : item.GetMessage().parts) {
        if (part.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
          text.append(part.GetText().text);
        }
      }
    }
  }
  return text;
}

int main(int argc, char* argv[]) {
  if (argc != 2) {
    std::cerr << "Usage: tutorial-voice-to-text <audio-file>\n";
    return 1;
  }

  try {
    Configuration config("foundry_local_cpp_voice_to_text");
    Manager manager(std::move(config));

    // <transcription>
    auto speech_model = manager.GetCatalog().GetModel("whisper-tiny");
    if (!speech_model) {
      throw std::runtime_error("Model 'whisper-tiny' was not found in the catalog.");
    }
    DownloadIfNeeded(*speech_model, "speech");
    speech_model->Load();

    std::string transcript;
    {
      AudioSession session(*speech_model);
      Request request{Item::AudioFromUri(argv[1])};
      transcript = ResponseText(session.ProcessRequest(request));
    }
    speech_model->Unload();
    std::cout << "Transcription:\n" << transcript << "\n";
    // </transcription>

    // <summarization>
    auto chat_model = manager.GetCatalog().GetModel("qwen2.5-0.5b");
    if (!chat_model) {
      throw std::runtime_error("Model 'qwen2.5-0.5b' was not found in the catalog.");
    }
    DownloadIfNeeded(*chat_model, "chat");
    chat_model->Load();

    {
      ChatSession session(*chat_model);
      Request request{
          SystemMessage(
              "Turn the transcription into concise meeting notes with action items."),
          UserMessage(transcript),
      };
      request.SetOptions({
          .search = {.temperature = 0.2F, .max_output_tokens = 512, .seed = 42},
      });
      std::cout << "Summary:\n" << ResponseText(session.ProcessRequest(request)) << "\n";
    }
    chat_model->Unload();
    // </summarization>

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
