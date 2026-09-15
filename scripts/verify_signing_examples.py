#!/usr/bin/env python3
"""Verify the cryptographic consistency of the signing request examples in the spec.

Every signature this API produces is BLS.Sign(sk, hash_tree_root(SigningData(object_root, domain))),
which reduces to sha256(object_root || domain). The GENERIC signing request exposes object_root and
domain directly, so its examples can be checked against the same arithmetic a signer performs.

This script checks that:

  1. each GENERIC example satisfies signingRoot == sha256(merkle_root || domain);
  2. each GENERIC example carrying a slashing-protection container proves that container against
     merkle_root, and carries one exactly when its domain type is slashable;
  3. each GENERIC example is equivalent to the typed example it generalises -- the domain derived
     from fork_info matches the supplied domain, and both produce the same signing root.

Check 3 also re-derives the signing roots published for the typed ATTESTATION, BLOCK_V2 and
RANDAO_REVEAL examples, so a regression in those is caught too.

Requires PyYAML. Run from the repository root:

    python3 scripts/verify_signing_examples.py [path-to-sign.yaml]
"""

import hashlib
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

SPEC = sys.argv[1] if len(sys.argv) > 1 else "signing/paths/sign.yaml"
SLOTS_PER_EPOCH = 32

DOMAIN_BEACON_PROPOSER = "0x00000000"
DOMAIN_BEACON_ATTESTER = "0x01000000"
SLASHABLE_DOMAIN_TYPES = {
    DOMAIN_BEACON_PROPOSER: "block_header",
    DOMAIN_BEACON_ATTESTER: "attestation",
}

ZERO = b"\x00" * 32
failures = []


def check(condition, message):
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


# --- SSZ helpers -----------------------------------------------------------

def sha256(data):
    return hashlib.sha256(data).digest()


def unhex(value):
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def hx(value):
    return "0x" + value.hex()


def uint64(value):
    return int(value).to_bytes(8, "little") + ZERO[:24]


def bytes4(value):
    raw = unhex(value)
    assert len(raw) == 4, f"expected 4 bytes, got {len(raw)}"
    return raw + ZERO[:28]


def merkleize(chunks):
    """Merkleize chunks, right-padding the layer to the next power of two."""
    width = 1
    while width < len(chunks):
        width *= 2
    layer = list(chunks) + [ZERO] * (width - len(chunks))
    while len(layer) > 1:
        layer = [sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def htr_checkpoint(cp):
    return merkleize([uint64(cp["epoch"]), unhex(cp["root"])])


def htr_attestation_data(a):
    return merkleize([
        uint64(a["slot"]),
        uint64(a["index"]),
        unhex(a["beacon_block_root"]),
        htr_checkpoint(a["source"]),
        htr_checkpoint(a["target"]),
    ])


def htr_block_header(b):
    # hash_tree_root(BeaconBlock) == hash_tree_root(BeaconBlockHeader): the body leaf of a block is
    # hash_tree_root(body), which is exactly the header's body_root.
    return merkleize([
        uint64(b["slot"]),
        uint64(b["proposer_index"]),
        unhex(b["parent_root"]),
        unhex(b["state_root"]),
        unhex(b["body_root"]),
    ])


def compute_fork_data_root(version, genesis_validators_root):
    return merkleize([bytes4(version), unhex(genesis_validators_root)])


def compute_domain(domain_type, version, genesis_validators_root):
    return unhex(domain_type) + compute_fork_data_root(version, genesis_validators_root)[:28]


def compute_signing_root(object_root, domain):
    return merkleize([object_root, domain])


def fork_version_for_epoch(fork_info, epoch):
    fork = fork_info["fork"]
    return fork["previous_version"] if int(epoch) < int(fork["epoch"]) else fork["current_version"]


def verify_merkle_proof(leaf, branch, generalized_index, root):
    """Fold a leaf up to the root using its generalized index."""
    index = int(generalized_index)
    if index < 1:
        return False
    if len(branch) != index.bit_length() - 1:
        return False
    node = leaf
    for sibling in branch:
        node = sha256(node + unhex(sibling)) if index % 2 == 0 else sha256(unhex(sibling) + node)
        index //= 2
    return index == 1 and node == root


# --- checks ----------------------------------------------------------------

def load_examples():
    with open(SPEC) as handle:
        spec = yaml.safe_load(handle)
    examples = spec["post"]["requestBody"]["content"]["application/json"]["examples"]
    return {name: body["value"] for name, body in examples.items()}


def check_signing_root_identity(name, example):
    merkle_root = unhex(example["merkle_root"])
    domain = unhex(example["domain"])
    expected = compute_signing_root(merkle_root, domain)
    check(
        hx(expected) == example["signingRoot"],
        f"{name}: signingRoot == sha256(merkle_root || domain)",
    )
    return expected


def check_slashing_protection(name, example):
    domain_type = "0x" + unhex(example["domain"])[:4].hex()
    merkle_root = unhex(example["merkle_root"])
    expected_field = SLASHABLE_DOMAIN_TYPES.get(domain_type)

    present = [f for f in SLASHABLE_DOMAIN_TYPES.values() if f in example]
    check(
        present == ([expected_field] if expected_field else []),
        f"{name}: domain type {domain_type} carries {expected_field or 'no'} slashing-protection container",
    )
    if expected_field is None or expected_field not in example:
        return

    container = dict(example[expected_field])
    proof = container.pop("proof")
    leaf = htr_attestation_data(container) if expected_field == "attestation" else htr_block_header(container)
    check(
        verify_merkle_proof(leaf, proof["merkle_proof"], proof["generalized_index"], merkle_root),
        f"{name}: {expected_field} proves against merkle_root at generalized index {proof['generalized_index']}",
    )


def check_equivalence(name, generic, typed, domain_type, object_root, epoch):
    """The generic example must be indistinguishable from the typed example it generalises."""
    domain = compute_domain(domain_type, fork_version_for_epoch(generic["fork_info"], epoch),
                            generic["fork_info"]["genesis_validators_root"])
    check(hx(domain) == generic["domain"], f"{name}: domain matches compute_domain() from fork_info")
    check(hx(object_root) == generic["merkle_root"], f"{name}: merkle_root matches hash_tree_root(object)")
    check(
        hx(compute_signing_root(object_root, domain)) == typed["signingRoot"],
        f"{name}: signing root equals the typed example's published signingRoot",
    )


def require(examples, name):
    """Look up an example by name, recording a failure rather than raising if it is missing."""
    if name not in examples:
        check(False, f"example {name!r} is present in {SPEC}")
        return None
    return examples[name]


def main():
    examples = load_examples()
    generic = {n: e for n, e in examples.items() if e.get("type") == "GENERIC"}
    if not generic:
        sys.exit("no GENERIC examples found in " + SPEC)

    print(f"Checking {len(generic)} GENERIC example(s) in {SPEC}\n")

    for name, example in generic.items():
        print(name)
        check_signing_root_identity(name, example)
        check_slashing_protection(name, example)
        print()

    # Equivalence with the typed examples these generalise.
    print("Equivalence with typed examples")
    att = require(examples, "GENERIC (DOMAIN_BEACON_ATTESTER)")
    typed_att = require(examples, "ATTESTATION")
    if att and typed_att:
        check_equivalence(
            "attester", att, typed_att, DOMAIN_BEACON_ATTESTER,
            htr_attestation_data(att["attestation"]), att["attestation"]["target"]["epoch"],
        )

    blk = require(examples, "GENERIC (DOMAIN_BEACON_PROPOSER)")
    typed_blk = require(examples, "BLOCK_V2 (GLOAS)")
    if blk and typed_blk:
        header = {k: v for k, v in blk["block_header"].items() if k != "proof"}
        check_equivalence(
            "proposer", blk, typed_blk, DOMAIN_BEACON_PROPOSER,
            htr_block_header(header), int(header["slot"]) // SLOTS_PER_EPOCH,
        )

    randao = require(examples, "GENERIC (non-slashable domain)")
    typed_randao = require(examples, "RANDAO_REVEAL")
    if randao and typed_randao:
        randao_epoch = typed_randao["randao_reveal"]["epoch"]
        check_equivalence(
            "randao", {**randao, "fork_info": typed_randao["fork_info"]},
            typed_randao, "0x02000000", uint64(randao_epoch), randao_epoch,
        )

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
