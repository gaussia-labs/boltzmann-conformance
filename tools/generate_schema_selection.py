"""Emit the schema-selection vectors: payload + registered set -> the version assigned."""
import json
from pathlib import Path

from boltzmann.blocks.base import Block
from boltzmann.blocks.memory_type import MemoryType
from boltzmann.constants import PROTOCOL_VERSION
from boltzmann.identity.serialization import SERIALIZATION_ID

OUT = Path("/Users/alexfiorenza/Documents/software_development/projects/gaussia/boltzmann-conformance/vectors/schema_selection.json")

CASES = [
    (
        "semantic_satisfying_several_takes_the_oldest",
        MemoryType.SEMANTIC,
        {"kind": "formula", "label": "Fourier", "statement": "a periodic function decomposes into sines and cosines"},
        "The case the rule exists for. This payload validates under more than one registered schema, "
        "and the oldest is chosen: writing it under the newest would silently re-version every block "
        "written after a schema is registered, including blocks using nothing it added.",
    ),
    (
        "semantic_using_a_later_vocabulary_takes_that_version",
        MemoryType.SEMANTIC,
        {"kind": "scheme", "scheme": "argument", "exclusive": True},
        "A brain stops being readable by an older client exactly at the point where it genuinely uses "
        "something that client has no schema for -- and not one block earlier.",
    ),
    (
        "episodic_minimal_takes_the_oldest",
        MemoryType.EPISODIC,
        {"summary": "Lecture 07", "occurred_at": "2026-05-14T14:00:00Z"},
        "The same rule in a second memory type: registration number decides, never recency.",
    ),
    (
        "procedural_minimal_takes_the_oldest",
        MemoryType.PROCEDURAL,
        {"label": "normalize a PDF", "goal": "recover readable text", "steps": [{"action": "extract text"}, {"action": "strip headers"}]},
        "A procedure that uses no later vocabulary stays readable by the oldest client that knows procedures.",
    ),
]


def satisfied_versions(memory_type: MemoryType, payload: dict) -> list[int]:
    versions = []
    for candidate in Block.schemas(memory_type):
        try:
            candidate.model_validate(dict(payload))
        except Exception:
            continue
        versions.append(candidate.SCHEMA_VERSION)
    return versions


def main() -> None:
    vectors = []
    for name, memory_type, payload, why in CASES:
        block = Block.build(memory_type, payload)
        satisfies = satisfied_versions(memory_type, payload)
        assert block.SCHEMA_VERSION == min(satisfies), (name, satisfies, block.SCHEMA_VERSION)
        vectors.append(
            {
                "name": name,
                "memory_type": memory_type.value,
                "payload": payload,
                "satisfies": satisfies,
                "schema_version": block.SCHEMA_VERSION,
                "canonical_bytes": block.canonical_bytes().decode("utf-8"),
                "block_id": str(block.block_id),
                "why": why,
            }
        )

    document = {
        "boltzmann": PROTOCOL_VERSION,
        "serialization": SERIALIZATION_ID,
        "hash": "sha256",
        "registry_version": 1,
        "description": (
            "Payloads and the schema_version that oldest-that-fits assigns them against the registered "
            "set in registry/schemas.json. 'satisfies' lists every registered version the payload "
            "validates under, with no coercion and no members the schema does not name; "
            "'schema_version' is the smallest of them, always. Because schema_version sits inside the "
            "envelope and therefore inside block_id, two implementations that chose differently here "
            "would compute different names for identical knowledge and stop sharing blocks without "
            "either of them failing."
        ),
        "vectors": vectors,
    }
    OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for v in vectors:
        print(f"  {v['name']}: satisfies {v['satisfies']} -> v{v['schema_version']}")


if __name__ == "__main__":
    main()
