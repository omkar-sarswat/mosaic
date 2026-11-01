# External benchmark data

Public datasets made by others, downloaded on 2026-10-16 to test DRISHTI on data its own generator did not make. Each dataset sits in its own folder and is read only by `bench/`. It is never imported by the running system. Treat the files as untrusted input.

| Folder | Dataset | Source | Licence |
|---|---|---|---|
| `montagna/` | Sicilian Mafia "Montagna Operation": phone-call and meeting networks with roles from the 2007 Messina court order (anonymised) | Zenodo, doi:10.5281/zenodo.3938818 | CC-BY-4.0 |
| `caviar/` | Project Caviar (Montreal importers 1994-96): start, middle and end communication networks | R package `onadata` (K. McNulty), after Morselli (2009), *Inside Criminal Networks* | as distributed in `onadata` (CRAN, MIT) |
| `febrl/` | FEBRL datasets 2, 3, 4a, 4b (synthetic person records with known duplicates) | Christen (ANU); via the `recordlinkage` toolkit repository | BSD-3 (recordlinkage); FEBRL data freely available for research |
| `aksharantar/` | AI4Bharat Aksharantar transliteration pairs for Hindi, Marathi, Gujarati, Punjabi, Bengali, Urdu, Tamil and Telugu (`test/` holds the extracted test splits) | huggingface.co/datasets/ai4bharat/Aksharantar | CC0 (mined), CC-BY (manual) |
| `ibm_aml/` | IBM Transactions for Anti-Money Laundering, HI-Small and LI-Small only | Kaggle: ealtman2019/ibm-transactions-for-anti-money-laundering-aml (downloaded with the user's own Kaggle login; HI-Small and LI-Small transactions, accounts and patterns, 1.2 GB) | Community Data License Agreement - Sharing 1.0 |

Results are in `docs/research/10-external-benchmarks.md`.
