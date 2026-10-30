# Security Lab 0.12.0: validation and coverage

This report distinguishes implemented operations, owned-fixture acceptance and integrations that still need real hardware or service configuration. The release name is **0.12.0 (UNLEASHED)**. It does not certify universal decryption, unrestricted device control, a live VOX service or exploit coverage.

## Observed native acceptance

The production Windows window ran an owned 121-candidate authenticated password recovery in **3.540 seconds**, while the actual globe painted **132 frames**. The correct final candidate recovered authenticated plaintext. This is observed work/paint activity, not a GPU timestamp benchmark or guaranteed compositor frame rate.

All **17 routes** opened under **White, Pitch Black and Glass**. Actual window sizes matched **720×580, 1366×840 and 1920×900**. Recovery, file inspection, source review, chat routing and the actual generated-source repair were exercised. Callback errors: **zero**. Shutdown: clean, **zero remaining resource leases and zero pending workers**. The screenshots in [the README](../README.md) are actual native captures from owned fixtures.

The installed official **ADB 37.0.1** started on a separate ephemeral server port. Observed listening address: **127.0.0.1 only**. Device listing completed with **zero attached devices**, and the owned server stopped afterward. This caught and corrected Windows ADB's unsupported explicit-listener-hostname syntax. No phone diagnostics or wireless pairing is certified by this discovery check.

Windows Bluetooth metadata returned **26 present records**. Device names/addresses remain local and are omitted here. This demonstrates metadata enumeration only, not physical pairing, BLE access or control.

## File timing samples

Owned generated local inputs, measured on the development host:

| Operation | Input bytes | Wall time |
| --- | ---: | ---: |
| Inspect text sample | 1,170,000 | 0.081 s |
| Decode Base64 | 1,560,000 | 0.684 s |
| Inspect structured JSON | 382,274 | 0.107 s |

These are a single observed run, not a cross-machine performance guarantee. Script detection is bounded to its sample; scripts do not establish language. A text file with no binary signature can correctly retain an UNKNOWN binary-format classification.

## Tests and failure boundaries

The focused Security Lab suite contains **64 tests** covering actual cryptographic fixtures, full readback, wrong keys, missing random secrets, corrupted data, unsupported formats, cancellation, candidate/resource limits, actual process-family memory limits, path/member validation, original preservation, export scope, secret redaction, conversation isolation, source repair, API identities/readback, native UI and the verification/resource-release race.

Full-suite and packaged-build totals are recorded in the release's **MORICE-v0.12.0-Validation.json** and SHA-256 manifests. Those receipts bind checks to the exact source and executable; public and private packages are checked separately. Prior-release validation is not substituted for current executable acceptance.

## Requested audit coverage

“Owned fixture” means a generated local test target. “Conditional” identifies an implemented adapter that needs actual external setup. “Unavailable” identifies work not implemented/certified; it is not a passing test.

| # | Audit topic | Result and evidence scope |
| ---: | --- | --- |
| 1 | Existing architecture | Reuses RuntimeServices, Capability Kernel, registry, workers and Resource Manager |
| 2 | Existing security | Existing Security workspace, permissions and action runtime preserved |
| 3 | Module architecture | Typed local security_lab adapter; no new agent/runtime owner |
| 4 | Permission model | Existing controller and exact one-use grants; explicit denials remain denied |
| 5 | Target scope | Selected local paths, exact device serial or one configured HTTP origin |
| 6 | File detection | Actual signatures, hashes and supported structural parsers |
| 7 | Encoding support | Validated Base64/Base32/hex/URL/HTML/GZIP chain fixtures |
| 8 | Compression | Bounded ZIP/TAR/GZIP metadata/decoding; expansion/member limits |
| 9 | Language detection | Encoding and Unicode scripts; linguistic language inference unavailable |
| 10 | Binary inspection | Bounded PE/header and known signature metadata; no arbitrary execution |
| 11 | Encryption classification | Detectable ZIP/PDF/AEAD algorithm/KDF/salt/tag metadata |
| 12 | Authorized decryption | Real supplied-password/key ZIP/PDF/AEAD operations |
| 13 | Unsupported decryption | Explicit 7z/RAR/Office/ZIP64/raw-ciphertext limits |
| 14 | Cryptographic verification | Actual AES HMAC/AEAD tags, full readback/hash; legacy CRC limitations explicit |
| 15 | Unknown formats | UNKNOWN/UNSUPPORTED_FORMAT without invented plaintext |
| 16 | File benchmarks | Owned measured samples above |
| 17 | Android ADB | Actual installed SDK/server/list discovery passed; no phone attached |
| 18 | Wi-Fi pairing | Implemented official pairing/connection adapter; physical pairing untested |
| 19 | ADB diagnostics | Exact-serial typed commands; contract fixtures; physical results unavailable |
| 20 | Debugging disabled | Unauthorized/offline fixture blocks diagnostics and device substitution |
| 21 | Bluetooth | Actual Windows metadata enumeration; BLE/GATT control unavailable |
| 22 | Companion | Existing paired Device Mesh unchanged; no new companion certification |
| 23 | Device permissions | Existing connected_devices authority and Android authorization |
| 24 | Device results | Actual zero-device discovery; no simulated phone data passed as real |
| 25 | Static analysis | File/line/hash evidence; findings remain POSSIBLE |
| 26 | Dependency analysis | Actual manifest inventory; advisory/CVE queries NOT_CHECKED |
| 27 | Dynamic tests | Owned localhost HTTP challenge and independent repair retest |
| 28 | Network scoping | One exact origin, no redirects, bounded requests/bodies/time |
| 29 | Finding verification | Planted unauthorized read reproduced before repair |
| 30 | False positives | Static patterns distinct from reproduced authorization failure |
| 31 | Remediation | Actual generated authorization.py patched through filesystem.apply_patch |
| 32 | Regression | Outsider read 200 before / 403 after; legitimate recipient retains access |
| 33 | CTF runner | One bounded owned messaging challenge; no general exploit agent |
| 34 | Seeded challenge | Actual isolated identities, sessions, storage and HTTP server |
| 35 | Live VOX architecture | Unavailable: no actual VOX source repository found/configured |
| 36 | VOX environment | Owned API fixture validated; actual deployment not tested |
| 37 | Account authorization | Mapped identity checks tested on owned API; live tokens absent |
| 38 | Message delivery | Exact phrase actually stored/delivered in owned fixtures only |
| 39 | Recipient verification | Actual ID/sender/recipient/content/timestamp comparison |
| 40 | Security negatives | Unauthenticated, invalid-session, impersonation and outsider tests on owned target |
| 41 | VOX repair | Owned planted source fixed/retested; no live VOX source modification claimed |
| 42 | NLUI | Selected target, clarification, actual job execution, cancel/status/export |
| 43 | Memory | Existing retained chat integration; secret material excluded from model/history |
| 44 | Rich responses | Actual receipt/artifact source, hashes and conversation checks |
| 45 | Globe/UI | Three themes × 17 routes and three actual native window sizes |
| 46 | Private data | Transient candidates/tokens; explicit DPAPI recovery-key namespace |
| 47 | Boundary audit | Traversal, output limits, no-overwrite, exact grants and redaction fixtures |
| 48 | Performance | Measured native workload and local file timing; no invented GPU/quality claims |
| 49 | Added tests | Six focused test modules, 64 tests |
| 50 | Targeted tests | Actual focused suite passed; catalog/source-repair checks repeated after fixes |
| 51 | Full regression | Exact-source final result in distributed Validation.json |
| 52 | Candidate build | Separate public and private PyInstaller directories |
| 53 | Frozen native startup | Production window, source/asset parity, actual packaged crypto and repair probes |
| 54 | Private dist | Promoted only after regression, parity, startup and policy checks; local receipt |
| 55 | Limits | Unsupported formats/providers, no physical phone or live VOX certification |
| 56 | Added files | security_lab package, six test modules, guides and fresh screenshot set |
| 57 | Modified files | Existing runtime/NLUI/rich-source adapters, launcher, build metadata, docs and website |
| 58 | Source control | Final commit/tag bound by release manifest and exact-commit cloud checks |
| 59 | Scorecard | Verified owned operations and conditional/unavailable integrations stated separately; no invented competition score |
| 60 | Final verification | Release manifest, validation receipt, package audit and SHA-256 asset manifests |

## Independent review and package checks

The full regression caught a missing verification description in the new NLUI catalog. A repeated owned HTTP challenge exposed a Windows connection reset caused by rejecting a POST before draining its bounded body. Both were fixed. Native acceptance exposed premature completion before physical CPU release; a delayed-verifier regression now asserts the intermediate state and immediate subsequent-job admission.

Each frozen candidate must match the current Python module code and bundled assets. Its owned native profile exercises actual ZIP correct/wrong passwords, missing/direct keys, the source repair, existing chat/LaTeX/chart behavior, globe rendering and clean shutdown. The wheel is inspected against source and installed into a separate Python 3.12 environment without system site packages; fresh dependency resolution is a separate cloud check.

Public packages exclude the local private answer/content override, model weights, credentials and runtime receipts. The existing local model selections/data are preserved during dist promotion. The override does not change a model's learned behavior or remove action authorization, integrity verification, resource budgets or Android pairing.

## Reference contracts

- [Security Lab guide and exact API mapping](security-lab-guide.md)
- [Official Android ADB command contract](https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/user/adb.1.md)
- [pyzipper implementation](https://github.com/danifus/pyzipper)
- [cryptography AEAD interface](https://cryptography.io/en/46.0.5/hazmat/primitives/aead/)
