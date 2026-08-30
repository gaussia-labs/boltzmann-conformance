"""Emit the schema registry companion from the SDK's registered block classes."""
import json
from pathlib import Path

from boltzmann.blocks.base import Block
from boltzmann.blocks.memory_type import MemoryType
from boltzmann.constants import PROTOCOL_VERSION
from boltzmann.ingest.schema import JSON_SCHEMA_DIALECT, REF_TEMPLATE

OUT = Path("/Users/alexfiorenza/Documents/software_development/projects/gaussia/boltzmann-conformance/registry/schemas.json")

registry = Block.registry()
schemas: dict[str, list[dict]] = {}
for memory_type in MemoryType:
    entries = sorted((v, c) for (mt, v), c in registry.items() if mt is memory_type)
    if not entries:
        continue
    schemas[memory_type.value] = [
        {
            "schema_version": version,
            "title": cls.__name__,
            "schema": cls.model_json_schema(ref_template=REF_TEMPLATE),
        }
        for version, cls in entries
    ]

document = {
    "boltzmann": PROTOCOL_VERSION,
    "registry_version": 1,
    "dialect": JSON_SCHEMA_DIALECT,
    "description": (
        "The registered block schemas. A schema is registered exactly when this document carries it; "
        "oldest-that-fits selects by schema_version, which is consecutive per memory type."
    ),
    "schemas": schemas,
}
OUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {OUT}")
for kind, entries in schemas.items():
    print(f"  {kind}: versions {[e['schema_version'] for e in entries]}")
