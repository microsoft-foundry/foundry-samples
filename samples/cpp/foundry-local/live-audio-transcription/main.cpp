// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <cstdint>
#include <exception>
#include <fstream>
#include <iostream>
#include <limits>
#include <stop_token>
#include <string>
#include <system_error>
#include <thread>
#include <vector>

#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#include <fcntl.h>
#include <io.h>
#else
#include <sys/select.h>
#include <unistd.h>
#endif

using namespace foundry_local;

std::streamsize ReadStdinChunk(
    std::stop_token stop_token, std::uint8_t* data, std::size_t size) {
  while (!stop_token.stop_requested()) {
#ifdef _WIN32
    const HANDLE stdin_handle = GetStdHandle(STD_INPUT_HANDLE);
    if (stdin_handle == INVALID_HANDLE_VALUE || stdin_handle == nullptr) {
      throw std::system_error(
          static_cast<int>(GetLastError()), std::system_category(), "Could not access stdin");
    }

    DWORD available = static_cast<DWORD>(
        std::min(size, static_cast<std::size_t>(std::numeric_limits<DWORD>::max())));
    const DWORD file_type = GetFileType(stdin_handle);
    if (file_type == FILE_TYPE_CHAR) {
      const DWORD wait_result = WaitForSingleObject(stdin_handle, 100);
      if (wait_result == WAIT_TIMEOUT) {
        continue;
      }
      if (wait_result != WAIT_OBJECT_0) {
        throw std::system_error(
            static_cast<int>(GetLastError()), std::system_category(), "Could not wait for stdin");
      }
    } else if (file_type == FILE_TYPE_PIPE) {
      if (!PeekNamedPipe(stdin_handle, nullptr, 0, nullptr, &available, nullptr)) {
        const DWORD error = GetLastError();
        if (error == ERROR_BROKEN_PIPE) {
          return 0;
        }
        throw std::system_error(
            static_cast<int>(error), std::system_category(), "Could not inspect stdin");
      }
      if (available == 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        continue;
      }
    }

    const auto read_size = static_cast<unsigned int>(std::min(
        static_cast<std::size_t>(available),
        static_cast<std::size_t>(std::numeric_limits<unsigned int>::max())));
    const int count = _read(_fileno(stdin), data, read_size);
#else
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(STDIN_FILENO, &read_fds);
    timeval timeout{0, 100000};
    const int ready = select(STDIN_FILENO + 1, &read_fds, nullptr, nullptr, &timeout);
    if (ready == 0) {
      continue;
    }
    if (ready < 0) {
      if (errno == EINTR) {
        continue;
      }
      throw std::system_error(errno, std::generic_category(), "Could not wait for stdin");
    }

    const ssize_t count = read(STDIN_FILENO, data, size);
#endif
    if (count < 0) {
      if (errno == EINTR) {
        continue;
      }
      throw std::system_error(errno, std::generic_category(), "Could not read stdin");
    }
    return static_cast<std::streamsize>(count);
  }

  return 0;
}

void StreamPcm(
    std::istream& input, bool uses_stdin, ItemQueue& queue, std::stop_token stop_token) {
  constexpr std::size_t kBytesPer100Milliseconds = 16000 * 2 / 10;
  std::vector<std::uint8_t> buffer(kBytesPer100Milliseconds);

  while (!stop_token.stop_requested()) {
    std::streamsize count = 0;
    if (uses_stdin) {
      count = ReadStdinChunk(stop_token, buffer.data(), buffer.size());
    } else {
      input.read(
          reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(buffer.size()));
      count = input.gcount();
    }
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
    const bool uses_stdin = std::string(argv[1]) == "-";
    if (uses_stdin) {
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

      std::exception_ptr producer_error;
      std::jthread producer([&](std::stop_token stop_token) {
        try {
          StreamPcm(*input, uses_stdin, audio_queue, stop_token);
        } catch (...) {
          producer_error = std::current_exception();
          if (!audio_queue.IsFinished()) {
            try {
              audio_queue.MarkFinished();
            } catch (const std::exception& cleanup_error) {
              std::cerr << "Could not finish the audio queue after a producer error: "
                        << cleanup_error.what() << "\n";
            } catch (...) {
              std::cerr << "Could not finish the audio queue after a producer error.\n";
            }
          }
        }
      });
      std::cout << "Transcription: ";
      Response response = session.ProcessRequest(request);
      producer.join();
      if (producer_error) {
        std::rethrow_exception(producer_error);
      }
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
