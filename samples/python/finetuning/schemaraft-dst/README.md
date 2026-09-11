# SchemaRAFT — Deployment-Faithful Schema Evaluation for Dialogue State Tracking

Schema-guided dialogue state tracking (DST) is almost always evaluated with the
**correct service schema already in the prompt**. A deployed assistant does not
get that. It retrieves candidate schemas from a registry, and the prompt ends up
holding the right schema *plus* whatever else the retriever dragged in.

This sample changes exactly one thing — how schemas reach the prompt — and
measures what that costs. On SGD, the same `gpt-4.1-mini` deployment scores
**58.0 JGA** with the gold schema and **18.3 JGA** under retrieval with
distractors.

The collapse is **not** a retrieval miss. On the subset of turns where the gold
schema demonstrably *was* in the prompt, the base model still only reaches
**24.0 JGA**. Better retrieval cannot fix that number.

The sample then ships **SchemaRAFT**, the fine-tuning recipe that closes most of
the gap (18.3 → 45.0) by building every training prompt the way the serving
prompt gets built.

Everything runs on the public [Schema-Guided Dialogue][sgd] dataset (CC BY-SA 4.0).

[sgd]: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

---

## What's in here

| Path | What it does |
|---|---|
| `download_sgd.py` | Fetches SGD. Retrieval at test time runs over the 21-service test registry; SGD defines 45 services / 20 domains overall. |
| `sgd_data.py` | Loads dialogues into DST turns and serialises schemas. Single source of truth for both eval and training. |
| `schema_retriever.py` | BM25 over the registry, plus distractor sampling. Pure standard library. |
| `build_prompts.py` | The four schema-delivery modes, the response parser, and the metrics. |
| `foundry_client.py` | Keyless Microsoft Foundry client via `DefaultAzureCredential`. |
| `eval_jga.py` | Runs an evaluation and reports Joint Goal Accuracy. `--mode` is the experiment. |
| `goldpresent_strata.py` | Splits results by whether the gold schema was in the prompt. **This is the step that carries the argument.** |
| `build_sft_data.py` | Emits the SchemaRAFT training file. |
| `submit_finetune.py` | Submits and monitors the fine-tuning job. |
| `selftest.py` | 42 offline checks over bundled fixtures. No Azure calls, no tokens. |

The four modes in `build_prompts.py` are the whole experiment:

| `--mode` | What the model sees | What it measures |
|---|---|---|
| `none` | no schema | how much the model is running on memorised slot names |
| `oracle` | the one correct schema | the number papers report |
| `retrieved` | BM25 top-*k* | retrieval quality alone |
| `retrieved_distractor` | BM25 top-1 + *n* random schemas | **what your users get** |

---

## Prerequisites

### 1. Access to Microsoft Foundry

You need an Azure subscription and a **Microsoft Foundry** resource with a chat
model deployment. If you have never used Foundry:

1. Sign in at [ai.azure.com](https://ai.azure.com) with an Azure account and
   make sure the **New Foundry** toggle is on. A
   [free account](https://azure.microsoft.com/free/) is enough for steps 1-4.
2. Create a project. The portal creates the underlying Foundry resource for you.
   Walkthrough: [Create a project][doc-project].
3. Deploy a small chat model - `gpt-4.1-mini` is what the numbers below use.
   Walkthrough: [Deploy a model][doc-deploy]. Note the **deployment name**; that
   is what `--deployment` wants, not the model name.
4. Copy the endpoint into `AOAI_ENDPOINT`. In the portal it sits on the project
   **Home** page next to the API key; ignore the key, this sample uses Microsoft
   Entra ID. Either `https://<resource>.services.ai.azure.com` or
   `https://<resource>.openai.azure.com` works - the code appends `/openai/v1`.
5. Model availability is regional, and each deployment draws on a
   tokens-per-minute quota. Check [models and regions][doc-region] and
   [quotas and limits][doc-quota] before you pick one.
6. Fine-tuning (step 5 only) runs on a subset of models and regions, and only on
   a resource's **default project** - see [fine-tuning][doc-ft]. Steps 1-4 need
   no fine-tuning.

[doc-project]: https://learn.microsoft.com/azure/foundry/how-to/create-projects
[doc-deploy]: https://learn.microsoft.com/azure/foundry/foundry-models/how-to/deploy-foundry-models
[doc-region]: https://learn.microsoft.com/azure/foundry/concepts/models-sold-directly-by-azure
[doc-quota]: https://learn.microsoft.com/azure/foundry/foundry-models/quotas-limits
[doc-ft]: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/fine-tuning

### 2. Permissions

This sample is **keyless**. It authenticates with `DefaultAzureCredential`, so
no API key is ever written to disk. That means your identity needs a role, not a
secret.

| To do this | Role on the Foundry resource | Role definition ID |
|---|---|---|
| Steps 2-4 (inference only) | **Foundry User** | `53ca6127-db72-4b80-b1b0-d745d6d5456d` |
| Step 5 (fine-tune and deploy) | **Foundry Owner** | `c883944f-8b7b-4483-af10-35834be79c4a` |

Fine-tuning needs both data-plane and control-plane permissions, and **Foundry
Owner** is the only built-in role that carries both. If you would rather not
grant it, **Foundry User** plus **Foundry Account Owner**
(`e47c6f54-e4a2-4754-9501-8e0985b135e1`) is the equivalent pair.

Two things that trip people up:

- **Do not use the `Cognitive Services *` roles**, or `Azure AI Developer`, for
  this. They target AI Services resources directly and do not apply to Foundry
  projects. See [role-based access control for Microsoft Foundry][doc-rbac].
- Being subscription **Owner** does not imply data-plane access. The role has to
  be assigned explicitly at the Foundry resource or project scope.

These roles were renamed recently (**Foundry User** was *Azure AI User*, and so
on). Pass the **role definition ID** rather than the display name while the
rename rolls out:

```bash
az role assignment create \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --assignee "<your-user-principal-name>" \
  --assignee-principal-type User \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-resource>"
```

If your organisation blocks keyless access, that is a policy question for your
admin — this sample has no API-key fallback by design.

[doc-rbac]: https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry

### 3. Local setup

```bash
python -m pip install -r requirements.txt
cp .env.example .env          # set AOAI_ENDPOINT and DEPLOYMENT
az login                      # DefaultAzureCredential picks this up
```

Requires Python 3.10+ and the [Azure CLI][doc-cli]. The only dependencies are
`openai` and `azure-identity` — BM25, the SGD download, and the metrics are all
standard library.

If you belong to more than one tenant, add `--tenant <tenant-id>` to `az login`.
Otherwise `DefaultAzureCredential` uses whichever tenant the CLI defaulted to,
and you get a 401 that looks like a role problem but is not.

[doc-cli]: https://learn.microsoft.com/cli/azure/install-azure-cli

### Troubleshooting

| Symptom | Most likely cause |
|---|---|
| `401 Unauthorized` | `az login` session is on the wrong tenant, or a fresh role assignment has not propagated yet. |
| `403 Forbidden` | Identity has no **Foundry User** role at the resource or project scope. Subscription Owner is not enough. |
| `404 DeploymentNotFound` | `--deployment` was given the model name instead of the deployment name. |
| `429` on most calls | The deployment's tokens-per-minute quota is too low. Lower `--concurrency` or raise the quota. |
| Endpoint rejected at startup | `AOAI_ENDPOINT` must be an `https://` URL. Do not append `/openai/v1` yourself. |

---

## Runbook

Steps 1–4 take roughly 20 minutes and cost only inference tokens on ~400 turns.
Step 5 is optional and is the only part that costs real money.

### Step 0 — Confirm the checkout works (offline, free)

```bash
python selftest.py
```

40 checks over bundled fixtures: retrieval ranking, all four prompt modes, seed
determinism, the JSON parser, JGA scoring, the training-data builder, and the
stratification maths. No network, no Azure. If this fails, the problem is your
checkout, not your deployment.

### Step 1 — Get the data

```bash
python download_sgd.py --splits test          # enough for steps 2-4
python download_sgd.py --splits train test    # add this before step 5
```

### Step 2 — The number papers report

The gold schema is placed directly in the prompt.

```bash
python eval_jga.py --mode oracle \
    --deployment <your-deployment> --n 200 \
    --output-dir results/oracle
```

### Step 3 — The number your users get

One flag changes. `retrieved_distractor` retrieves BM25 top-1 and adds two
random schemas from the registry, shuffled — the shape of a real serving prompt.

```bash
python eval_jga.py --mode retrieved_distractor \
    --deployment <your-deployment> --n 200 \
    --n-schemas 1 --n-distractors 2 \
    --output-dir results/retdist
```

Compare `results/*/summary.json`. On `gpt-4.1-mini` this is roughly **58 vs 18**.

Same turns, same order, same prompt template, same metric, same weights. Runs
are reproducible from `--seed` alone.

### Step 4 — Prove it is not a retrieval problem

This is the step that matters.

```bash
python goldpresent_strata.py --results results/retdist
```

It splits the turns into those where the correct schema really was in the prompt
and those where it was not, and reports JGA on each. Read it this way:

- Low JGA where the gold schema was **absent** is expected and uninteresting.
  The model was never shown the answer.
- Low JGA where the gold schema was **present** is the finding. The correct
  schema was sitting in the context and the model still got the turn wrong. No
  amount of retrieval tuning fixes that.
- The abstention rate on the gold-absent stratum tells you whether the model
  degrades safely. Emitting `{}` is correct there; inventing slots from a
  distractor schema is not.

We call the gap between the oracle number and the gold-present number
**schema-following collapse**.

### Step 5 — The fix: train on the noise (optional, costs money)

SchemaRAFT is [RAFT][raft] applied to retrieved *schemas* instead of retrieved
*documents*. Build the training data so it looks like the deployment prompt:

- 1 correct schema + 2 random distractors per example, shuffled, exactly as at
  serving time
- **20% of examples omit the correct schema entirely and are labelled `{}`.**
  That fraction is what teaches the model to abstain instead of guessing. Set it
  to zero and the model learns that some schema in the prompt is always right —
  which is the habit that breaks in production.

```bash
python build_sft_data.py --split train \
    --n-distractors 2 --gold-absent-frac 0.2 \
    --out data/schemaraft_train.jsonl

python submit_finetune.py --train-file data/schemaraft_train.jsonl --epochs 3
```

Deploy the resulting model in the Foundry portal, then re-run step 3 against the
new deployment name and compare.

> **Cost.** The full train split yields ~19,300 examples (~124M training tokens
> over 3 epochs). Budget on the order of $150 plus several hours of queue time,
> and check current [fine-tuning pricing][doc-price] first. Use
> `--max-dialogues 2000` for a cheap smoke run. Steps 1–4 cost only inference.

[raft]: https://arxiv.org/abs/2403.10131
[doc-price]: https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/

---

## Reported results

SGD test, n=1,810 turns, `gpt-4.1-mini` unless noted.

| Condition | JGA |
|---|---:|
| No schema in prompt | 2.0 |
| Retrieval + distractors, base | 18.3 |
| **Retrieval + distractors, SchemaRAFT** | **45.0** |
| Retrieved top-3, base | 55.6 |
| Oracle gold schema, base | 58.0 |

Gold-in-prompt stratum: base **24.0** → SchemaRAFT **62.7**. This stratum is
every turn where the gold schema reached the prompt — whether BM25 ranked it
top-1 or a distractor draw happened to surface it — which is exactly what
`goldpresent_strata.py` reports.

Prompting does not substitute for this. A frontier reasoning model, prompted,
reaches 16.6 JGA on the same turns at roughly 4.4 s and 24x the per-turn cost;
the fine-tuned small model reaches 45.0 at roughly 1.1 s and 1.0x.

Your absolute numbers will differ with model version, region, and sampling. The
**gap between step 2 and step 3** is the reproducible part.

---

## When this will not reproduce

The gap needs schemas that are genuinely **confusable**. SGD defines 45 services
across 20 domains with heavily overlapping slot names — the slot `city` alone
appears in 9 of them, and 15 services carry some `*city*` variant. If the schemas
in your own registry are clearly distinguishable, a model that retrieves the
wrong one tends to notice, and the collapse is much smaller.

Run steps 2–4 against your own registry before deciding to fine-tune.

---

## License

Code: MIT, per the repository root. The SGD dataset is downloaded at runtime
from Google Research under CC BY-SA 4.0; it is not redistributed here.
