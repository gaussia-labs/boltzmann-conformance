"""Append the provenance attribution vectors: who took part, and which version records it.

Appends only. A published vector is never edited, so this adds cases to block_ids.json and
schema_selection.json and leaves every existing entry byte-identical.

Run from the SDK checkout: ``uv run python <this file>``.
"""

import json
from pathlib import Path

from boltzmann.blocks.base import Block
from boltzmann.blocks.memory_type import MemoryType
from boltzmann.blocks.provenance import (
    Actor,
    ActorKind,
    Collaborator,
    DerivationRecord,
    Producer,
    ProducerKind,
    RemovalMechanism,
    RemovalRecord,
    provenance_block,
)
from boltzmann.identity.digest import BlockId

CORPUS = Path("/Users/alexfiorenza/Documents/software_development/projects/gaussia/boltzmann-conformance")

BLOCK = BlockId.of(b"boltzmann conformance: a derived block")
SOURCE = BlockId.of(b"boltzmann conformance: the evidence it cites")
AT = "2026-08-31T00:00:00Z"

ALEX = Actor(id="alex@example.org", kind=ActorKind.HUMAN)
JUAN = Collaborator(id="juan@example.org", kind=ActorKind.HUMAN)
CLAUDE_CODE = Collaborator(id="anthropic/claude-code", kind=ActorKind.AGENT, model="anthropic/fable-5")
CODEX = Collaborator(id="openai/codex", kind=ActorKind.AGENT, model="openai/gpt-5.6-sol")
HARNESS_ONLY = Collaborator(id="nousresearch/hermes", kind=ActorKind.AGENT)
DIRECT = Collaborator(id="anthropic/fable-5", kind=ActorKind.AGENT, model="anthropic/fable-5")


SOLO = Producer(kind=ProducerKind.ACTOR, id="alex@example.org")
"""What a version-1 derivation names when a person worked alone.

Passed even to the assisted cases below, and discarded there: version 2 has no producer, and
constructing a version-1 record to hand to the selector is how the two versions stay one code path.
The published vector is the block that comes out, which carries no producer at all.
"""


def derivation(**extra):
    return DerivationRecord(block=BLOCK, derived_from=[SOURCE], actor=ALEX, at=AT, producer=SOLO, **extra)


CASES = [
    (
        "provenance_derivation_unassisted",
        provenance_block(derivation()),
        "A person working alone. It names nobody, so it stays at schema version 1 with the bytes it "
        "would have had before version 2 existed -- which is the property that keeps a brain readable "
        "by clients that have not upgraded. Reproduce this one before any other.",
    ),
    (
        "provenance_derivation_with_an_agent",
        provenance_block(derivation(), [CLAUDE_CODE]),
        "The ordinary case once a brain is hydrated through an agent: a runtime, and the model it ran. "
        "The pair is one entry because the same model under a different harness is a different "
        "collaborator -- the harness decides what the model sees and which tools it can reach.",
    ),
    (
        "provenance_derivation_agent_without_a_model",
        provenance_block(derivation(), [HARNESS_ONLY]),
        "A participant whose model is not disclosed. Naming the harness alone is a smaller claim than "
        "naming a model that was guessed, and a batch invalidation over a model will not reach it, "
        "which is correct: nothing said it was there.",
    ),
    (
        "provenance_derivation_model_called_directly",
        provenance_block(derivation(), [DIRECT]),
        "A model called with no harness around it. The participant is the model, so the identifier and "
        "the model agree. The repetition is what lets a batch invalidation look in exactly one place "
        "instead of guessing whether an entry names a runtime or a model.",
    ),
    (
        "provenance_joint_session",
        provenance_block(derivation(), [CODEX, JUAN]),
        "Two people and an agent in one session. People and agents share one shape, so reading who took "
        "part never branches; the person carries no model, because a person does not run one as part of "
        "their identity.",
    ),
    (
        "provenance_two_agents_keep_their_pairs",
        provenance_block(derivation(), [CLAUDE_CODE, CODEX]),
        "Two agents writing into one snapshot. Each runtime carries its own model, so which model ran "
        "where is unambiguous -- the thing a flat list of participants would lose.",
    ),
    (
        "provenance_removal_stays_at_version_one",
        provenance_block(
            RemovalRecord(
                blocks=[BLOCK],
                mechanism=RemovalMechanism.DROP,
                memory_type=MemoryType.SEMANTIC,
                actor=ALEX,
                at=AT,
                reason="ingested in error",
            ),
            [CLAUDE_CODE],
        ),
        "A removal, written by a session that names assisting parties -- and still at version 1, "
        "carrying none of them. A removal record is the one record a verifier must decode to decide a "
        "blocking question, so a version an older client lacks would turn 'I cannot read this' into "
        "'you violated the removal invariant': a specific, confident, wrong accusation with no way to "
        "withdraw it. Not being able to read something must never be reported as that thing being wrong.",
    ),
]


def main() -> None:
    path = CORPUS / "vectors" / "block_ids.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    existing = {vector["name"] for vector in document["vectors"]}

    for name, block, note in CASES:
        if name in existing:
            raise SystemExit(f"{name} is already published; a published vector is never edited")
        document["vectors"].append(
            {
                "name": name,
                "memory_type": block.MEMORY_TYPE.value,
                "schema_version": block.SCHEMA_VERSION,
                "envelope": block.envelope(),
                "canonical_bytes": block.canonical_bytes().decode("utf-8"),
                "block_id": str(block.block_id),
                "note": note,
            }
        )

    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"block_ids.json: {len(CASES)} appended, {len(document['vectors'])} total")

    # --- schema selection: the disjoint case ----------------------------------------------------
    path = CORPUS / "vectors" / "schema_selection.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    existing = {vector["name"] for vector in document["vectors"]}

    base = {"record_type": "derivation", "block": str(BLOCK), "derived_from": [str(SOURCE)],
            "actor": ALEX.model_dump(mode="json", exclude_none=True), "at": AT}
    producer = {"kind": "actor", "id": "alex@example.org"}
    assisted = [CLAUDE_CODE.model_dump(mode="json", exclude_none=True)]

    selections = [
        ("provenance_naming_nobody_stays_at_one", {**base, "producer": producer}, [1],
         "Version 2 removes a required member rather than adding one, so the two are disjoint rather "
         "than nested. A payload carrying producer satisfies version 1 alone."),
        ("provenance_naming_who_assisted_takes_two", {**base, "assisted_by": assisted}, [2],
         "And the mirror: a payload carrying assisting parties satisfies version 2 alone. Oldest-that-fits "
         "needs no new rule for a removal, because 'satisfies' already admits no member a schema does not name."),
    ]
    refusals = [
        ("provenance_carrying_both_is_refused", {**base, "producer": producer, "assisted_by": assisted},
         "producer belongs to version 1 and assisted_by to version 2; a payload with both satisfies neither, "
         "and a writer that meant one of them must say which."),
        ("provenance_carrying_neither_is_refused", dict(base),
         "Version 1 obliged a writer to say what produced a derived block. Dropping producer must not quietly "
         "relax that into 'derived, and I decline to say by what', so version 2 requires the parties instead."),
    ]

    for name, payload, satisfies, note in selections:
        if name in existing:
            raise SystemExit(f"{name} is already published")
        block = Block.build(MemoryType.PROVENANCE, {"record": payload})
        assert block.SCHEMA_VERSION == min(satisfies), (name, block.SCHEMA_VERSION)
        document["vectors"].append({
            "name": name, "memory_type": "provenance", "payload": {"record": payload},
            "satisfies": satisfies, "schema_version": block.SCHEMA_VERSION,
            "canonical_bytes": block.canonical_bytes().decode("utf-8"),
            "block_id": str(block.block_id), "note": note,
        })

    for name, payload, note in refusals:
        if name in existing:
            raise SystemExit(f"{name} is already published")
        try:
            Block.build(MemoryType.PROVENANCE, {"record": payload})
        except Exception:
            pass
        else:
            raise SystemExit(f"{name} was accepted and must not be")
        document["vectors"].append({
            "name": name, "memory_type": "provenance", "payload": {"record": payload},
            "satisfies": [], "refused": True, "note": note,
        })

    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"schema_selection.json: {len(selections) + len(refusals)} appended, {len(document['vectors'])} total")


if __name__ == "__main__":
    main()
