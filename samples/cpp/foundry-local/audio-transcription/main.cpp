// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>

using namespace foundry_local;

void DownloadIfNeeded(IModel& model) {
  if (model.IsCached()) {
    std::cout << "Using cached model " << model.GetInfo().Id() << ".\n";
    return;
  }

  model.Download([](float progress) {
    std::cout << "\rDownloading model: " << static_cast<int>(progress) << "%" << std::flush;
    return 0;
  });
  std::cout << "\n";
}

void PrintTranscript(const Response& response) {
  for (const Item& item : response.GetItems()) {
    if (item.GetType() == FOUNDRY_LOCAL_ITEM_SPEECH_RESULT) {
      std::cout << item.GetSpeechResult().text << "\n";
    } else if (item.GetType() == FOUNDRY_LOCAL_ITEM_TEXT) {
      std::cout << item.GetText().text << "\n";
    }
  }
}

int main(int argc, char* argv[]) {
  if (argc != 2) {
    std::cerr << "Usage: audio-transcription <audio-file>\n";
    return 1;
  }

  try {
    Configuration config("foundry_local_cpp_audio_transcription");
    if (const char* cache_dir = std::getenv("FOUNDRY_LOCAL_SAMPLE_CACHE_DIR")) {
      config.SetModelCacheDir(cache_dir);
    }
    Manager manager(std::move(config));

    auto model = manager.GetCatalog().GetModel("whisper-tiny");
    if (!model) {
      throw std::runtime_error("Model 'whisper-tiny' was not found in the catalog.");
    }

    DownloadIfNeeded(*model);
    model->Load();

    {
      AudioSession session(*model);
      Request request{Item::AudioFromUri(argv[1])};
      Response response = session.ProcessRequest(request);
      std::cout << "Transcription:\n";
      PrintTranscript(response);
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
