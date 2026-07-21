# Distributed signing test vectors

`threshold-signing.json` defines a deterministic 2-of-3 Ethereum BLS threshold
signature.

The master polynomial is:

```text
f(x) = 1 + 2x
```

The composite secret is `f(0) = 1`; participant secrets are `f(1) = 3`,
`f(2) = 5`, and `f(3) = 7`. Each participant signs the same consensus signing
root using the Ethereum BLS12-381 signature ciphersuite. Recovering at
coordinate zero with any two distinct participant IDs produces the listed
`recovered_signature`, which verifies against `composite_public_key`.

Secret keys in this file are public, deterministic test values and **MUST NOT**
be used outside tests.
