# MaaS Fine-tuning Templates

This directory contains starter templates for submitting Models as a Service (MaaS) fine-tuning jobs using the Azure Developer CLI (azd) fine-tuning extension.

When you run `azd ai finetuning init` with template flag, these templates are pulled locally to provide sample configurations for your fine-tuning jobs:

```bash
azd ai finetuning init -t <template-url>
```

## Templates

| Template | Link | Description |
|----------|------|-------------|
| Supervised Fine-tuning | [supervised](supervised) | Standard supervised fine-tuning with training and validation datasets. |
| Direct Preference Optimization (DPO) | [direct_preference_optimization](direct_preference_optimization) | Fine-tuning using preference data to align model outputs. |
| Reinforcement Fine-tuning | [reinforcement](reinforcement) | Reinforcement learning-based fine-tuning approach. |

## Template Configurations

### Supervised Fine-tuning
- [sample_finetuning_supervised.yaml](supervised/sample_finetuning_supervised.yaml) - Fine-tune GPT-4o-mini with custom training data
- [sample_finetuning_oss_supervised.yaml](supervised/sample_finetuning_oss_supervised.yaml) - Fine-tune OSS Ministral 3B model

### Direct Preference Optimization (DPO)
- [sample_finetuning_dpo.yaml](direct_preference_optimization/sample_finetuning_dpo.yaml) - Fine-tune using preference pairs

### Reinforcement Fine-tuning
- [sample_finetuning_rft.yaml](reinforcement/sample_finetuning_rft.yaml) - Reinforcement learning-based fine-tuning
