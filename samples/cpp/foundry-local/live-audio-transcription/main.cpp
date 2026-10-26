// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

using namespace foundry_local;

void StreamPcm(std::istream& input, ItemQueue& queue) {
  constexpr std::size_t kBytesPer100Milliseconds = 16000 * 2 / 10;
  std::vector<std::uint8_t> buffer(kBytesPer100Milliseconds);

  while (input) {
    input.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(buffer.size()));
    const auto count = input.gcount();
    if (count <= 0) {
      break;
    }
    const auto size = static_cast<std::size_t>(count);
    auto* owned_chunk = new std::uint8_t[size];
    std::memcpy(owned_chunk, buffer.data(), size);
    queue.Push(Item::Bytes(
        FOUNDRY_LOCAL_ITEM_BYTES, owned_chunk, size,
        [](const flBytesData* data) {
          delete[] static_cast<std::uint8_t*>(data->mutable_data);
        }));
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  queue.MarkFinished();
}

int main(int argc, char* argv[]) {
  if (argc != 2) {
    std::cerr << "Usage: live-audio-transcription <raw-16khz-s16le-mono-pcm-file|->\n"
              << "Use '-' to read PCM from standard input. Microphone capture must be supplied "
                 "by a platform audio tool.\n";
    return 1;
  }

  try {
    Configuration config("foundry_local_cpp_live_audio");
    Manager manager(std::move(config));
    auto model = manager.GetCatalog().GetModel("nemotron-speech-streaming-en-0.6b");
    if (!model) {
      throw std::runtime_error(
          "Streaming speech model unavailable; support depends on platform and hardware.");
    }

    if (!model->IsCached()) {
      model->Download([](float progress) {
        std::cout << "\rDownloading model: " << static_cast<int>(progress) << "%" << std::flush;
        return 0;
      });
      std::cout << "\n";
    }
    model->Load();

    std::ifstream file;
    std::istream* input = &std::cin;
    if (std::string(argv[1]) == "-") {
#ifdef _WIN32
      if (_setmode(_fileno(stdin), _O_BINARY) == -1) {
        throw std::runtime_error("Could not switch standard input to binary mode.");
      }
#endif
    } else {
      file.open(argv[1], std::ios::binary);
      if (!file) {
        throw std::runtime_error("Could not open PCM input file.");
      }
      input = &file;
    }

    {
      AudioSession session(*model);
      session.SetStreamingCallback([](Item item) {
        if (item.GetType() == FOUNDRY_LOCAL_ITEM_SPEECH_SEGMENT) {
          const auto segment = item.GetSpeechSegment();
          std::cout.write(segment.text.data(), static_cast<std::streamsize>(segment.text.size()));
          std::cout.flush();
        }
        return 0;
      });

      ItemQueue audio_queue;
      Request request;
      request.AddItem(Item::AudioFromData("pcm", nullptr, 0, 16000, 1));
      request.AddItem(audio_queue, false);

      std::thread producer([&] { StreamPcm(*input, audio_queue); });
      std::cout << "Transcription: ";
      Response response = session.ProcessRequest(request);
      producer.join();
      std::cout << "\n";

      for (const Item& item : response.GetItems()) {
        if (item.GetType() == FOUNDRY_LOCAL_ITEM_SPEECH_RESULT) {
          std::cout << "Final transcript: " << item.GetSpeechResult().text << "\n";
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
