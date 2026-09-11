"""BM25 retrieval over the schema registry, plus distractor sampling.

BM25 is implemented inline rather than pulled from a package so the exact
ranking function is auditable and the sample has one less dependency. Character
n-grams beat word tokens here because SGD slot names run together
(``restaurant_name`` vs ``restaurant name``) and the query is raw dialogue text.
"""
from __future__ import annotations

import math
import random
from collections import Counter

from sgd_data import schema_to_text


def char_ngram_tokenize(text: str, lo: int = 3, hi: int = 5) -> list[str]:
    text = text.lower()
    toks: list[str] = []
    n_chars = len(text)
    for n in range(lo, hi + 1):
        if n_chars < n:
            break
        toks.extend(text[i : i + n] for i in range(n_chars - n + 1))
    return toks


class BM25Okapi:
    def __init__(
        self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75
    ):
        self.k1, self.b = k1, b
        self.n_docs = len(corpus_tokens)
        self.doc_len = [len(d) for d in corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        self.doc_freqs = [Counter(d) for d in corpus_tokens]
        df: Counter = Counter()
        for freqs in self.doc_freqs:
            df.update(freqs.keys())
        self.idf = {
            term: math.log(1.0 + (self.n_docs - n + 0.5) / (n + 0.5))
            for term, n in df.items()
        }

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.n_docs
        if self.avgdl == 0.0:
            return scores
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                f = freqs.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (
                    1 - self.b + self.b * self.doc_len[i] / self.avgdl
                )
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        return scores


class SchemaRetriever:
    """Ranks every schema in the registry against the dialogue history."""

    def __init__(self, schema_map: dict[str, dict]):
        self.schema_map = schema_map
        self.service_ids = list(schema_map)
        docs = [schema_to_text(schema_map[s]) for s in self.service_ids]
        self._bm25 = BM25Okapi([char_ngram_tokenize(d) for d in docs])

    @staticmethod
    def _as_text(history: list[str] | str) -> str:
        return "\n".join(history) if isinstance(history, list) else history

    def rank(self, history: list[str] | str) -> list[tuple[str, float]]:
        scores = self._bm25.get_scores(char_ngram_tokenize(self._as_text(history)))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [(self.service_ids[i], scores[i]) for i in order]

    def retrieve(self, history: list[str] | str, k: int = 1) -> list[dict]:
        if k <= 0:
            return []
        return [self.schema_map[s] for s, _ in self.rank(history)[:k]]

    def sample_distractors(
        self,
        exclude: set[str],
        n: int,
        rng: random.Random,
    ) -> list[dict]:
        """Uniform random schemas from the registry, excluding what is already shown."""
        if n <= 0:
            return []
        pool = [s for s in self.service_ids if s not in exclude]
        if not pool:
            return []
        return [self.schema_map[s] for s in rng.sample(pool, min(n, len(pool)))]
