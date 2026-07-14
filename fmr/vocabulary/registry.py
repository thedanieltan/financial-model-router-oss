from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


@dataclass(frozen=True)
class IndustryVocabulary:
    vocabulary_id: str
    version: str
    kind: str
    canonical_industry: str | None
    aliases: tuple[str, ...]
    concepts: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "industry-vocabulary.v1", "vocabulary_id": self.vocabulary_id,
            "version": self.version, "kind": self.kind, "canonical_industry": self.canonical_industry,
            "aliases": list(self.aliases), "concepts": [dict(item) for item in self.concepts],
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "IndustryVocabulary":
        required = {"contract_version", "vocabulary_id", "version", "kind", "canonical_industry", "aliases", "concepts"}
        if not isinstance(payload, dict) or set(payload) != required or payload.get("contract_version") != "industry-vocabulary.v1":
            raise ValueError("industry vocabulary fields do not match the contract")
        kind = payload.get("kind")
        if kind not in {"core", "industry"}:
            raise ValueError("vocabulary kind is invalid")
        if not isinstance(payload.get("vocabulary_id"), str) or not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", payload["vocabulary_id"]):
            raise ValueError("vocabulary_id is invalid")
        if not isinstance(payload.get("version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", payload["version"]):
            raise ValueError("vocabulary version is invalid")
        canonical = payload.get("canonical_industry")
        if (kind == "industry" and not isinstance(canonical, str)) or (kind == "core" and canonical is not None):
            raise ValueError("canonical_industry does not match vocabulary kind")
        if isinstance(canonical, str) and not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", canonical):
            raise ValueError("canonical_industry is invalid")
        aliases = payload.get("aliases")
        concepts = payload.get("concepts")
        if not isinstance(aliases, list) or not all(isinstance(item, str) and item for item in aliases) or len(set(aliases)) != len(aliases):
            raise ValueError("vocabulary aliases must be unique strings")
        if len({_normalized(item) for item in aliases}) != len(aliases):
            raise ValueError("normalized vocabulary aliases must be unique")
        if not isinstance(concepts, list) or not concepts:
            raise ValueError("vocabulary concepts must be non-empty")
        seen = set()
        for concept in concepts:
            if not isinstance(concept, dict) or set(concept) != {"concept_id", "label", "aliases"}:
                raise ValueError("vocabulary concept is invalid")
            if not isinstance(concept["concept_id"], str) or not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", concept["concept_id"]) or concept["concept_id"] in seen:
                raise ValueError("vocabulary concept IDs must be unique strings")
            if not isinstance(concept["label"], str) or not concept["label"] or not isinstance(concept["aliases"], list) or not all(isinstance(item, str) and item for item in concept["aliases"]) or len(set(concept["aliases"])) != len(concept["aliases"]):
                raise ValueError("vocabulary concept labels and aliases are invalid")
            seen.add(concept["concept_id"])
        return cls(payload["vocabulary_id"], payload["version"], kind, canonical, tuple(aliases), tuple(concepts))


class VocabularyRegistry:
    def __init__(self, vocabularies: tuple[IndustryVocabulary, ...]) -> None:
        if len({item.vocabulary_id for item in vocabularies}) != len(vocabularies):
            raise ValueError("vocabulary IDs must be unique")
        self.vocabularies = tuple(sorted(vocabularies, key=lambda item: item.vocabulary_id))
        aliases: dict[str, str] = {}
        for item in self.vocabularies:
            if item.kind != "industry" or item.canonical_industry is None:
                continue
            for alias in (item.canonical_industry, *item.aliases):
                key = _normalized(alias)
                if key in aliases and aliases[key] != item.canonical_industry:
                    raise ValueError("industry vocabulary aliases conflict")
                aliases[key] = item.canonical_industry
        self._industry_aliases = aliases

    @classmethod
    def builtins(cls) -> "VocabularyRegistry":
        root = files("fmr.vocabulary.data")
        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.iterdir(), key=lambda item: item.name) if path.name.endswith(".json")]
        return cls(tuple(IndustryVocabulary.from_mapping(item) for item in payloads))

    def normalize_industry(self, value: str) -> str:
        normalized = _normalized(value)
        return self._industry_aliases.get(normalized, normalized.replace(" ", "_"))

    def concept_ids(self, vocabulary_id: str) -> tuple[str, ...]:
        for vocabulary in self.vocabularies:
            if vocabulary.vocabulary_id == vocabulary_id:
                return tuple(concept["concept_id"] for concept in vocabulary.concepts)
        raise KeyError(vocabulary_id)
