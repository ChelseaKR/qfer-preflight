# Source manifest

A retrieval date and a SHA-256 for every published document this project
cites or reads. Its purpose is to turn the README's warning, "published
documents change, and when they do this tool is wrong until it is updated",
from an act of faith into a procedure: re-download a document, compare its
hash against this file, and a silent revision announces itself before it can
make a quote or a header row wrong without anyone noticing.

`tests/test_source_manifest.py` holds this file against the profiles: every
instruction URL, template URL and workshop deck URL the code cites must appear
here with a well formed hash and date. The runtime never reads this file.
Nothing here is fetched at validation time; the hashes are dev-time snapshots
of documents that live on the Commission's site, recorded so drift is visible,
not so behaviour can depend on them.

## What to do when a hash stops matching

1. Stop. Do not patch the hash first. A changed hash means the published text
   moved, and any rule quoting that text may now be quoting a superseded
   revision.
2. Download the new copy and diff what changed, by reading both versions.
3. If a quoted passage changed wording, update the transcription deliberately:
   rules carry quotes verbatim, defects included, per
   `docs/adr/0002-transcribe-published-artifacts-verbatim.md`.
4. If the change alters what a rule reports, that is a severity or behaviour
   decision: write the ADR, update the tests, record it in the changelog.
5. Only then update the `sha256` and `retrieved` lines here, with the changelog
   entry naming which revision changed.

## Manifest

### CEC-1306A instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf
- sha256: b32dbdfc514798f8b2738f3142883aaa020a054fdccaaf1391ce32e63f8ef648
- retrieved: 2026-08-26
- cited by: CEC-1306A-S1 and CEC-1306A-S2 profiles; most field rules

### CEC-1306B instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306B_Instructions_07142025_ada.pdf
- sha256: 0fdcc6faf6a1b1a746dcfe4379fc775b6adece9a8509097ddfbf82ccf1ce1804
- retrieved: 2026-08-26
- cited by: CEC-1306B profile; QP015, QP022

### CEC-1308B instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1308B_Instructions_07142025_ada.pdf
- sha256: 7235933d9092df86f7f74e9c56fb70bb53cfeadc73e0b7735758992dc8220498
- retrieved: 2026-08-26
- cited by: CEC-1308B-S1 profile; QP016, QP023

### CEC-1308C instructions, rev. 07/14/2025

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1308C_Instructions_07142025_ada.pdf
- sha256: b75410d7c9f430e89063febc55c998e2208bd7c98aebed856e8428da0a1b152c
- retrieved: 2026-08-26
- cited by: CEC-1308C profile; QP015

### CEC-1306A Schedule 1 CSV template

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306A_S1_template.csv
- sha256: def26aba211105ca2f2e725f8496416d6727fdc814943a5d21753e9001643d09
- retrieved: 2026-08-26
- cited by: QP002 for CEC-1306A-S1; source of the transcribed header row

### CEC-1306A Schedule 2 CSV template

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306A_S2_template.csv
- sha256: aead545f8d3a7243067e583b677f7d9bdbfc6abea7aacb18a9d24a6aa7d975d0
- retrieved: 2026-08-26
- cited by: QP002 for CEC-1306A-S2; source of the transcribed header row

### CEC-1306B CSV template

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1306B_template.csv
- sha256: 377f56b2a50bff79eaf68dbcab83fc5c078677c7b7c733798e096f9d6201f83a
- retrieved: 2026-08-26
- cited by: QP002 for CEC-1306B; source of the transcribed header row

### CEC-1308B Schedule 1 CSV template

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1308B_S1_template.csv
- sha256: 88a9b82e6f23c4918afa46c54ef160ae73472c2e8717a8224007e647fea49783
- retrieved: 2026-08-26
- cited by: QP002 for CEC-1308B-S1; source of the transcribed header row

### CEC-1308C CSV template

- url: https://www.energy.ca.gov/sites/default/files/2025-07/1308C_template.csv
- sha256: f40e7994cfe727547e6fbc24e80d417d6e946f0f5ba5cb623739238a79f86ce3
- retrieved: 2026-08-26
- cited by: QP002 for CEC-1308C; source of the transcribed header row

### QFER DSP Workshop slides, June 24, 2025

- url: https://www.energy.ca.gov/sites/default/files/2025-06/QFER_DSP_Workshop_ada.pdf
- sha256: 81986ce99c05e36dc6e135e58bfc4b6dd34a4a471a291ff242a178533cc736f0
- retrieved: 2026-08-26
- cited by: QP024, QP025

### Previous revision of the CEC-1306A instructions (2020)

- url: https://www.energy.ca.gov/sites/default/files/2020-08/1306A_Instructions_ada.pdf
- sha256: 4fa7cde04cc4df660bc47bc1507c76c4f535e782f689f987a4a875708fced807
- retrieved: 2026-08-26
- cited by: no rule. Read for one purpose only, in
  `docs/adr/0005-customer-type-o-re-examined-and-held.md`: to establish what
  the Customer Type list said before the July 2025 revision.

### Energy Consumption Data Files, county table

- url: https://www.energy.ca.gov/filebrowser/download/8144
- sha256: 142a104d6deebc5c789c1dfcc51387f8681891e4e300f787510cf8b7c23d67ca
- retrieved: 2026-08-26
- cited by: no rule. Corroborates the county code set; see
  `docs/adr/0008-county-numbers-corroborated-by-a-second-cec-dataset.md`.
- expected to change: yes, with a known cause. This file's two defective 2024
  rows, which put county 33 on IMPERIAL and SAN DIEGO, were reported to the
  Commission and confirmed on 2026-08-26 as a data transformation error,
  corrected but not yet posted. When this hash stops matching, check that
  correction first before treating the drift as a revision. Nothing cited
  depends on this file.

### Energy Consumption Data Files, utility table

- url: https://www.energy.ca.gov/filebrowser/download/8168
- sha256: b2a8a8d5863cca938ce3cf6c41c6ff941c20640a977952e75e449732f19460c2
- retrieved: 2026-08-26
- cited by: no rule. Read while closing part of the QP018 search; publishes no
  NAICS, customer type or rate class list.

## Not a document

Correspondence with the Commission's Consumption Data Analytics Unit,
2026-08-17 to 2026-08-26, answered three questions this project had asked:
where the "Valid NAICS codes" list is published, whether the portal accepts a
zero padded County Number, and whether Customer Type `O` is still accepted.

It carries no url, no hash and no retrieval date, because it is not
retrievable. That is the point of the entry rather than an omission from it.
No rule cites it, no rule may, and nothing in the manifest ritual applies to
it. It is recorded because it closed searches that the README and three rule
reasons describe as closed, and a reader is owed the reason. See
`docs/adr/0009-authoritative-answers-that-cannot-be-cited.md`.

## Deliberately absent

The QFER program page,
<https://www.energy.ca.gov/rules-and-regulations/energy-suppliers-reporting/quarterly-fuel-and-energy-reporting-qfer>,
carries no hash. It is an HTML page that changes routinely for reasons unrelated
to the filings, it grounds no rule, and a hash of it would cry wolf. The
documents above are what the citations resolve to.
