#!/usr/bin/env python3
"""Reproduce the corpus using nothing but the standard library.

This is deliberately not an SDK, and it deliberately shares no code with one. It implements
canonical serialization, the block identity rule, and the Merkle construction directly from the
paper, so that "the vectors are reproducible without depending on an implementation" is a claim
something actually checks rather than one the corpus makes about itself.

If this and an implementation disagree, one of them is wrong, and the vectors are how you find out
which. Run it from the repository root:

    python3 tools/verify.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "vectors"

# --- Canonical serialization (RFC 8785, "jcs/1") ------------------------------------------------

ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def canonical_string(value: str) -> str:
    out = ['"']
    for char in value:
        if char in ESCAPES:
            out.append(ESCAPES[char])
        elif ord(char) < 0x20:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def canonical(value: object) -> str:
    """Serialize one value canonically.

    Object members are sorted by the UTF-16 code units of their names, which is what RFC 8785
    specifies and what makes a key outside the Basic Multilingual Plane a case worth having a
    vector for: it sorts differently under code points.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return canonical_string(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        members = sorted(value.items(), key=lambda item: item[0].encode("utf-16-be"))
        return "{" + ",".join(f"{canonical_string(k)}:{canonical(v)}" for k, v in members) + "}"
    raise TypeError(f"not representable in canonical JSON: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return canonical(value).encode("utf-8")


def strict_loads(text: str) -> object:
    """Decode with the semantics the protocol requires, so a rejection case can be shown rejected.

    Python's json takes the last of a duplicate key and accepts lone surrogates. Both would let two
    implementations read one document as two different values, which is precisely the silent
    divergence the identity layer exists to prevent.
    """

    def unique(pairs: list[tuple[str, object]]) -> dict:
        seen: set[str] = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError(f"duplicate JSON key: {key!r}")
            seen.add(key)
        return dict(pairs)

    def no_lone_surrogates(value: object) -> object:
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError("lone surrogate is not encodable as UTF-8") from error
        elif isinstance(value, dict):
            for key, item in value.items():
                no_lone_surrogates(key)
                no_lone_surrogates(item)
        elif isinstance(value, list):
            for item in value:
                no_lone_surrogates(item)
        return value

    def reject_constant(name: str) -> object:
        raise ValueError(f"{name} is not representable in canonical JSON")

    return no_lone_surrogates(json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant))


# --- Identity -----------------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def block_id(envelope: object) -> str:
    """A block's identity: the SHA-256 of its canonical bytes, algorithm-prefixed."""
    return "sha256:" + sha256_hex(canonical_bytes(envelope))


# --- The Merkle construction (RFC 9162, over sorted unique leaves) -------------------------------


def hash_leaf(raw: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + raw).digest()


def hash_node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def largest_power_of_two_below(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def merkle_root(leaves: list[bytes]) -> bytes:
    """The root of a set of leaves.

    The input is sorted and de-duplicated first, which is what makes the root a function of the
    *set*: two clients that hold the same knowledge in a different order must compute the same root,
    or they stop sharing blocks without ever failing.
    """
    ordered = sorted(set(leaves))
    return subtree(ordered)


def subtree(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return hash_leaf(leaves[0])
    split = largest_power_of_two_below(len(leaves))
    return hash_node(subtree(leaves[:split]), subtree(leaves[split:]))


def verify_inclusion(leaf: bytes, index: int, size: int, path: list[bytes], root: bytes) -> bool:
    """RFC 9162 Section 2.1.3.2, with the right-edge normalization written out."""
    if index >= size:
        return False
    running = hash_leaf(leaf)
    position, last = index, size - 1
    for sibling in path:
        if last == 0:
            return False
        if position & 1 or position == last:
            running = hash_node(sibling, running)
            while position & 1 == 0 and position != 0:
                position >>= 1
                last >>= 1
        else:
            running = hash_node(running, sibling)
        position >>= 1
        last >>= 1
    return last == 0 and running == root


# --- Actor identifiers --------------------------------------------------------------------------

LOWER = "abcdefghijklmnopqrstuvwxyz0123456789"
LOCAL_EXTRA = "._%+-"
LABEL_EXTRA = "-"
SEGMENT_EXTRA = "._-"

MAX_IDENTIFIER = 320


def _is_run(value: str, allowed: str) -> bool:
    return bool(value) and all(char in allowed for char in value)


def _valid_label(label: str) -> bool:
    if not 1 <= len(label) <= 63:
        return False
    if not _is_run(label, LOWER + LABEL_EXTRA):
        return False
    return label[0] in LOWER and label[-1] in LOWER


def _valid_domain(domain: str) -> bool:
    if not 1 <= len(domain) <= 255:
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    return all(_valid_label(label) for label in labels)


def _valid_segment(segment: str) -> bool:
    if not 1 <= len(segment) <= 128:
        return False
    if not _is_run(segment, LOWER + SEGMENT_EXTRA):
        return False
    return segment[0] in LOWER and segment[-1] in LOWER


def actor_id_form(value: str) -> str | None:
    """The form an actor identifier takes, or ``None`` when it takes neither.

    Implemented here from the rule rather than imported from anywhere, for the same reason the
    canonical serializer above is: an identifier grammar two implementations read differently
    produces two names for one party, and nothing fails when it happens.
    """
    if not value or len(value) > MAX_IDENTIFIER:
        return None
    if any(char.isspace() or ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        return None
    if "@" in value and "/" in value:
        return None

    if "@" in value:
        local, _, domain = value.partition("@")
        if not 1 <= len(local) <= 64 or ".." in local:
            return None
        if not _is_run(local, LOWER + LOCAL_EXTRA):
            return None
        if local[0] == "." or local[-1] == ".":
            return None
        return "address" if _valid_domain(domain) else None

    if value.count("/") == 1:
        namespace, _, name = value.partition("/")
        if _valid_segment(namespace) and _valid_segment(name):
            return "namespaced"
        return None

    return None


# --- The checks -------------------------------------------------------------------------------


def load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def raw(digest: str) -> bytes:
    algorithm, _, hexed = digest.partition(":")
    if algorithm != "sha256":
        raise ValueError(f"this corpus is sha256 only, got {algorithm!r}")
    return bytes.fromhex(hexed)


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, condition: bool, description: str) -> None:
        if condition:
            self.passed += 1
        else:
            self.failures.append(description)


def check_header(report: Report, name: str, document: dict) -> None:
    report.check(document.get("boltzmann") == 1, f"{name}: protocol version")
    report.check(document.get("serialization") == "jcs/1", f"{name}: serialization identifier")
    report.check(document.get("hash") == "sha256", f"{name}: hash algorithm")
    report.check(bool(document.get("vectors") or document.get("cases")), f"{name}: is not empty")


def check_serialization(report: Report) -> None:
    document = load("serialization.json")
    check_header(report, "serialization", document)
    for vector in document["vectors"]:
        name = vector["name"]
        if vector.get("rejected"):
            try:
                strict_loads(vector["document"])
            except ValueError:
                report.passed += 1
            else:
                report.failures.append(f"serialization/{name}: document MUST be rejected and was not")
            continue
        produced = canonical(vector["value"])
        report.check(produced == vector["canonical_bytes"], f"serialization/{name}: canonical bytes")
        report.check(
            "sha256:" + sha256_hex(produced.encode("utf-8")) == vector["sha256"],
            f"serialization/{name}: digest of the canonical bytes",
        )


def check_block_ids(report: Report) -> None:
    document = load("block_ids.json")
    check_header(report, "block_ids", document)
    for vector in document["vectors"]:
        name = vector["name"]
        report.check(
            canonical(vector["envelope"]) == vector["canonical_bytes"],
            f"block_ids/{name}: envelope canonicalizes to the published bytes",
        )
        report.check(
            block_id(vector["envelope"]) == vector["block_id"],
            f"block_ids/{name}: bytes hash to the published block id",
        )


def check_merkle_roots(report: Report) -> None:
    document = load("merkle_roots.json")
    check_header(report, "merkle_roots", document)
    for vector in document["vectors"]:
        name = vector["name"]
        leaves = [raw(value) for value in vector["block_ids"]]
        report.check(
            merkle_root(leaves).hex() == raw(vector["root"]).hex(),
            f"merkle_roots/{name}: leaf set produces the published root",
        )


def check_inclusion_proofs(report: Report) -> None:
    document = load("inclusion_proofs.json")
    check_header(report, "inclusion_proofs", document)
    for vector in document["vectors"]:
        name = vector["name"]
        report.check(
            verify_inclusion(
                raw(vector["block_id"]),
                vector["leaf_index"],
                vector["tree_size"],
                [bytes.fromhex(node) for node in vector["audit_path"]],
                raw(vector["root"]),
            ),
            f"inclusion_proofs/{name}: proof reconstructs the published root",
        )


def check_schema_selection(report: Report) -> None:
    """Oldest-that-fits, checked as arithmetic rather than taken on trust.

    The rule reduces to one comparison: the assigned version is the smallest the payload satisfies.
    A reader needs no schema engine to check that the corpus is internally consistent about it.
    """
    document = load("schema_selection.json")
    check_header(report, "schema_selection", document)
    for vector in document["vectors"]:
        name = vector["name"]
        satisfies = vector["satisfies"]
        if vector.get("refused"):
            # A version that removes a required member makes the two versions disjoint rather than
            # nested, so a payload can satisfy neither. That is a case oldest-that-fits has to have
            # an answer for, and the answer is a refusal.
            report.check(satisfies == [], f"schema_selection/{name}: satisfies no registered schema")
            report.check(
                "schema_version" not in vector,
                f"schema_selection/{name}: a refused payload is assigned no version",
            )
            continue
        report.check(bool(satisfies), f"schema_selection/{name}: satisfies at least one schema")
        report.check(
            vector["schema_version"] == min(satisfies),
            f"schema_selection/{name}: oldest of {satisfies} was assigned",
        )
        report.check(
            "sha256:" + sha256_hex(vector["canonical_bytes"].encode("utf-8")) == vector["block_id"],
            f"schema_selection/{name}: canonical bytes hash to the published block id",
        )
        envelope = json.loads(vector["canonical_bytes"])
        report.check(
            envelope.get("schema_version") == vector["schema_version"],
            f"schema_selection/{name}: the envelope carries the assigned version",
        )


def check_actor_ids(report: Report) -> None:
    """The identifier grammar, reproduced rather than trusted.

    A rejection is checked as strictly as an acceptance. An implementation that quietly lowercased,
    trimmed, or stripped a scheme prefix would pass every accepting vector and still compute a
    different block_id than everyone else for the same record, which is exactly the failure the
    corpus exists to catch.
    """
    document = load("actor_ids.json")
    check_header(report, "actor_ids", document)
    for vector in document["vectors"]:
        name = vector["name"]
        form = actor_id_form(vector["id"])
        if vector["accepted"]:
            report.check(form == vector["form"], f"actor_ids/{name}: accepted as {vector['form']}")
        else:
            report.check(form is None, f"actor_ids/{name}: refused ({vector['reason']})")


def check_normalization(report: Report) -> None:
    """NFC and NFD are different bytes and therefore different blocks.

    The protocol normalizes nothing, so this is a property of the corpus rather than of a
    normalization step: if these two ever collide, the vectors were built by something that
    normalized behind its own back.
    """
    composed = unicodedata.normalize("NFC", "é")
    decomposed = unicodedata.normalize("NFD", "é")
    report.check(composed != decomposed, "unicode: NFC and NFD are distinct inputs")
    report.check(
        block_id({"value": composed}) != block_id({"value": decomposed}),
        "unicode: NFC and NFD yield distinct block ids",
    )


def main() -> int:
    report = Report()
    check_serialization(report)
    check_block_ids(report)
    check_merkle_roots(report)
    check_inclusion_proofs(report)
    check_schema_selection(report)
    check_actor_ids(report)
    check_normalization(report)

    for failure in report.failures:
        print(f"FAIL  {failure}")
    print(f"\n{report.passed} checks reproduced, {len(report.failures)} failed")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
