# Screen a model for extraction fine-tuning (text-only ExtractBench)

Build a text-only structured-extraction dataset from the public
[ExtractBench](https://huggingface.co/datasets/llamaindex/ExtractBench) corpus,
then measure whether a model has anything wrong with it that fine-tuning could
repair — before you pay for a training run.

The measurement is three zero-shot columns:

| column | question it answers |
| --- | --- |
| `refusal` | did the model decline to attempt the document at all? |
| `valid_json` | did the response parse as a single JSON value? |
| `coverage` | how much of the expected leaf volume did it emit? |

In the study this sample accompanies, reinforcement fine-tuning moved the models
that failed these columns and barely moved the ones that did not. The gain
tracked the number of broken columns, not model size. All three are measurable
in one pass on an untouched model, so the decision can be made up front.

This sample ships the **data preparation and the evaluation**. It does not ship
a training loop — see [What this does not include](#what-this-does-not-include).

## Files

| file | purpose |
| --- | --- |
| `prepare_data.py` | Download ExtractBench, select a difficulty band, extract the text layer, split into schema-disjoint train and test. |
| `grader.py` | Leaf-multiset F-beta plus the behaviour columns. Standard library only. |
| `evaluate.py` | Run a model over a split and print the screen. |
| `selftest.py` | Offline checks. No network, no credentials. |

## Prerequisites

- Python 3.10+
- An OpenAI-compatible endpoint. For Microsoft Foundry, set `AOAI_ENDPOINT` and
  sign in with `az login`; auth is `DefaultAzureCredential`, and there is no
  API-key path in this sample.
- Disk space for the selected PDFs. Only the documents that survive the filters
  are downloaded; the full corpus is much larger and is never fetched.

```bash
pip install -r requirements.txt
python selftest.py          # offline, should print SELFTEST PASS
```

## 1. Build the dataset

```bash
python prepare_data.py prepare --out data/band.jsonl
```

This pulls the corpus metadata, keeps the documents in the difficulty band, then
downloads and text-extracts only those PDFs. Add `--limit 12` for a cheap first
run that stops early instead of fetching the whole band.

Two filters decide what survives, and both matter:

- **Perception-tagged documents are dropped.** Their answers are not in the text
  layer at all. Scoring a text-only model on them measures the PDF extractor.
- **Leaf count between 200 and 3000.** Leaf count — the number of scalar values
  in the gold answer — is the difficulty axis here, not page count. Below ~200
  leaves most current models are already near ceiling and there is nothing to
  measure. Above ~3000 the answer does not fit in one response, and no amount of
  fine-tuning fixes an output budget.

Then split. Schemas, not documents, are the unit: a shared schema is the
strongest leak available, because half the answer is the shape of the answer.
The split is a seeded shuffle that never looks at how any model scores, so the
defects the test set exists to expose are not quietly routed into training.

```bash
python prepare_data.py split --source data/band.jsonl
# -> data/band_train.jsonl, data/band_test.jsonl
```

Test deliberately gets the larger share. Reinforcement fine-tuning draws several
rollouts per training document, so training documents get reused and evaluation
documents do not; the test set is the scarce resource.

If you are targeting a model with a fixed context window, add the envelope pass
so documents that cannot fit are excluded up front rather than failing mid-run:

```bash
pip install transformers
python prepare_data.py prepare --out data/band.jsonl \
  --tokenizer openai/gpt-oss-20b --context 32768 --max-output-tokens 15360
```

## 2. Screen a model

```bash
export AOAI_ENDPOINT="https://<your-resource>.openai.azure.com"
python evaluate.py --model <your-deployment> --data data/band_test.jsonl --repeats 4
```

It prints each metric as a mean and a standard deviation across passes, marks
the three screen columns `ok` or `BROKEN`, and ends with a count of broken
behaviours and the room left (`1 - f1`).

For a worked example, `gpt-oss-20b` measured on this band, untouched, four
passes at temperature 0:

| f1 | refusal | valid_json | coverage | verdict |
| ---: | ---: | ---: | ---: | --- |
| 0.438 | 0.250 | 0.638 | 0.471 | 3 of 3 broken |

That is a model abandoning the task. A quarter of its responses are an apology,
a third of the rest are not parseable, and what it does return covers under half
the expected values. Fine-tuning has something concrete to repair, and in the
study it recovered about two thirds of the room left.

Your numbers will not match these to three decimals — they depend on which
documents land in your test split, and absolute scores are not comparable across
different splits. The verdict is what transfers.

A model that scores `0 of 3` is the opposite case. Its remaining error is
capability, not behaviour, and in this study fine-tuning against this metric
returned nothing on every such model tested. That is a useful answer: it saves
the run.

### Reading it honestly

- **Use `--repeats 4` or more.** Temperature 0 is not deterministic on
  mixture-of-experts serving stacks. Single passes on this benchmark have
  differed by more than 0.10 f1 — larger than most effects worth chasing. The
  reported `sd` is across passes and tells you whether a difference is real.
- **A column within 0.05 of its threshold is a judgement call.** `evaluate.py`
  labels those `borderline`. Do not let a threshold decide something the
  measurement cannot.
- **`--max-tokens` has to be generous.** Gold answers here run to thousands of
  tokens, and a response cut off mid-object is not valid JSON. Too small a budget
  reports a capable model as unable to produce JSON at all.
- **Compare only within this harness.** These scores come from a difficulty-
  controlled subset, scored by this prompt, this parser and this metric, on text
  only. They are not comparable to full-benchmark ExtractBench scores published
  elsewhere, in either direction, and a gap between them is not a result.

## How the score works

`grader.py` flattens both the prediction and the gold answer to a multiset of
`(path, value)` leaves and takes an F-measure over the overlap.

Flattening is what makes partial credit meaningful. A model returning 38 of 40
line items should score near one that returns all 40, and a model returning an
apology should score zero; tree equality cannot express that, and per-field
accuracy assumes both sides have the same fields. List membership is recorded as
`[]` rather than an index, so records match as a bag — these documents have no
reliable row ordering.

One property worth knowing before you use the score as a training reward: under
F1, against 100 expected leaves, omitting 10 scores 0.947 while attempting 10 and
getting them wrong scores 0.900. F1 pays a model to stop early, which is the
behaviour this benchmark exists to detect. `grade(..., beta=2)` narrows that gap.
Reported numbers here use `beta=1`.

## What this does not include

No training loop. The study behind this sample trained with the Microsoft Foundry
Interactive Post-Training API, which is in private preview; the dataset this
sample produces is in the chat format those jobs take, but the training code is
not reproducible outside the preview and is therefore not shipped here.

No processed data either — only the code that builds it. The corpus belongs to
its authors, and a rebuild script keeps the document selection auditable rather
than asking you to trust a checked-in file.

## Background

The thresholds and the worked example come from a difficulty-controlled study of
reinforcement fine-tuning on this task across five models, published on the
Microsoft Foundry blog.

ExtractBench is published by LlamaIndex under its own license; this sample
downloads it at runtime and redistributes none of it.
