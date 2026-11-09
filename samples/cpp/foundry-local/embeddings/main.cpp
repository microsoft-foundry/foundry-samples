// <complete_code>
#include <foundry_local/foundry_local_cpp.h>

#include <cmath>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using namespace foundry_local;

float CosineSimilarity(const std::vector<float>& left, const std::vector<float>& right) {
  float dot = 0.0F;
  float left_norm = 0.0F;
  float right_norm = 0.0F;
  for (std::size_t index = 0; index < left.size(); ++index) {
    dot += left[index] * right[index];
    left_norm += left[index] * left[index];
    right_norm += right[index] * right[index];
  }
  return dot / (std::sqrt(left_norm) * std::sqrt(right_norm));
}

int main() {
  try {
    Configuration config("foundry_local_cpp_embeddings");
    Manager manager(std::move(config));
    auto& catalog = manager.GetCatalog();

    std::unique_ptr<IModel> model;
    for (const auto& catalog_model : catalog.GetModels()) {
      if (catalog_model->GetInfo().Task() == "embeddings") {
        model = catalog.GetModel(std::string(catalog_model->GetInfo().Alias()));
        break;
      }
    }
    if (!model) {
      throw std::runtime_error("No embeddings model was found in the catalog.");
    }

    for (const auto& variant : model->GetVariants()) {
      if (variant->GetInfo().DeviceType() == FOUNDRY_LOCAL_DEVICE_CPU) {
        model->SelectVariant(*variant);
        break;
      }
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
      EmbeddingsSession session(*model);

      const auto single = session.Embed("The quick brown fox jumps over the lazy dog.");
      std::cout << "Single embedding dimensions: " << single.size() << "\n";

      const std::vector<std::string> inputs{
          "The cat sat on the mat.",
          "A kitten rested on the rug.",
          "The stock market moved sharply.",
      };
      const auto batch = session.Embed(inputs);
      std::cout << "Batch count: " << batch.size() << "\n";
      std::cout << "Related-sentence similarity: "
                << CosineSimilarity(batch.at(0), batch.at(1)) << "\n";
      std::cout << "Unrelated-sentence similarity: "
                << CosineSimilarity(batch.at(0), batch.at(2)) << "\n";
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
