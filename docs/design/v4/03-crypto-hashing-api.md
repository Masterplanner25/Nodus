# Nodus v4.0 — Design Doc 03: Crypto / Hashing API

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 7 (Crypto / Hashing API Shape) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships hashing, encoding, and secure-random functionality as three
Tier 1 orchestration stdlib namespaces. Decision 7 (Phase 0) locked the
namespace split and scope: `std:hash` for hashing and HMAC, `std:encoding`
for base64/hex/URL encoding, `std:secrets` for cryptographically secure
random.

This doc specifies all three namespaces in implementable detail. Three
namespaces in one doc because they're conceptually grouped (cryptographic
primitives) and share an implementation substrate (Python stdlib only,
no external dependencies).

The scope is deliberately narrow: orchestration scripts need to hash
data (content addressing, integrity checks), sign messages (HMAC for
API authentication), encode binary data for transport (base64, hex,
URL), and generate secure tokens (API keys, idempotency keys, request
IDs). Encryption, key derivation, and TLS configuration are NOT in
scope — those are concerns of the services Nodus orchestrates, not of
Nodus itself.

---

## What Phase 0 already settled

From Decision 7:

- Three separate namespaces: `std:hash`, `std:encoding`, `std:secrets`
- Tightly scoped to orchestration needs
- One-shot for common case, streaming for large files
- Hash values formatted via methods: `to_hex()`, `to_base64()`,
  `to_bytes()`
- HMAC: key-first parameter order per RFC 2104
- Constant-time compare in `std:hash` (primary use is hash comparison)
- Legacy hashes (sha1, md5) included with prominent security warnings
- Out of scope: symmetric/asymmetric encryption, KDF (PBKDF2/Argon2/
  scrypt), TLS config, certificates, digital signatures

This doc resolves:

- Hash value type and accessor surface
- Streaming hash API (builder pattern + file convenience)
- HMAC function set across algorithms
- Constant-time compare input handling
- Encoding API surface (base64 variants, hex case, URL encoding modes)
- Secrets API surface (tokens, UUIDs)
- Implementation substrate (all Python stdlib)

---

## `std:hash` API surface

### Hash algorithms

Five algorithms supported across three function forms each (one-shot,
builder, file convenience):

| Algorithm | One-shot | Builder | File | Notes |
|---|---|---|---|---|
| SHA-256 | `hash.sha256(data)` | `hash.sha256_builder()` | `hash.sha256_file(path)` | Primary choice for general hashing |
| SHA-512 | `hash.sha512(data)` | `hash.sha512_builder()` | `hash.sha512_file(path)` | When 256-bit output is insufficient |
| BLAKE2b | `hash.blake2b(data)` | `hash.blake2b_builder()` | `hash.blake2b_file(path)` | Modern, faster than SHA-2 |
| SHA-1 | `hash.sha1(data)` | `hash.sha1_builder()` | `hash.sha1_file(path)` | **Legacy — cryptographically broken** |
| MD5 | `hash.md5(data)` | `hash.md5_builder()` | `hash.md5_file(path)` | **Legacy — cryptographically broken** |

15 hash functions total. The naming is symmetric: `<algorithm>` for
one-shot, `<algorithm>_builder` for streaming, `<algorithm>_file` for
file convenience.

### One-shot hashing

```nodus
let h = hash.sha256("hello world")
h.to_hex()  // "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
```

**Input types accepted:**

- `string` — encoded as UTF-8 before hashing
- `bytes` — hashed directly

**Returns:** a hash record (see below).

**Errors:** none for valid inputs. Invalid input types (numbers, maps,
nil) produce err with `kind: "type_error"`.

### Streaming hashing (builder pattern)

```nodus
let h = hash.sha256_builder()
h.update("chunk 1")
h.update("chunk 2")
h.update(bytes_value)
let digest = h.finalize()
print(digest.to_hex())
```

**Builder methods:**

| Method | Description |
|---|---|
| `b.update(data)` | Add data to the hash; data is string or bytes |
| `b.finalize()` | Compute the final hash; returns hash record. Builder is consumed and cannot be used after. |
| `b.algorithm` | Read-only field; returns algorithm name (e.g., `"sha256"`) |

**Reuse:** builders are single-use. Calling `update()` after `finalize()`
returns err with `kind: "state_error"`. Use a new builder for each
hash operation.

### File convenience

```nodus
let digest = hash.sha256_file("/path/to/large.bin")
print(digest.to_hex())
```

Reads the file in chunks internally (64KB chunks). Useful for large
files where loading into memory is wasteful. Returns the same hash
record shape as one-shot.

**Errors:** file not found, permission denied, etc. return err with
`kind: "io_error"`.

### Hash record

The value returned by all hash functions:

| Method / Field | Type | Description |
|---|---|---|
| `h.to_hex()` | string | Lowercase hex (e.g., `"b94d27..."`) |
| `h.to_hex_upper()` | string | Uppercase hex (e.g., `"B94D27..."`) |
| `h.to_base64()` | string | Standard base64 with padding |
| `h.to_base64_url()` | string | URL-safe base64 without padding |
| `h.to_bytes()` | bytes | Raw digest bytes |
| `h.algorithm` | string | Algorithm name (e.g., `"sha256"`) |
| `h.length` | int | Length in bytes (32 for SHA-256, 64 for SHA-512, etc.) |

The hash record is immutable. Format conversions return new strings/bytes
without modifying the hash.

### HMAC

Five HMAC functions matching the hash algorithm set:

```nodus
hash.hmac_sha256(key, message)
hash.hmac_sha512(key, message)
hash.hmac_blake2b(key, message)
hash.hmac_sha1(key, message)     // legacy
hash.hmac_md5(key, message)       // legacy
```

**Parameter order:** key first, message second. Matches RFC 2104.
Critically: **this is the order users typically get wrong.** API request
signing patterns often look like `sign(message, secret_key)` — reverse
of what HMAC actually takes. The function name is explicit about which
parameter is which.

**Input types:**

- `key`: string or bytes. Strings encoded as UTF-8.
- `message`: string or bytes. Strings encoded as UTF-8.

**Returns:** a hash record (same shape as plain hash), with
`h.algorithm` set to `"hmac-sha256"` etc.

**Streaming HMAC:** not supported in v4.0. The typical HMAC use case
is signing small messages (API requests, JWT segments). If real demand
for streaming HMAC surfaces, add as v4.x additive.

### Constant-time comparison

```nodus
let computed = hash.hmac_sha256(key, body)
let received = encoding.hex_decode(signature_from_header)
if hash.compare(computed, received) {
    // valid signature
}
```

**Function:** `hash.compare(a, b)` — constant-time equality check.

**Inputs accepted:**

- Two hash records
- Two bytes values
- Two strings (encoded as UTF-8 before comparison)
- Mixed: string + hash record, bytes + hash record, etc.

The library normalizes all inputs to bytes internally before
comparison.

**Returns:** `bool`. No err case. Mismatched lengths return `false`
rather than erroring, so a timing attacker cannot distinguish "wrong
length" from "wrong value" via err vs return.

**Why this lives in `std:hash`:** primary use case is hash comparison
(verifying HMACs, comparing content hashes). Could conceptually live
in a `std:compare` namespace, but Decision 7 placed it here.

### Security notes for legacy algorithms

**SHA-1:** Cryptographically broken since 2017 (Google SHAttered
attack). MUST NOT be used for:

- Digital signatures
- HTTPS certificates
- Password hashing (use a KDF instead, not in scope for v4.0)
- Any new security-critical application

Acceptable use cases:

- Git commit IDs (legacy; not a security guarantee)
- Hash table keys where collision is not a security issue
- Compatibility with legacy systems that require SHA-1

The function is included so users don't shell out to OpenSSL for
legacy interop. Function docstring includes a prominent security
warning.

**MD5:** Cryptographically broken since the early 2000s. MUST NOT be
used for any security purpose. Acceptable use cases:

- ETag generation for HTTP caching
- Checksums for non-security file integrity
- Compatibility with legacy systems

Same approach as SHA-1: included for interop, documented with security
warning.

---

## `std:encoding` API surface

### Base64

```nodus
encoding.base64_encode(data)        // standard base64 with padding
encoding.base64_decode(string)       // returns bytes

encoding.base64_url_encode(data)    // URL-safe base64, no padding
encoding.base64_url_decode(string)   // accepts URL-safe input
```

**Standard vs URL-safe:**

- Standard base64 uses `+`, `/`, and `=` (padding). Suitable for HTTP
  bodies, file data, anywhere URL-unsafe characters are allowed.
- URL-safe base64 uses `-`, `_`, and no padding. Suitable for query
  strings, JWT segments, anywhere `+`/`/`/`=` would be problematic.

**Input types for encode:** string (UTF-8 encoded first) or bytes.
**Output of encode:** string.
**Input of decode:** string.
**Output of decode:** bytes.

**Errors:** decode of invalid base64 (wrong alphabet, malformed
padding) returns err with `kind: "encoding_error"`,
`payload.category: "decode_error"`.

### Hex

```nodus
encoding.hex_encode(bytes)           // lowercase output
encoding.hex_encode_upper(bytes)     // uppercase output

encoding.hex_decode(string)          // accepts upper or lower (mixed too)
```

**Returns:** encode returns string; decode returns bytes.

**Errors:** decode of invalid hex (odd length, non-hex characters)
returns err with `category: "decode_error"`.

### URL encoding

Two distinct URL encoding modes because they serve different
contexts:

```nodus
encoding.url_encode(string)          // RFC 3986 component encoding
encoding.url_decode(string)          // decode percent-encoded

encoding.url_encode_form(map)        // application/x-www-form-urlencoded
encoding.url_decode_form(string)     // parse form-encoded string to map
```

**`url_encode` (RFC 3986 percent-encoding):**

- Encodes all characters except unreserved set (`A-Z`, `a-z`, `0-9`, `-`,
  `_`, `.`, `~`)
- Spaces encode as `%20`
- Equivalent to JavaScript's `encodeURIComponent()`
- Use for URL path segments and query parameter values

```nodus
encoding.url_encode("hello world")   // "hello%20world"
encoding.url_encode("a+b=c")          // "a%2Bb%3Dc"
```

**`url_encode_form` (application/x-www-form-urlencoded):**

- Same as RFC 3986 component encoding EXCEPT spaces encode as `+`
  rather than `%20`
- Takes a map of string-to-string-or-list, outputs `a=1&b=2&c=3` string
- For lists, generates repeated keys: `{tag: ["a", "b"]}` → `tag=a&tag=b`

```nodus
encoding.url_encode_form({"name": "Alice", "city": "Phoenix"})
// "name=Alice&city=Phoenix"

encoding.url_encode_form({"q": "hello world"})
// "q=hello+world"

encoding.url_encode_form({"tag": ["a", "b", "c"]})
// "tag=a&tag=b&tag=c"
```

**`url_decode_form`:** parses query strings or form bodies back to a
map. Multiple values for the same key produce a list:

```nodus
encoding.url_decode_form("a=1&b=2")
// {"a": "1", "b": "2"}

encoding.url_decode_form("tag=a&tag=b")
// {"tag": ["a", "b"]}
```

**Errors:** decode of malformed percent-encoding (e.g., `%XY`) returns
err with `category: "decode_error"`.

### Why URL encoding has two modes

`std:http`'s `query` option key (Decision 5 / `01-http-api.md`) uses
the form-encoded variant when building URL query strings, but URL path
segments use the component-encoded variant. Other contexts (constructing
arbitrary URLs from parts) need one or the other. Providing both makes
the right choice explicit at call sites; conflating them in a single
function (Python's `urllib.parse.quote` has a `safe` parameter to
control this) creates more confusion than clarity.

### What's NOT in `std:encoding`

- **JSON:** `std:json` already exists. Decision 7 didn't include JSON
  in encoding.
- **HTML / XML escape:** Out of scope per orchestration DSL identity.
  Workflows that produce HTML/XML are doing presentation work, which
  belongs to the components Nodus orchestrates.
- **Quoted-printable, uuencode, other historical encodings:** Out of
  scope. Use Python via embedding API if needed.

---

## `std:secrets` API surface

### Random bytes and integers

```nodus
secrets.random_bytes(n)              // n bytes of CSPRNG output
secrets.random_int(min, max)          // int in [min, max] inclusive
```

**`random_bytes`:** primary primitive. Cryptographically secure random
bytes from the OS CSPRNG (`/dev/urandom` on Unix, `BCryptGenRandom` on
Windows).

**`random_int`:** convenience for random integer selection within a
range. Uses rejection sampling to avoid modulo bias.

### Token generation

```nodus
secrets.token_hex(n_bytes)           // 2n hex characters
secrets.token_base64(n_bytes)         // standard base64 of n random bytes
secrets.token_urlsafe(n_bytes)        // URL-safe base64 without padding
secrets.token_alphanumeric(n_chars)   // n chars from [a-zA-Z0-9]
```

**Parameter semantics:**

- For `token_hex`, `token_base64`, `token_urlsafe`: the parameter is
  the number of random BYTES; output length depends on encoding.
- For `token_alphanumeric`: the parameter is the number of OUTPUT
  CHARACTERS.

This asymmetry is documented prominently. The hex/base64 helpers
follow Python's `secrets` module convention (bytes-in); alphanumeric
diverges because users care about output length, not entropy bytes.

**Typical use cases:**

- API keys: `secrets.token_hex(32)` → 64-char hex string (256 bits of
  entropy)
- Session tokens: `secrets.token_urlsafe(32)` → ~43-char URL-safe
  string
- Idempotency keys: `secrets.token_urlsafe(16)` → ~22-char URL-safe
  string
- Short tokens: `secrets.token_alphanumeric(8)` → 8-char alphanumeric

### UUID generation

```nodus
secrets.uuid_v4()                     // random UUID
secrets.uuid_v7()                     // time-ordered UUID
```

**UUID v4** (random): the most common UUID variant. 122 bits of random
data. Used for unrelated, unordered IDs (database primary keys, file
names, correlation IDs).

```nodus
secrets.uuid_v4()
// "550e8400-e29b-41d4-a716-446655440000"
```

**UUID v7** (time-ordered, RFC 9562): timestamp-prefixed UUID. The
first 48 bits encode milliseconds since Unix epoch; the remaining bits
are random. Used for time-ordered IDs (database keys where insert
order matters, event IDs in a stream).

```nodus
secrets.uuid_v7()
// "01967a3b-8e4c-7000-8000-abcdef012345"
//  ^ timestamp prefix             ^ random bits
```

**Why UUID is in `std:secrets`:** UUIDs are often used adjacent to
cryptographic tokens (request IDs, idempotency keys). They use the
same CSPRNG. Creating a separate `std:uuid` namespace for one or two
functions adds organizational overhead without clarity benefit.

**Not included: UUID v1, v2, v3, v5.**

- v1 / v2 embed the machine's MAC address (privacy concern)
- v3 / v5 are namespace-based hashes (not random; specialized use cases)
- All are rarely needed in modern systems

If real demand surfaces for any of these, add as v4.x additive.

---

## Pattern consistency with other stdlib namespaces

### Err record shape

All three crypto namespaces use the standard err record pattern:

```nodus
err {
    kind: "encoding_error" | "io_error" | "type_error" | "state_error",
    message: string,
    path: ..., line: ..., column: ..., stack: ...,
    payload: {
        category: string,
        input: string or bytes or nil,   # the input that caused the error (truncated for size)
        algorithm: string or nil          # for hash errors
    }
}
```

**Kind values:**

| Kind | When emitted |
|---|---|
| `"encoding_error"` | Decoding invalid base64, hex, URL encoding |
| `"io_error"` | File operations in `hash.*_file` functions |
| `"type_error"` | Invalid input type (number, map, nil where bytes/string expected) |
| `"state_error"` | Reusing a builder after `finalize()` |

The kind values are consistent with HTTP (`http_error`), subprocess
(`subprocess_error`), and time (`time_error`).

### Capability surface ceiling

Per the capabilities-not-orchestration principle:

**NOT included in `std:hash`:**

- Password hashing (KDF: PBKDF2, Argon2, scrypt). Use a service that
  owns password storage. Possibly `nodus-password-hash` registry
  library in v5.x.
- Encryption (AES, ChaCha20, RSA). Out of scope per Decision 7. Call
  an encryption service via HTTP/subprocess.
- Digital signatures (RSA, EdDSA). Out of scope.
- Certificate handling, TLS config. Out of scope.
- Hash with personalization / keyed hash for BLAKE2b. BLAKE2b in v4.0
  uses default parameters only. If real demand surfaces, add as
  additive option.

**NOT included in `std:encoding`:**

- Quoted-printable, uuencode, other historical encodings
- HTML / XML / JSON escape (JSON has its own namespace; HTML/XML out
  of scope)
- Character encoding conversion (UTF-8 to UTF-16, etc.). Use Python
  via embedding API if needed.

**NOT included in `std:secrets`:**

- Password generators (more than alphanumeric tokens, with specific
  character class requirements)
- Pronounceable random strings
- Wordlists / passphrase generation
- UUID v1, v2, v3, v5 (covered above)
- Cryptographic key generation (key sizes specific to algorithms;
  proper key management is out of scope per Decision 7)

### Reconsideration triggers

Scope expands if:

- Real user issues request specific additions (10+ across distinct
  use cases per addition)
- A v4.0 library implementation requires a primitive only cleanly
  provided by one of these namespaces
- The orchestration DSL identity changes (per LANGUAGE_VISION.md)

---

## Implementation outline

### Substrate: Python stdlib only

All three namespaces are implemented on top of Python stdlib modules
with no external dependencies:

```python
import hashlib       # for hash algorithms (sha256, sha512, blake2b, sha1, md5)
import hmac          # for HMAC variants
import secrets       # for CSPRNG (random_bytes, token_*, etc.)
import base64        # for base64 encode/decode
import binascii      # for hex encode/decode
import urllib.parse  # for URL encoding
import uuid          # for UUIDv4 (UUIDv7 needs implementation)
```

**No new dependencies in `pyproject.toml`.** Important: `std:hash`,
`std:encoding`, `std:secrets` add zero wheel size.

### Hash builder lifecycle

Builders wrap Python `hashlib` objects. The `update()` method delegates
directly. `finalize()` calls `digest()` and constructs a hash record.
After `finalize()`, the builder marks itself consumed; subsequent
`update()` or `finalize()` calls return err.

### UUIDv7 implementation

Python 3.14+ adds UUIDv7 to the stdlib `uuid` module. For earlier
Python versions (Nodus requires 3.9+), implement manually:

```
Layout (128 bits):
[0:48]   = Unix timestamp ms
[48:52]  = version (0111 = 7)
[52:64]  = 12 random bits
[64:66]  = variant (10)
[66:128] = 62 random bits

Total random: 12 + 62 = 74 bits
```

Implementation is ~20 lines of Python; no external dependency.

### Hash record implementation

Hash records are Nodus records (per Decision 9 of Phase 0 — records
with methods). Internal storage:

```python
{
    "_digest_bytes": bytes,
    "_algorithm": str,
    "_length": int,
}
```

Methods compute format conversions on demand. The record is immutable;
conversion methods return new strings/bytes without modifying state.

### File hashing

`hash.<alg>_file(path)` reads the file in 64KB chunks:

```python
hasher = hashlib.sha256()
with open(path, "rb") as f:
    while chunk := f.read(65536):
        hasher.update(chunk)
return hash_record(hasher.digest(), "sha256")
```

64KB is a balance between memory usage and read efficiency. Smaller
chunks (4KB) waste syscall overhead; larger chunks (1MB) waste memory
for small-file hashing.

### URL encoding character set

`url_encode` (RFC 3986):

- Safe characters: `A-Z`, `a-z`, `0-9`, `-`, `_`, `.`, `~`
- All others percent-encoded

`url_encode_form`:

- Same safe set as RFC 3986 component
- Space encoded as `+` instead of `%20`
- `=` and `&` are percent-encoded in values (they're separators in
  form-encoded output)

---

## Open implementation questions for Phase 3B

1. **Builder state representation.** Internal flag or sentinel for
   "consumed" state. Tentative: boolean flag; subsequent update/finalize
   raise err.

2. **Streaming HMAC user demand.** Not in v4.0 scope. Track issues
   requesting it; reconsider for v4.x if 10+ distinct use cases surface.

3. **UUIDv7 entropy quality.** Specification suggests at least 62 bits
   of randomness; verify Python `secrets` module provides sufficient
   entropy. Tentative: yes, `secrets.token_bytes(10)` provides 80 bits
   from the OS CSPRNG.

4. **`random_int` rejection sampling.** For uniform distribution
   without modulo bias. Tentative: use Python `secrets.randbelow()`
   pattern; well-tested.

5. **Hash record garbage collection.** Hash records hold a small bytes
   value (<=64 bytes for SHA-512). No special handling needed; standard
   Python GC suffices.

6. **`binascii` vs manual hex.** Python's `binascii.hexlify` is fast
   C code; use it. Manual implementation would be ~3x slower.

---

## MCP and A2A consumer validation

### nodus-mcp consumer needs

- ✓ Content addressing for MCP resources: `hash.sha256(content)` then
  `h.to_hex()` for resource ID generation
- ✓ HMAC for any MCP-level signing (currently not in spec, but future-
  ready)
- ✓ Token generation for OAuth state parameters (if/when MCP adds OAuth):
  `secrets.token_urlsafe(32)`
- ✓ Idempotency keys for request retries (not in spec, but standard
  pattern): `secrets.uuid_v7()`

### nodus-a2a consumer needs

- ✓ Task ID generation: `secrets.uuid_v7()` for time-ordered task IDs
  (A2A's primary ID format)
- ✓ Context ID generation: `secrets.uuid_v4()` for conversation
  identifiers
- ✓ Request signing (when A2A adds advanced auth in v0.2):
  `hash.hmac_sha256(api_key, request_body)`
- ✓ Webhook signature verification (when A2A adds push notification
  HMAC verification): `hash.compare(computed_sig, header_sig)` for
  constant-time check
- ✓ URL parameter encoding: `encoding.url_encode(path_segment)` for
  agent ID embedded in REST paths

Both libraries' cryptographic and encoding needs are covered by the
locked API surface.

---

## Migration impact

`std:hash`, `std:encoding`, and `std:secrets` are new namespaces in
v4.0. No migration from v3.x.

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

All three crypto namespaces (`std:hash`, `std:encoding`, `std:secrets`)
are implemented as Python-side builtin functions registered through the
existing builtin registry. Hash records are Nodus records (existing
type) with methods that format from underlying bytes. User code calls
all crypto functions via the existing `CALL_BUILTIN` opcode.

The frozen-bytecode contract from v1.0 is preserved by this design.
Compiled v3.x `.ndbc` files remain loadable in the v4.0 VM.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 7 (three crypto
  namespaces)
- `docs/design/v4/00-phase-0-decisions.md` Decision 9 (record types)
- `docs/design/v4/01-http-api.md` (sibling; `url_encode` and
  `url_encode_form` used by HTTP for query parameters and form bodies)
- `docs/design/v4/02-datetime-api.md` (sibling; UUIDv7 uses Unix epoch
  ms compatible with `time.epoch_ms`)
- `docs/design/v4/04-subprocess-api.md` (sibling; `shell_quote`
  parallels encoding's escaping helpers but lives in subprocess because
  shell-specific)
- `docs/language/LANGUAGE_VISION.md` principle #6 (capabilities not
  orchestration)
- `docs/language/DESIGN.md` § "Capability surfaces stay narrow"
- `docs/governance/LIBRARY_ECOSYSTEM.md` § "Not pursued: per-call
  orchestration options in stdlib"
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3B implementation handoff

When Phase 3B begins (crypto namespaces implementation), the following
artifacts are ready:

1. This design doc (`03-crypto-hashing-api.md`)
2. Decision 7 (Phase 0)
3. Six open implementation questions enumerated above
4. Substrate locked: Python stdlib only (`hashlib`, `hmac`, `secrets`,
   `base64`, `binascii`, `urllib.parse`, `uuid`)
5. Test surface to cover:
   - All 15 hash functions (5 algorithms x 3 forms)
   - All 5 HMAC functions
   - Hash record methods (to_hex, to_hex_upper, to_base64,
     to_base64_url, to_bytes, algorithm, length)
   - Constant-time compare with all input type combinations
   - Builder lifecycle (single-use, err on reuse after finalize)
   - File hashing (small, large, missing, permission-denied)
   - Base64 standard and URL-safe (encode + decode)
   - Hex lower and upper (encode + decode; decode accepts both cases)
   - URL encoding (RFC 3986 component vs form-encoded)
   - URL form encoding with map-to-list values
   - URL decoding to map (single and multi-value)
   - Random bytes and random int distribution
   - Token generation (hex, base64, urlsafe, alphanumeric)
   - UUIDv4 format compliance
   - UUIDv7 timestamp ordering and format compliance
   - Err categories: encoding_error, io_error, type_error, state_error

Estimated implementation effort: 1-2 days focused work. Most functions
are thin wrappers over Python stdlib. UUIDv7 requires modest
implementation; everything else is straightforward.

---

**Phase 1 doc 03-crypto-hashing-api.md: COMPLETE.**
