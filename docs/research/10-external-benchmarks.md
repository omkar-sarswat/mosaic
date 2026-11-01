# 10 · External benchmarks: data DRISHTI did not generate

*Measured 16 Oct 2026. Everything else in this research pack is measured on DRISHTI's own synthetic worlds. Those results show that the system does what it was designed to do. They cannot show how it compares with anything else, because the data, the planted networks and the detectors share one set of assumptions. This note tests DRISHTI on public data made by other people, with known answers. The sources and licences are listed in `data/external/README.md`. Reproduce with `python -m bench.<name>`.*

## 1. Real criminal networks: key players and communities (`bench/criminal_networks.py`)

The test runs the product's own network analysis, `web/src/lib/network-analysis.ts` (the code behind the Network view's brokers, dense core, cut points and communities), on real anonymised networks.

**Montagna (Sicilian Mafia, Messina 2007).** The networks cover phone calls and meetings among suspects. The court order names each person's role.

The question is whether the product's measures put the people named as bosses, deputy bosses and executives at the top. ROC-AUC is the probability that a leader is ranked above a non-leader (0.5 is chance). Precision@k is the share of leaders among the top k, where k is the number of leaders. Degree (number of contacts) is the naive baseline.

| Network | People | Leaders | Betweenness (brokers): AUC / P@k | k-core: AUC / P@k | Degree baseline: AUC / P@k |
|---|---|---|---|---|---|
| Phone calls | 95 | 10 | 0.724 / 0.50 | 0.676 / 0.30 | 0.731 / 0.50 |
| Meetings | 95 | 15 | **0.772 / 0.53** | 0.685 / 0.33 | 0.759 / 0.40 |
| Combined | 144 | 16 | 0.765 / 0.50 | 0.744 / 0.38 | **0.790** / 0.44 |

Three further measures:
- **Communities and families.** Louvain communities against family membership (people with a known family) give ARI 0.37-0.48 and NMI 0.57-0.60. That is moderate agreement: the algorithm splits a family into sub-groups.
- **Cut points.** Leaders are 5-8 of the 10-15 cut points.
- **Victims.** Entrepreneurs, mostly extortion victims, make up 14-22% of the dense core against 21-26% of the network, so the core does not attract them.

**Caviar (Montreal, 1994-96).** N1 is the documented principal trafficker. He ranks 1st by betweenness in the first two phases and 2nd at the end, after the network reorganised under seizures. N3, his broker, ranks only 7th to 23rd.

**Reading.** The key-player measures work (AUC 0.72-0.77), but they are **no better than counting contacts**. This matches the criminology of covert networks: leaders insulate themselves (Morselli 2009). Leader identification is therefore an open problem for DRISHTI. It is not a solved one, and it will not be tuned on this single case, which would be overfitting. A fair next test needs a second labelled network.

## 2. Indian names across scripts (`bench/names_aksharantar.py`)

The data is AI4Bharat Aksharantar test pairs from AK-NEI, Indian named entities written by people in an Indian script and in English. "Same" means DRISHTI's comparator rates the pair exact or phonetic, which is what the resolver counts as name agreement. Hard negatives use the most similar-looking English word from another pair.

| Script | Pairs | DRISHTI recall | False match: random / hard | Plain transliteration recall | Jaro-Winkler ≥ 0.9: recall / false match hard |
|---|---|---|---|---|---|
| Hindi | 1,188 | **0.857** | 0.000 / 0.068 | 0.448 | 0.716 / 0.083 |
| Marathi | 1,247 | **0.862** | 0.002 / 0.087 | 0.430 | 0.698 / 0.108 |
| Gujarati | 1,481 | **0.866** | 0.001 / 0.071 | 0.450 | 0.721 / 0.084 |
| Punjabi | 1,234 | **0.853** | 0.001 / 0.074 | 0.303 | 0.605 / 0.087 |
| Telugu | 1,347 | **0.877** | 0.000 / 0.079 | 0.454 | 0.733 / 0.091 |
| Bengali | 1,639 | 0.782 | 0.001 / 0.071 | 0.442 | 0.705 / 0.079 |
| Tamil (before / **after** fix) | 1,216 | 0.479 / **0.887** | 0.001 / 0.073 | 0.180 | 0.451 / 0.070 |
| Urdu (before / **after** fix) | 1,174 | 0.000 / **0.750** | 0.001 / 0.051 | 0.071 | 0.370 / 0.037 |

**Reading.**
- **The main scripts.** For Hindi, Marathi, Gujarati, Punjabi and Telugu, DRISHTI finds 12-25 points more true matches than string similarity, with fewer false matches on look-alikes.
- **Tamil: 0.48 to 0.89.** Tamil script does not mark voicing (one letter for k/g, t/d, p/b, s/ch/j), so a Tamil-script name and its English spelling differ exactly there. When either record is in Tamil script, names now compare on a key with voicing merged, and blocking adds voicing-merged blocks for pairs with a Tamil-script member only. No other language's candidate pairs grow.
- **Urdu: 0.00 to 0.75.** DRISHTI did not read Perso-Arabic script at all. It now transliterates the consonants and the long vowels (alif, waw, yeh), drops the optional short-vowel marks and handles the positional letters (word-final heh, ain).
- **Look-alikes stay apart.** For both scripts the false-match rate on random pairs stays at or below 0.1%.
- **How the fixes were made.** Both were developed on Aksharantar's training split (Wikidata, Existing and Dakshina pairs, 4,000 per script) and checked once on the test split. Development recall was Tamil 0.865 and Urdu 0.676.
- **No effect on the Indian synthetic worlds.** On the four held-out worlds, false links and recall are unchanged. Those worlds contain only Devanagari and Latin records, so this table is the only measurement of the two fixes.
- **The remaining Urdu gap.** Urdu omits short vowels, so names that differ only in them (Salim / Sulaim) cannot be told apart from the script alone; a person or another field has to.

## 3. Person-record matching: FEBRL (`bench/febrl.py`)

FEBRL is the standard record-linkage benchmark. FEBRL3 has 5,000 records: 2,000 originals and 3,000 corrupted duplicates. FEBRL4 links 5,000 originals to 5,000 duplicates.

The records are mapped onto DRISHTI's features: name, birth year, postcode as "district", and the social-security number as an identifier. DRISHTI has no address feature, and FEBRL leans heavily on addresses and corrupts identifiers on purpose, so this test sits away from DRISHTI's design point.

**Changed after the first run.** Identifiers that differ by one keying slip now count as a typo, not a conflict. Such a pair scores higher but is never linked automatically. Two valid Aadhaar numbers cannot be one digit apart, because the Verhoeff checksum catches every single substitution and adjacent transposition.

| Dataset | DRISHTI parameters | Automatic links: P / R | After review: P / R / F1 | Review queue |
|---|---|---|---|---|
| FEBRL3 | hand-set | 1.000 / 0.857 | 0.999 / 0.931 / 0.964 | 446 |
| FEBRL3 | adopted (trained on the Indian synthetic scale world) | 1.000 / 0.778 | **1.000 / 0.961 / 0.980** | 1,256 |
| FEBRL4 | hand-set | 1.000 / 0.912 | 1.000 / 0.958 / 0.979 | 229 |
| FEBRL4 | adopted | 1.000 / 0.854 | **1.000 / 0.969 / 0.984** | 576 |

The change was checked on the four Indian held-out worlds. False automatic links and recall after review are identical to before, because those worlds contain no identifier typos.

**Head-to-head with Splink 5** (UK Ministry of Justice; `bench/febrl_splink.py`, isolated environment). Splink was trained on each dataset with its documented procedure: deterministic prior, u by random sampling, EM over three blocking rules.

| Recall after review (precision in brackets) | FEBRL3 | FEBRL4 |
|---|---|---|
| DRISHTI, first run (birth year, postcode, ID) | 0.961 (1.000) | 0.969 (1.000) |
| DRISHTI + full date of birth + address + date-of-birth blocking (v5) | 0.981 (1.000) | 0.987 (1.000) |
| + ID noise learned from the other FEBRL file's labels | **0.983** (0.999) | **0.988** (1.000) |
| Splink 5, same information as DRISHTI | 0.986 (1.000) | 0.987 (1.000) |
| Splink 5, all fields | 0.994 (1.000) | 0.995 (1.000) |

Reading:
- **Blocking ceiling.** It rose from 0.984 to 0.996 (FEBRL3) and from 0.995 to 0.999 (FEBRL4).
- **The remaining gap to Splink is about one point,** and almost all of it is two deliberate DRISHTI rules:
  1. A completely different ID number counts strongly against a match. FEBRL replaces the ID outright in 6.4% of true pairs, far more than a checksummed, biometrically de-duplicated Aadhaar would.
  2. A pair whose given names conflict is never linked automatically. FEBRL often replaces the given name entirely ("oliver mugo" / "benjamin mugo" with one date of birth and address), which in Indian data is what twins look like.
- **What the second rule costs on FEBRL.** Fewer pairs link without review (auto recall 0.61 and 0.73), and the review queue is larger. Recall after review is unchanged.
- **Precision is 1.000 throughout.**

## 4. Money laundering: IBM AML (`bench/ibm_aml.py`)

**Data.** IBM's synthetic transactions (Altman et al., NeurIPS 2023), generated by a simulator independent of DRISHTI's. HI-Small has 5,078,345 transactions with eight labelled laundering patterns.

**Protocol.** This follows the published results (Egressy et al., AAAI 2024, Appendix E.1):
- order the transactions by time and split them 60/20/20;
- score only the last 20%, with minority-class (laundering) F1.

DRISHTI is unsupervised and never sees a label. Its typology rules and pattern detectors ran on the newest half of the transactions (2,539,173). A transaction counts as flagged when an alert or lead cites it as evidence.

| HI-Small, test window (1,015,669 transactions, 1,797 laundering) | Uses labels | Laundering F1 (%) |
|---|---|---|
| Multi-PNA+EU (best published) | trained | **68.16** |
| XGBoost + graph features | trained | 63.23 |
| LightGBM + graph features | trained | 62.86 |
| PNA | trained | 56.77 |
| GIN | trained | 28.70 |
| **DRISHTI rules** | none | **1.69** (precision 0.89, recall 15.92) |

**Scheme level.** At least one transaction was flagged for 89 of the 192 laundering attempts with transactions in the test window:

| Pattern | Attempts flagged |
|---|---|
| Gather-scatter | 24/39 |
| Cycle | 13/25 |
| Scatter-gather | 12/23 |
| Bipartite | 11/21 |
| Stack | 11/26 |
| Fan-out | 9/21 |
| Random | 5/17 |
| Fan-in | 4/20 |

**Noise.** 32,117 test transactions were flagged in all. The 72-hour pass-through rule (RAPID_LAYERING) flagged 71,208 transactions across the loaded half. In IBM's world, many ordinary accounts pass money on within days, so the rule is not specific there.

**Reading.**
- **The rules do not transfer.** DRISHTI's money rules were designed for Indian typologies and tuned on its own world, and they do not carry over to an independently generated one.
- **They act only as a coarse filter.** They reach about half the schemes, at very low precision.
- **The gap is large.** Supervised models trained on the target world's labels are 35-40 times better on its transaction-level metric.
- **What the result does not show.** It does not say the rules are useless on Indian data. It does say the 120/120 figure on DRISHTI's own worlds must not be read as general detection quality.
- **The way forward.** A learned transaction scorer, trained on labelled outcomes (STR dispositions in deployment, IBM labels here) with DRISHTI's detectors as features, under the same protocol.

**LI-Small, rules only:**
- Laundering F1 0.20 (precision 0.10, recall 8.65), against 20.83-33.07 published.
- 26 of 60 laundering schemes touched.

### 4.1 A learned scorer, under the same protocol (`bench/ibm_scorer.py`)

**Model.** Gradient boosting (scikit-learn's HistGradientBoostingClassifier) over 44 graph features of each transfer:
- the transfer itself;
- each end's activity overall and in ±12 h and ±72 h windows;
- pass-through: money in during the 72 h before and out during the 72 h after, relative to the transfer (DRISHTI's layering idea);
- fan-in and fan-out within 72 h;
- repeats on the same pair, and the reverse pair (a 2-cycle).

**Protocol.**
- No label is a feature.
- Features use the whole transaction graph, as the published graph models' test graph does.
- The model is fitted on the first 60% only.
- Thresholds are chosen on the middle 20%, and the last 20% is scored once.
- The model is deterministic.

| Test window | Threshold chosen on validation for | Precision | Recall | **F1** | Flagged | Best published F1 |
|---|---|---|---|---|---|---|
| HI-Small (1,797 laundering of 1,015,669) | best F1 | **96.35** | 61.71 | **75.24** | 1,151 | 68.16 (Multi-PNA+EU) |
| | precision ≥ 96% | **99.28** | 54.03 | 69.98 | 978 | |
| | precision ≥ 99% | **99.64** | 46.69 | 63.58 | 842 | |
| LI-Small (925 laundering of 1,384,810) | best F1 | 87.14 | 22.70 | **36.02** | 241 | 33.07 (Multi-PNA+EU) |
| | precision ≥ 96% | **99.33** | 16.11 | 27.72 | 150 | |
| | precision ≥ 99% | **100.00** | 13.30 | 23.47 | 123 | |

**Reading.**
- **It beats the best published result on both datasets.** On the same split and metric it leads by 7.1 F1 points on HI-Small and 2.9 on LI-Small (Egressy et al., AAAI 2024, Table 2).
- **It holds a precision of 96% or more on unseen data.** At such a threshold it catches 54% of laundering transactions on HI-Small and 16% on LI-Small, with almost no false alarms.
- **The published figures are means over five seeds.** This model is deterministic, so it reports a single run.
- **Like every model in that table, it is trained and tested on one simulator's world.** It shows that the method is strong. It does not show accuracy on Indian bank data, which would need labelled outcomes (STR dispositions) to train on.
- **It ranks transactions for an analyst. It never scores a person.**


### 4.2 What the lead rests on, and what a live system would get

Two further runs on HI-Small use the same split, model and threshold rules.

| Variant | Laundering F1 (best-F1 threshold) | Precision / recall at the "≥ 96%" threshold | Precision / recall at the "≥ 99%" threshold |
|---|---|---|---|
| Full features (4.1) | **75.24** | 99.28 / 54.03 | 99.64 / 46.69 |
| Without the transfer's own attributes (payment format, currency, hour, weekday, round amount, bank change, self-transfer) | 65.87 | 98.78 / 45.13 | 99.70 / 37.28 |
| **Past only:** each transfer sees only earlier minutes, with no whole-timeline totals and no look-ahead | 61.94 | 96.58 / 20.42 | **97.27** / 13.86 |

Reading:
- **The lead depends on the transfer's own attributes.** Without them, the F1 of 65.9 is below the best published 68.2. The published models also take payment format and currency as inputs, so using them is within the protocol, but the lead is not structural.
- **The strongest single signal** is how many times the same two accounts have transacted (permutation importance 0.67). Laundering transfers in IBM's simulator mostly run between pairs with no history. This is a real red flag in practice, and also a property of this simulator.
- **The headline numbers see the whole timeline.** The published protocol lets a model see the whole transaction graph, including transfers after the one being scored, and the published graph models use that too.
- **A live system sees only the past.** With past-only features, F1 is 61.9, close to the published LightGBM with graph features (62.9). At a threshold fixed on validation for 96%, precision on the unseen test window is 96.6%, catching one laundering transfer in five. The threshold fixed for 99% gave 99.3% on validation but **97.3% on test**: a 99% target did not hold on new data.
- **For an Indian bank feed, the honest operating point** is a scorer trained on that bank's labelled outcomes and run past-only. Expect about 96-97% precision at a recall of 15-20% of laundering transfers, with the rest left to scheme-level detectors and analysts.

## 5. What this says about "world's best"

On the evidence so far:
- **Indian cross-script name matching** is clearly better than standard string methods.
- **Record matching** makes no false merges on an external benchmark. Splink still finds 2-3 points more true pairs on FEBRL's Western records.
- **Money laundering.**
  - The hand-written rules are far behind (F1 1.7).
  - A learned scorer beats the best published models on both IBM datasets under their protocol: 75.2 against 68.2, and 36.0 against 33.1, with 99.3-100% precision at thresholds fixed on validation.
  - The lead depends on the transfer's own attributes and on seeing the whole timeline. Seeing only the past, as a live system does, it reaches F1 61.9 and holds 96.6-97.3% precision while catching 14-20% of laundering transfers.
- **Key-player analysis** is only as good as a contact count.
- **Urdu and Tamil names** were measured gaps and are now at 0.75 and 0.89 recall. **Leader identification** remains a gap.
- **96-99% precision** is reachable for record matching (1.000 on FEBRL, 0.991-0.995 on the Indian worlds) and for money laundering at a strict threshold (96.6-97.3% past-only). It is not reachable for leader identification from contact data.

These are claims about specific public datasets. They are not a general ranking against Palantir or anyone else, because their methods are not public.
