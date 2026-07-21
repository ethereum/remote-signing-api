# Distributed signing profile

## Status

This document defines an optional threshold BLS profile for the Remote Signing
API. It introduces a coordinator-to-participant interface without changing the
existing validator-client interface. A coordinator continues to expose
`POST /api/v1/eth2/sign/{identifier}` and returns a complete validator
signature. It uses the distributed endpoints internally to obtain partial
signatures.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as described in RFC 2119 and RFC 8174 when,
and only when, they appear in bold.

## Architecture

```text
validator client
    -> Remote Signing API coordinator
        -> distributed participant 1
        -> distributed participant 2
        -> distributed participant 3
        -> threshold recovery and final verification
    <- complete validator signature
```

A **participant** stores one BLS secret-key share. A **coordinator** discovers
the shares' public metadata, sends an identical signing request to multiple
participants, verifies their partial signatures, and recovers a complete
signature from any threshold-sized subset.

The component public key belongs to one participant's share. The composite
public key is the validator public key recovered at polynomial coordinate zero.
The composite public key is the `identifier` used by every distributed signing
request. A coordinator never substitutes a participant's component key into
the path.

Distributed key generation, share encryption and storage, account creation,
and operator provisioning are outside this profile.

## Endpoints

| Purpose | Operation |
| --- | --- |
| List distributed accounts | `GET /api/v1/eth2/distributed/accounts` |
| Get one distributed account | `GET /api/v1/eth2/distributed/accounts/{identifier}` |
| Create one partial signature | `POST /api/v1/eth2/distributed/sign/{identifier}` |
| Create partial signatures for multiple accounts | `POST /api/v1/eth2/distributed/sign` |

The single and batch signing operations use the same `SigningRequest` and
`BatchSigningRequest` schemas as the complete-signature operations. This keeps
fork-specific signing behavior identical across the validator-client and
coordinator-participant boundaries.

## Account discovery

Each distributed account contains:

| Field | Meaning |
| --- | --- |
| `participant_id` | Non-zero Shamir coordinate held by the responding participant. |
| `public_key` | Component public key for the responding participant's share. |
| `composite_public_key` | Complete validator public key, common to every participant. |
| `signing_threshold` | Number of valid partial signatures required for recovery. |
| `participants` | Complete set of participant IDs and HTTPS origins. |

Participant IDs and thresholds are unsigned 64-bit integers encoded as decimal
JSON strings. Public keys are compressed 48-byte BLS public keys encoded as
`0x`-prefixed hexadecimal.

For `n` participants, every ID **MUST** be unique and non-zero and the threshold
**MUST** satisfy:

```text
1 <= signing_threshold <= n
```

Each endpoint **MUST** be unique. The responder's authenticated endpoint
**MUST** map to its `participant_id`, and the responder **MUST** possess the
share at that ID.

All participants for a distributed validator **MUST** advertise the same
composite public key, threshold, and participant set. Their component public
keys normally differ. A coordinator obtains each component public key by
querying that participant's account resource.

A coordinator **MUST** reject discovery with conflicting common metadata,
duplicate or zero IDs, duplicate endpoints, an invalid threshold, malformed
keys, or a response that cannot be bound to its authenticated endpoint. It
**MUST** constrain discovered endpoints with operator-configured trust roots
and network or endpoint allowlists before connecting to them.

## Signing roots

Participants **MUST** independently compute the Ethereum consensus signing
root from the structured request. If `signingRoot` is present, a participant
**MUST** reject the request when it differs from the computed root.

For `GENERIC`, the request contains the already-computed SSZ object root and the
consensus domain:

```text
SigningData:
  object_root: Bytes32
  domain: Bytes32

signing_root = SHA-256(object_root || domain)
```

No JSON bytes, hexadecimal prefix, or length prefix is included in that hash.
A participant with slashing protection **MUST** reject `GENERIC` requests whose
domain type is beacon proposer or beacon attester. Callers use `BLOCK_V2` and
`ATTESTATION` for those duties so every participant evaluates the structured
slashable data.

For other request types, signing-root computation is exactly the computation
defined by the base Remote Signing API and Ethereum consensus specifications.

## BLS share relationship

For a `t`-of-`n` account, provisioning creates a degree-`t-1` polynomial over
the BLS scalar field:

```text
f(x) = a_0 + a_1*x + ... + a_(t-1)*x^(t-1)
```

For participant ID `i`:

```text
component_secret_i = f(i)
component_public_i = component_secret_i * G1
composite_secret = f(0) = a_0
composite_public = composite_secret * G1
```

The decimal participant ID is interpreted as its unsigned numeric value in
`Fr`. It is not hashed and is not an array index.

A participant computes:

```text
partial_signature_i = BLS.Sign(component_secret_i, signing_root)
```

Public keys use the Ethereum compressed 48-byte G1 format. Partial and complete
signatures use the Ethereum compressed 96-byte G2 format. Implementations
**MUST** reject invalid encodings and points at infinity.

The partial-signature response includes `participant_id`, `signing_root`, and
`signature`. The response ID is a consistency check. A coordinator binds the
share to the authenticated endpoint and discovery view rather than trusting an
unbound body value.

## Threshold recovery

For a set `S` containing at least `t` distinct valid participants, recover the
signature at coordinate zero. For each `i` in `S`, calculate:

```text
lambda_i = product over j in S, j != i of (0 - j) / (i - j)
```

with all operations in `Fr`, then recover the G2 point:

```text
composite_signature = sum over i in S of lambda_i * partial_signature_i
```

The equivalent `product(j / (j - i))` coefficient form is valid. A coordinator
**SHOULD** verify every partial signature against the component public key
learned from that endpoint. It **MUST** verify the recovered signature against
the composite public key and signing root, and **MUST NOT** return an unverified
signature.

The [2-of-3 test vector](distributed/test-vectors/threshold-signing.json)
contains component keys and signatures, participant IDs, and a recovered
signature for every threshold-sized subset.

## Coordinator algorithm

For each signing request, a coordinator:

1. Loads and validates a complete account view.
2. Constructs the structured request and computes its signing root.
3. Sends the identical request to participant endpoints, changing only the
   HTTPS origin.
4. Binds each response to the endpoint's discovered ID and component key.
5. Treats a non-200 response, timeout, malformed body, mismatched ID,
   mismatched signing root, malformed signature, or invalid partial signature
   as no share.
6. Recovers after collecting `t` valid shares.
7. Verifies the recovered signature against the composite public key.
8. Returns the complete signature through the base Remote Signing API.

If fewer than `t` valid shares are available, the coordinator fails without
returning a signature. It **MUST NOT** combine shares from different composite
keys, participant configurations, messages, domains, or batch positions.

## Batch signing

The batch endpoints apply one common `signing_request` to each public key in
`identifiers`. This permits implementations to compute common signing data once
while still applying authorization, key lookup, and slashing protection per
validator.

`identifiers` **MUST** be non-empty and **MUST NOT** contain the same decoded
public key more than once, including through different hexadecimal casing.

Batch signing is defined for `AGGREGATION_SLOT`, `ATTESTATION`, `GENERIC`,
`RANDAO_REVEAL`, `SYNC_COMMITTEE_MESSAGE`, and
`SYNC_COMMITTEE_SELECTION_PROOF`. Types whose signed object embeds a unique
validator or aggregator identity use the existing single-key endpoint.

The HTTP response is 200 when the batch itself is valid and contains one result
per identifier in request order. Each result contains either a signature or an
error object. An error's `code` is the HTTP status that the equivalent
single-key request would have returned. An individual error does not fail or
shift another item.

For distributed batches, every successful item additionally contains that
account's `participant_id` and computed `signing_root`. A coordinator maintains
a separate set of `(participant_id, partial_signature)` values for every batch
position.

## Authorization, transport, and slashing safety

Distributed participant endpoints are intended for a private,
operator-controlled network. A participant **MUST** authenticate and authorize
the coordinator before listing accounts or using a share. Deployments
**SHOULD** use HTTPS with TLS 1.3 and mutual TLS, validate both certificate
chains, and authorize a stable subject alternative name.

Every participant **MUST** independently apply durable Ethereum slashing
protection before releasing an attestation or block-proposal share. At minimum,
it prevents double proposals, double votes, and surround votes. The safety
record and decision to release a share **MUST** be ordered so a crash cannot
release a share without preserving the corresponding record.

An exact retry is not guaranteed to succeed because a participant may apply a
stricter slashing policy. A coordinator **SHOULD** cache a verified recovered
signature when safe replay is permitted by the surrounding system.

Threshold security does not replace authorization or slashing protection. A
participant makes its own policy decision and does not trust the coordinator's
decision merely because fewer than `t` participants cannot sign alone.

## One-participant operation

A conventional signer **MAY** expose a 1-of-1 distributed account. It advertises
one participant and a threshold of `"1"`; its component and composite public
keys are identical. Its partial signature is also the complete validator
signature.
