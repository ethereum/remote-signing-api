# CLAUDE.md

Guidance for Claude Code and other coding agents working in this repository.

## What this repository is

A specification, not an implementation. It contains the OpenAPI 3.0.3 document describing the REST API
between Ethereum validator clients and remote signers. There is no application code, no package manager
manifest, and no test suite in the usual sense — the "build" is linting and bundling the spec.

Changes here are protocol changes. Two independent implementations (validator clients and signers, listed
in the README) have to agree on them, so prefer additive changes and explicit normative language over
convenience.

## Layout

| Path | Purpose |
| ---- | ------- |
| `remote-signing-oapi.yaml` | Entry point: `info`, `servers`, `tags`, and `$ref`s into `signing/paths/` |
| `signing/paths/sign.yaml` | `POST /api/v1/eth2/sign/{identifier}` — the signing operation and its examples |
| `signing/paths/public_keys.yaml` | `GET /api/v1/eth2/publicKeys` |
| `signing/schemas.yaml` | Every schema, under `components.schemas` |
| `scripts/verify_signing_examples.py` | Recomputes the signing example vectors (see below) |
| `index.html`, `dist/` | Vendored Swagger UI for the GitHub Pages browser |
| `.github/workflows/` | `main.yml` is CI; `deploy.yaml` publishes Pages; `release.yaml` builds tagged releases |

Do not hand-edit anything in `dist/` — it is a vendored Swagger UI build.

## Checks

CI (`.github/workflows/main.yml`) runs three things. Run all three locally before proposing a change:

```bash
npx @stoplight/spectral-cli lint remote-signing-oapi.yaml
npx @apidevtools/swagger-cli bundle ./remote-signing-oapi.yaml -r -t yaml -o ./bundle.yaml
pip install pyyaml && python scripts/verify_signing_examples.py
```

`bundle.yaml` is a build artifact; it is gitignored and must not be committed.

Spectral runs `spectral:oas` with `all` rules plus the custom rules in `.spectral.yml`. Two consequences
worth knowing before you spend time debugging:

- `oas3-valid-media-example` validates every `examples` entry against the request schema. A new example
  that does not match **exactly one** member of the `oneOf` fails the build. This is the main way a
  malformed new signing type gets caught.
- There is one **pre-existing** warning: `paths-snake-case` fires on `/api/v1/eth2/publicKeys`. That path
  is the deployed wire format and cannot be renamed without breaking every client. Leave it. A clean run
  is `0 errors, 1 warning` — treat that as the baseline, not `0 problems`.

## Conventions

- Paths and parameters are snake_case (enforced). The `signingRoot` request property is camelCase for
  historical reasons and is deliberately inconsistent with the rest — see PR #6.
- `uint64` values are JSON **strings**, not numbers (`slot: "32"`). Bytes are `0x`-prefixed hex strings.
- Bump `info.version` in `remote-signing-oapi.yaml` in the feature PR itself, minor for additive changes.
  Every merged feature PR in the history does this.
- Every request body must offer `application/json` (enforced by a custom rule).

## Adding a signing request type

A new type touches four places, and missing any one of them either fails lint or silently produces an
unreachable schema:

1. `signing/schemas.yaml` — the schema. Compose with `allOf: [$ref Signing, ...]` to inherit `fork_info`
   and `signingRoot`, unless the type genuinely does not need them (`GenericSigning` does not, because the
   caller supplies `domain` directly).
2. `signing/paths/sign.yaml` — add to the `oneOf` list.
3. `signing/paths/sign.yaml` — add to `discriminator.mapping` under the `type` value.
4. `signing/paths/sign.yaml` — add an example. Give slashable types one per fork where the shape differs.

## Signing root arithmetic

Every signature this API produces is:

```
BLS.Sign(sk, hash_tree_root(SigningData(object_root, domain)))  ==  sha256(object_root || domain)
domain      = domain_type (4 bytes) || hash_tree_root(ForkData(fork_version, genesis_validators_root))[:28]
fork_version = fork.previous_version if epoch < fork.epoch else fork.current_version
```

`scripts/verify_signing_examples.py` implements this and reproduces the published `signingRoot` of the
`ATTESTATION`, `BLOCK_V2 (GLOAS)` and `RANDAO_REVEAL` examples exactly. If you add or change an example's
roots, run it — do not hand-compute or copy a placeholder root from a neighbouring example.

Note that `hash_tree_root(BeaconBlock) == hash_tree_root(BeaconBlockHeader)`, because a block's `body` leaf
is `hash_tree_root(body)`, which is the header's `body_root`. A signer can therefore do proposer slashing
protection from a header alone.

## Working style here

- Keep diffs minimal and additive; this is a spec several teams implement against.
- Use MUST/SHOULD/MAY deliberately — implementers read these words normatively.
- Link the issue or discussion that motivated a change in the PR description; protocol decisions here are
  usually the outcome of a discussion thread rather than a self-evident fix.
