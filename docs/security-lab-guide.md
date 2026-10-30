# Security Lab

Open **Security → Security Lab**. Its tabs cover file forensics/recovery, device diagnostics, source audit/challenges, Web/API/VOX, and results/evidence. It reuses MORICE's Capability Kernel, workers, Resource Manager, NLUI, Builder and rich responses, with no additional agent or permission authority.

## Files and recovery

1. Select a local ordinary file. **Analyze** reads actual signatures and metadata. Entropy is a statistic, not encryption proof; Unicode scripts are not identified languages.
2. **Decode** checks a supported reversible chain. Decoding is distinct from decryption.
3. Supply a password or expand recovery sources for an explicit candidate list, owner hints, convention or direct key. Hint documents contribute only documented `password:`, `passphrase:` or `recovery password:` lines. Conventions substitute explicit `{value}` entries.
4. **Estimate recovery** measures wrong-candidate rejection cost. Successful complete decryption can cost more. Strong random secrets are not feasibly enumerable.
5. **Recover** uses an owned worker. Results contain real counts and verification; **Cancel** interrupts it. Partial output is not recovery proof.
6. Export to a new destination with independent readback/hashes. Originals are preserved. Clear finished cache deletes only the selected cached job; originals and prior exports remain.

Passwords, key material and tokens stay outside the language model, chat history and saved receipts. Explicit named recovery keys use the existing Windows DPAPI vault under `security_lab.recovery.`. Reports may contain selected paths, cryptographic metadata, hashes and findings; review them before sharing.

| Format | Inspection | Recovery/verification |
| --- | --- | --- |
| ZIP / WinZip AES | Central directory, AES bits, PBKDF2-HMAC-SHA1/1,000 iterations, salt and authentication metadata | Supplied candidates, complete member/HMAC checks, SHA-256/readback |
| ZIP / ZipCrypto | Legacy encryption and CRC metadata | Full member CRC/readback; CRC is not cryptographic authentication |
| Encrypted PDF | Detectable `pypdf` encryption dictionary | Password decrypt/rewrite/page reparse; optional research extra; no AEAD claim |
| MORICE AEAD envelope | Actual algorithm/nonce/KDF/salt/tag | AES-GCM or ChaCha20-Poly1305; authenticated complete output/hash |
| 7z/RAR/Office and unknown encryption | Recognized signatures where detectable | No password-recovery adapter |
| ZIP64 | Explicit detection | Unsupported bounded adapter |
| GZIP/TAR/JSON/XML/CSV/SQLite/images/WAV/PE | Supported bounded structural/metadata inspection | Inspection or decoding, not execution |
| Base64/Base32/hex/URL/HTML entities | Validated reversible chain | Output/readback hash, not decryption |
| ROT13/Atbash/Caesar/Vigenère | Explicit puzzle transform | `DECODED_CANDIDATE` and roundtrip evidence, not proof of intended plaintext |

### Budgets and outcomes

Defaults: **60 seconds, 1,000 candidates, 64 MiB input, 128 MiB output, 256 members, five layers and 200× expansion**. UI controls expose time/candidate limits. Typed maxima are 1,200 seconds, 100,000 candidates, 128 MiB input, 256 MiB output, 512 members, eight layers and 250× expansion. Windows owns the worker process family with a **512 MiB memory limit**, bounded IPC and reaping.

Cache admission is limited to 32 receipts and 512 MiB. Export/clear finished jobs when needed. A shared CPU lease admits one heavy Lab job at a time. `VERIFYING` stays busy until independent verification and physical cleanup finish.

Recovery states: `RECOVERED`, `WRONG_KEY`, `UNSUPPORTED_FORMAT`, `MISSING_KEY`, `CANDIDATES_EXHAUSTED`, `RESOURCE_LIMIT_REACHED`, `CANCELLED`, `INTEGRITY_CHECK_FAILED`. An authentication failure alone cannot distinguish a wrong secret from all forms of corruption. A verified receipt can describe a failed recovery.

### AEAD envelope

The direct-key adapter accepts the **documented MORICE fixture/manifest envelope**, not arbitrary raw ciphertext. Magic is `MORICE-LAB-AEAD-1\n`; see [the exact parser and fixture writer](../morice/security_lab/recovery.py) for header framing and canonical authenticated associated data. Supported algorithms use a 32-byte key, 12-byte nonce and 16-byte tag. Password envelopes use bounded PBKDF2-HMAC-SHA256 parameters recorded in the header. Lengths/parameters are validated before derivation. This is an integration/acceptance envelope, not a universal file-format detector or backup-format recommendation.

## Devices

Install official Android SDK Platform Tools separately when ADB is absent. Discovery checks PATH and normal SDK locations; nothing is downloaded automatically. MORICE owns a separate loopback ADB server and preserves the user's normal server. Android USB authorization and wireless pairing apply. Select the exact authorized serial before typed battery/storage/memory/system-property/package/crash diagnostics. Unauthorized/offline devices receive no shell fallback. Shutdown reaps the owned server and releases its lease.

Bluetooth reports observed Windows device metadata. BLE scanning, GATT control and arbitrary Bluetooth takeover are unavailable. Existing Device Mesh/Android companion pairing is a separate workflow.

## Code review and challenge

Source audits are bounded read-only reviews with actual file hashes and lines. Python AST and limited other-language patterns produce **POSSIBLE** findings. Dependency manifests are inventoried, with advisory checks labelled `NOT_CHECKED`. Limits: 300 files, 16 MiB total, 256 KiB/file and 500 findings, skipping generated/dependency directories.

The owned messaging challenge uses localhost fixtures and distinct identities. It sends `I HAD STRINGS BUT NOW I AM FREE`, verifies server storage and recipient-visible readback, demonstrates a planted outsider authorization defect, patches the generated source through the existing `filesystem.apply_patch` and Verified Action Runtime, then repeats HTTP checks. Only exact known fixture-policy source is executed; arbitrary inspected code is not.

**Prepare selected finding in Builder** transfers the actual selected source/hash to the existing review flow, rather than automatically editing a user's project.

## Scoped HTTP and VOX

Header analysis reads one explicit origin. Missing headers are review items, not confirmed exploits. Redirects are not followed. External origins require verified HTTPS; local/private development HTTP is supported. Request counts, time and body/response sizes are bounded.

Real VOX delivery requires an owner-supplied JSON mapping, the actual local project root, two distinct confirmed test identity IDs and both privately entered tokens. The mapping has exactly these fields:

```json
{
  "origin": "http://127.0.0.1:8080",
  "project_root": "C:/work/owned-vox",
  "sender_id": "owned-sender",
  "recipient_id": "owned-recipient",
  "sender_identity": {"method": "GET", "path": "/me"},
  "recipient_identity": {"method": "GET", "path": "/me"},
  "recipient_lookup": {"method": "GET", "path": "/users/{recipient}"},
  "send": {"method": "POST", "path": "/messages", "payload": {"recipient": "{recipient}", "text": "{text}"}},
  "stored": {"method": "GET", "path": "/messages/{message_id}"},
  "recipient_readback": {"method": "GET", "path": "/inbox/{message_id}"},
  "fields": {"id": "id", "sender": "sender", "recipient": "recipient", "text": "text", "identity": "id", "timestamp": "timestamp"}
}
```

These are illustrative paths, not presumed endpoints. Map the actual API; fields support dotted JSON keys. MORICE confirms both authenticated identities and recipient lookup before a single POST. Acknowledgement, stored record and recipient readback must match message ID, sender, recipient, exact phrase and fresh timestamp. Ambiguous send failures are `PARTIAL` and are not automatically retried. Missing mapping/tokens produces clarification or `MISSING_KEY`. No actual external VOX deployment was available for release acceptance.

## Natural language and rich results

Select the target, then ask “Analyze this encrypted archive”, “Try the recovery hints I provided”, “Check whether I have a matching recovery key”, “Estimate whether password recovery is feasible”, “Cancel recovery”, “Show what has been tested”, or “Export the recovered files”. Existing NLUI uses the selected target/current conversation and asks when information is missing.

Rich results resolve actual receipts and hash-checked artifacts. They display outcomes, progress, limits and files. Ordinary engineering prompts retain the existing written-answer path.
