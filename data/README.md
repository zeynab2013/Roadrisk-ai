# Data directories

These directories separate inputs by origin. A local collision extract and codebook may be present after `python -m roadrisk.data download`. Those files stay gitignored. The accepted digests are in `configs/data_manifest.json`.

| Directory | What belongs here | Git policy |
| --- | --- | --- |
| `raw/` | Publisher files, stored exactly as downloaded | Ignored, except this placeholder |
| `external/` | Reference data from a second publisher, such as traffic counts or boundary files | Ignored, except this placeholder |
| `processed/` | Feature tables written by `python -m roadrisk.features build` | Ignored, except this placeholder |
| `synthetic/` | Generated rows used to test code | Ignored, except this placeholder |
| `models/` | Trained pipelines, metrics, and registry metadata | Ignored, except this placeholder |

Rules:

- Raw files stay immutable. Cleaning writes a new processed artifact.
- Synthetic rows are for tests and pipeline checks. Reported model metrics use the held-out real evaluation split only.
- Dataset licence, source URL, download date, and checksum are recorded before a file is used. See [data strategy](../docs/data-strategy.md).
- Paths are configured in code from the environment once configuration exists. They are not hard-coded in later modules.
