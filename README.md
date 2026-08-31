# Boltzmann conformance corpus

The golden vectors for the [Boltzmann Protocol](https://github.com/gaussia-labs/papers), and the
normative schema registry the protocol's versioning rule selects against.

> These vectors MUST be plain data, readable without executing any implementation of this protocol.
> An implementation in another language demonstrates agreement by reproducing them, which is a
> stronger claim than passing a test suite supplied by a reference implementation, because it
> requires no dependency on that implementation at all.
>
> — *Boltzmann Brain*, §15.2

That sentence is why this repository exists separately from any SDK. While the vectors lived inside
`pyboltzmann`, their location, naming and shape were governed by a Python package layout, and
"conforming" quietly degraded into "matches pyboltzmann, bugs included". The authority is the corpus;
an SDK is one of its consumers.

## What is here

```
vectors/          the golden vectors, one file per category
registry/         the schema registry companion (§6.6)
tools/            a generator, and a reader that depends on no SDK
CORPUS_VERSION    which corpus this tree is
```

Everything is JSON. Nothing here imports an implementation of the protocol, and nothing here needs
to be installed.

## Reading a vector file

Every file carries the same header, so a reader can refuse a file it cannot interpret before
looking at a single case:

| Field | Meaning |
|---|---|
| `boltzmann` | Protocol version these vectors are for. |
| `serialization` | Canonical serialization identifier. `jcs/1` is RFC 8785. |
| `hash` | Hash the identities are computed under. |
| `layout` | Merkle construction, where the category involves one. |
| `namespace` | Signature namespace, where the category involves one. |
| `description` | What the category demonstrates. |

Then either `vectors` (a list of cases) or `cases` (a list of judgements), never both. An empty
file is a promise with nothing behind it and is not a valid corpus file.

## Categories

| File | What must be reproduced |
|---|---|
| `serialization.json` | Values and the exact canonical bytes they produce, including the documents that MUST be rejected. |
| `block_ids.json` | Envelopes and the `block_id` each one hashes to. |
| `actor_ids.json` | Actor identifiers of both accepted forms, and the ones that MUST be refused, each with its reason. |
| `schema_selection.json` | Payloads and the `schema_version` oldest-that-fits assigns them against the registered set. |
| `merkle_roots.json` | Leaf sets and the root the construction produces. |
| `inclusion_proofs.json` | Proofs, each with its leaf index and tree size, and the roots they must reconstruct. |
| `signatures.json` | Snapshots, published test keys, and the verdict a verifier MUST reach. |
| `sshsig.json` | The SSHSIG framing layer: what parses, and what MUST be rejected. |
| `reconciliation.json` | An ancestor and two branches, with the set Equation 4 must produce — and the refusals. |

## Versioning

`CORPUS_VERSION` is `<protocol>.<revision>`: the protocol version these vectors are for, and how
many times the corpus has been published for it. A consumer pins a corpus version and records it.

**A published vector never changes.** A case whose expected output would change is not a corrected
case; it is either a bug in whatever produced it, or a new serialization identifier — the protocol
says so explicitly, because silently editing a vector would let two implementations agree with the
corpus at different times and disagree with each other. Cases are added, and a revision that adds
them bumps the revision number.

## The published test keys

`signatures.json` and `sshsig.json` carry private key seeds. **They are published test values.**
Anyone can sign anything with them. They exist so that two implementations reach the same verdict on
the same bytes, and they must never appear in a brain anyone relies on.

## Reproducing the corpus

```bash
python3 tools/verify.py          # recompute every identity, using only the standard library
```

`tools/verify.py` is deliberately not an SDK. It implements canonical serialization, the block
identity rule, and the Merkle construction directly from the paper, in a few hundred lines of
standard library, and checks that the vectors say what the paper says they should. If it and an SDK
ever disagree, one of them is wrong and the vectors are how you find out which.

`tools/generate.py` produces the files that are mechanically derivable. It is the only thing here
that imports an implementation, it is not required to read the corpus, and its output is committed.

## License

MIT. The vectors are data; reproduce them freely.
