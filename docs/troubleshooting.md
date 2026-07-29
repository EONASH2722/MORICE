# MORICE Troubleshooting

## MORICE does not start

Run the packaged EXE from `dist\MORICE`. Check `%APPDATA%\MORICE\runtime\logs`
and `last-update-result.json` under the platform update folder. Use
`python -m morice.cli` only for source-level diagnosis.

## Model will not load

Confirm the file has a `.gguf` extension and valid GGUF metadata. Compare its
estimated VRAM with the Hardware page. Lower GPU layers or select a smaller
quantization when VRAM is tight.

## Project output is not applied

Choose a valid work folder outside the application directory. Review the diff
and approve that exact patch. If the file changed after preview, request a new
preview; MORICE intentionally refuses stale writes.

## Visualization is unavailable

Open Diagnostics and inspect Renderer registry. MORICE does not replace a
failed graph or simulation with descriptive text pretending that it rendered.

## Plugin fails

Open Plugin Center diagnostics. Check compatibility, dependencies, permission
review, process exit, and timeout. Disable the plugin or roll back to its
previous verified package.

## Update fails

Inspect `last-update-result.json`. MORICE rejects a mismatched byte count,
SHA-256 checksum, unsafe ZIP path, symbolic link, unsupported package type, or
package without `MORICE.exe`. Portable updates preserve rollback copies.

## Secure backup cannot be opened

Encrypted backup is tied to the Windows user through DPAPI. Restore it from
the same Windows account. MORICE has no insecure plaintext fallback.
