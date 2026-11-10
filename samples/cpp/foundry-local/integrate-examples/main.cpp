// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <cstdlib>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

using namespace foundry_local;

namespace {

#ifdef _WIN32
using SocketHandle = SOCKET;
constexpr SocketHandle kInvalidSocket = INVALID_SOCKET;
#else
using SocketHandle = int;
constexpr SocketHandle kInvalidSocket = -1;
#endif

class SocketRuntime {
 public:
  SocketRuntime() {
#ifdef _WIN32
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
      throw std::runtime_error("WSAStartup failed.");
    }
#endif
  }

  ~SocketRuntime() {
#ifdef _WIN32
    WSACleanup();
#endif
  }
};

class Socket {
 public:
  explicit Socket(SocketHandle handle) : handle_(handle) {}
  ~Socket() {
    if (handle_ == kInvalidSocket) {
      return;
    }
#ifdef _WIN32
    closesocket(handle_);
#else
    close(handle_);
#endif
  }

  Socket(const Socket&) = delete;
  Socket& operator=(const Socket&) = delete;
  Socket(Socket&&) = delete;
  Socket& operator=(Socket&&) = delete;

  SocketHandle Get() const { return handle_; }

 private:
  SocketHandle handle_;
};

struct HttpEndpoint {
  std::string host;
  std::string port;
  std::string base_path;
};

HttpEndpoint ParseHttpEndpoint(std::string endpoint) {
  constexpr std::string_view prefix = "http://";
  if (!endpoint.starts_with(prefix)) {
    throw std::runtime_error("The built-in service returned a non-HTTP endpoint: " + endpoint);
  }

  endpoint.erase(0, prefix.size());
  const auto path_start = endpoint.find('/');
  std::string authority = endpoint.substr(0, path_start);
  std::string base_path = path_start == std::string::npos ? "" : endpoint.substr(path_start);
  while (!base_path.empty() && base_path.back() == '/') {
    base_path.pop_back();
  }

  std::string host;
  std::string port;
  if (!authority.empty() && authority.front() == '[') {
    const auto closing_bracket = authority.find(']');
    if (closing_bracket == std::string::npos ||
        closing_bracket + 2 > authority.size() ||
        authority[closing_bracket + 1] != ':') {
      throw std::runtime_error("Could not parse the service endpoint: " + authority);
    }
    host = authority.substr(1, closing_bracket - 1);
    port = authority.substr(closing_bracket + 2);
  } else {
    const auto colon = authority.rfind(':');
    if (colon == std::string::npos) {
      throw std::runtime_error("The service endpoint did not include a port: " + authority);
    }
    host = authority.substr(0, colon);
    port = authority.substr(colon + 1);
  }

  return {std::move(host), std::move(port), std::move(base_path)};
}

std::string JsonEscape(std::string_view value) {
  std::string escaped;
  escaped.reserve(value.size());
  for (const char character : value) {
    switch (character) {
      case '\\':
        escaped += "\\\\";
        break;
      case '"':
        escaped += "\\\"";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        escaped += character;
        break;
    }
  }
  return escaped;
}

Socket Connect(const HttpEndpoint& endpoint) {
  addrinfo hints{};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_protocol = IPPROTO_TCP;

  addrinfo* results = nullptr;
  if (getaddrinfo(endpoint.host.c_str(), endpoint.port.c_str(), &hints, &results) != 0) {
    throw std::runtime_error("Could not resolve the local service endpoint.");
  }

  SocketHandle connected = kInvalidSocket;
  for (addrinfo* address = results; address != nullptr; address = address->ai_next) {
    SocketHandle candidate =
        socket(address->ai_family, address->ai_socktype, address->ai_protocol);
    if (candidate == kInvalidSocket) {
      continue;
    }
    if (connect(candidate, address->ai_addr, static_cast<int>(address->ai_addrlen)) == 0) {
      connected = candidate;
      break;
    }
#ifdef _WIN32
    closesocket(candidate);
#else
    close(candidate);
#endif
  }
  freeaddrinfo(results);

  if (connected == kInvalidSocket) {
    throw std::runtime_error("Could not connect to the local Foundry service.");
  }
  return Socket(connected);
}

void SendAll(SocketHandle socket_handle, const std::string& request) {
  std::size_t sent = 0;
  while (sent < request.size()) {
    const auto remaining = request.size() - sent;
#ifdef _WIN32
    const int result =
        send(socket_handle, request.data() + sent, static_cast<int>(remaining), 0);
#else
    const auto result = send(socket_handle, request.data() + sent, remaining, 0);
#endif
    if (result <= 0) {
      throw std::runtime_error("Sending the HTTP request failed.");
    }
    sent += static_cast<std::size_t>(result);
  }
}

std::string ReceiveAll(SocketHandle socket_handle) {
  std::string response;
  char buffer[8192];
  while (true) {
#ifdef _WIN32
    const int received = recv(socket_handle, buffer, static_cast<int>(sizeof(buffer)), 0);
#else
    const auto received = recv(socket_handle, buffer, sizeof(buffer), 0);
#endif
    if (received == 0) {
      break;
    }
    if (received < 0) {
      throw std::runtime_error("Reading the HTTP response failed.");
    }
    response.append(buffer, static_cast<std::size_t>(received));
  }
  return response;
}

std::string PostChatCompletion(
    const std::string& endpoint,
    std::string_view model_id,
    std::string_view prompt) {
  SocketRuntime socket_runtime;
  const HttpEndpoint parsed = ParseHttpEndpoint(endpoint);
  Socket connection = Connect(parsed);

  const std::string body =
      "{\"model\":\"" + JsonEscape(model_id) +
      "\",\"messages\":[{\"role\":\"user\",\"content\":\"" +
      JsonEscape(prompt) + "\"}],\"stream\":false}";
  const std::string path = parsed.base_path + "/v1/chat/completions";

  std::ostringstream request;
  request << "POST " << path << " HTTP/1.1\r\n"
          << "Host: " << parsed.host << ":" << parsed.port << "\r\n"
          << "Content-Type: application/json\r\n"
          << "Accept: application/json\r\n"
          << "Connection: close\r\n"
          << "Content-Length: " << body.size() << "\r\n\r\n"
          << body;
  SendAll(connection.Get(), request.str());

  const std::string response = ReceiveAll(connection.Get());
  const auto headers_end = response.find("\r\n\r\n");
  if (headers_end == std::string::npos) {
    throw std::runtime_error("The local service returned an invalid HTTP response.");
  }

  const auto status_end = response.find("\r\n");
  const std::string status_line = response.substr(0, status_end);
  if (status_line.find(" 200 ") == std::string::npos) {
    throw std::runtime_error(
        "The local service returned " + status_line + ":\n" +
        response.substr(headers_end + 4));
  }
  return response.substr(headers_end + 4);
}

std::unique_ptr<IModel> SelectCpuChatModel(ICatalog& catalog) {
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

class WebServiceGuard {
 public:
  explicit WebServiceGuard(Manager& manager) : manager_(manager) {
    manager_.StartWebService();
  }

  ~WebServiceGuard() {
    if (active_) {
      try {
        manager_.StopWebService();
      } catch (...) {
      }
    }
  }

  WebServiceGuard(const WebServiceGuard&) = delete;
  WebServiceGuard& operator=(const WebServiceGuard&) = delete;

  void Stop() {
    if (active_) {
      manager_.StopWebService();
      active_ = false;
    }
  }

 private:
  Manager& manager_;
  bool active_ = true;
};

}  // namespace

int main(int argc, char* argv[]) {
  try {
    Configuration config("foundry_local_cpp_integrate_examples");
    if (const char* cache_dir = std::getenv("FOUNDRY_LOCAL_SAMPLE_CACHE_DIR")) {
      config.SetModelCacheDir(cache_dir);
    }
    Manager manager(std::move(config));

    const auto providers = manager.GetDiscoverableEps();
    std::cout << "Discoverable execution providers:\n";
    std::vector<std::string> missing_providers;
    for (const auto& provider : providers) {
      std::cout << "  " << provider.name
                << (provider.is_registered ? " [registered]" : " [not registered]") << "\n";
      if (!provider.is_registered) {
        missing_providers.push_back(provider.name);
      }
    }

    if (argc > 1 && std::string(argv[1]) == "--download-eps" && !missing_providers.empty()) {
      manager.DownloadAndRegisterEps(
          missing_providers, [](std::string_view name, float progress) {
            std::cout << "\r" << name << ": " << static_cast<int>(progress) << "%"
                      << std::flush;
            return true;
          });
      std::cout << "\n";
    }

    auto model = SelectCpuChatModel(manager.GetCatalog());
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
      WebServiceGuard web_service(manager);
      const auto endpoints = manager.GetWebServiceEndpoints();
      if (endpoints.empty()) {
        throw std::runtime_error("The built-in web service did not report a bound endpoint.");
      }

      const std::string endpoint = endpoints.front();
      std::cout << "Foundry Local web service: " << endpoint << "\n";
      std::cout << "OpenAI-compatible response:\n"
                << PostChatCompletion(
                       endpoint,
                       model->GetInfo().Id(),
                       "Give one benefit of running an AI model locally.")
                << "\n";
      web_service.Stop();
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
