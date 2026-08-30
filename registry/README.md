# The schema registry

> The schema set is part of the specification: block schemas are published as a normative companion
> document, versioned with the protocol, and a schema is registered exactly when that companion
> carries it.
>
> — *Boltzmann Brain*, §6.6

`schemas.json` is that companion. It exists because `schema_version` sits inside the block envelope
and therefore inside `block_id`: a per-deployment registry would make identity comparable only within
a deployment, and two parties holding the same knowledge would compute different names for it.

## What registration decides

Two rules read this file, and both are mechanical:

- **Satisfies** — a payload satisfies a schema exactly when it validates against it, with no coercion
  and no members the schema does not name.
- **Oldest** — a block MUST be written under the *oldest* registered schema its payload satisfies,
  and *oldest* means by registration number. The numbers are consecutive per memory type, so a
  payload satisfying versions 1 and 3 but not 2 is written under 1. Evolution is not required to be
  monotonic for the rule to stay well defined.

A writer that implements a memory type MUST implement every registered schema for it. One missing an
older schema would version blocks the newer way and silently fork their identities — which is the
failure canonical serialization exists to prevent, re-entering through the version field.

## Shape

```json
{
  "boltzmann": 1,
  "registry_version": 1,
  "schemas": {
    "semantic": [
      {"schema_version": 1, "schema": { ...JSON Schema... }}
    ]
  }
}
```

`registry_version` increments whenever a schema is added. Adding a schema is the only permitted
change: a registered schema is never edited and never withdrawn, because either would re-version
blocks that already exist.
