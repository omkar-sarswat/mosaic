# 05 · Entity resolution for Indian person records

Design doc Section 12.2 called entity resolution "the core of the Resolve module", and section 3.2 named weak Indian-name resolution as gap #2. This file records what the literature offers, what we built, how it scored, and what remains.

## Why Indian names are hard (literature)

- **One spelling, many romanisations.** Some Devanagari letters map to several Latin spellings, so one name appears as different strings ("Bhairoo" / "Bheru"). IDinsight found off-the-shelf fuzzy matchers miss true matches and produce unacceptable false-match rates on such data ([IDinsight](https://www.idinsight.org/article/part-1-whats-in-a-name-combining-datasets-when-unique-identifiers-are-missing/)).
- **Phonetic coding needs Indic rules.** The [indic-soundex](https://pypi.org/project/indic-soundex/) package adapts Soundex for aspirates and clusters like "ksh" and "gy", but only works on romanised text. Cross-script phonetic matching of English and Hindi named entities goes back to Nayan et al. (IJCNLP 2008 workshop, [paper](https://preview.aclanthology.org/fix_video/I08-5014.pdf)).
- **Neural transliteration is mature.** AI4Bharat's Aksharantar gives about 26 million word pairs across 21 languages and 12 scripts; the IndicXlit model trained on it reports large gains on the Dakshina benchmark ([paper](https://cs.paperswithcode.com/paper/aksharantar-towards-building-open), [AI4Bharat](https://ai4bharat.iitm.ac.in/areas/xlit)).
- **LLM matchers are the 2026 frontier.** A structure-guided method that first parses name structure and then classifies a match reports 99.02% accuracy on 50,000 real Indian identity pairs, deployed at Dream11 (ACL 2026 Industry Track, [preview](https://preview.aclanthology.org/ingest-acl/2026.acl-industry.101/)). Accuracy on balanced pairs is not the same as precision on a blocked population; it is promising for the *review* stage, not for auto-linking.
- **Probabilistic linkage is the explainable baseline.** The Fellegi–Sunter model, as implemented by Splink, gives per-feature match weights a reviewer can read ([Splink](https://github.com/moj-analytical-services/splink)).

## The pipeline as built (`drishti/resolve/`)

1. **Script detection** by Unicode block: Devanagari, Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu, Kannada, Malayalam. Arabic-script (Urdu) is detected but not transliterated yet.
2. **Transliteration to IAST**, then **schwa deletion on the IAST form**, then folding to ASCII. Doing the deletion *before* folding is essential (see 06): IAST distinguishes the inherent short `a` from long `ā`.
   - Word-final schwa is dropped after a single consonant (रमेश → *ramesh*) or after nasal + consonant (सिंघ → *singh*, आनंद → *anand*), but kept after other clusters (कृष्ण → *krishna*, मिश्र → *mishra*, चंद्र → *chandra*).
   - Medial schwa in the V C _ C V context is dropped (इरफान → *irphan*).
   - Dravidian scripts get no schwa deletion. Tamil uses `TAMIL_SUB` and voicing rules (முருகன் → *murugan*, செல்வி → *selvi*). Bengali ব → *b* (বসু → *basu*). ज्ञ → *gy* (Marathi "dny").
3. **Normalisation**: honorifics removed (Shri, Smt, Kum, Dr, Late …). Relation markers split off the father's or husband's name (`s/o`, `d/o`, `w/o`, `urf`, `@`). Variants canonicalised (Mohd/Md/Mohammed → *muhammad*; Sk/Sheikh/Shekh → *shaikh*; Syed/Saiyed → *sayyed*). Consonant clusters such as "RK" are read as initials.
4. **Indic phonetic key** per token: aspirate pairs merged, sh~s, z~j, v~w, vowel length folded, doubled letters collapsed, anusvara assimilated before labials (tanboli ~ tamboli), non-initial vowels dropped.
5. **Blocking**: every pair of full-token keys, (key, first letter of another token) so initials meet full names whichever way round, (key, birth-year band), and shared phone number. **Blocking recall: 961 of 965 true pairs (99.6%)**, measured.
6. **Scoring** (Fellegi–Sunter, log₂ match weights) with these features:
   - name level: exact / phonetic / subset / initials / partial / weak / none, with order-insensitive token alignment (Maharashtra lists put the surname first);
   - father's given names (the shared family surname is excluded);
   - birth-year band, district, shared phone, gender.
   
   Two refinements matter:
   - **Patronymic awareness:** an extra middle token equal to the other record's father's name is not a conflict (Dattatray Vishnu Patil = Dattatray Patil, s/o Vishnu).
   - **Term-frequency adjustment:** agreement on a common full name counts for less, applied only once there are at least 100 records and the name appears at least 3 times.
7. **Prior** P(match) is estimated per run in the Splink manner: pairs passing a strict deterministic rule, divided by an assumed rule recall of 0.6 and by all pairs.
8. **Routing**: p ≥ 0.95 creates an `auto` link (drawn red, traversed); 0.70–0.95 goes to the human review queue as a `candidate` link (drawn, not traversed); lower scores are dropped. **Nothing is ever merged.** Records stay separate objects, so un-merging is a status change.

## Benchmark

The synthetic generator (`drishti/synth/`) produces 1,220 true people and 1,660 records across FIRs, cyber-fraud complaints and a welfare list. Names are drawn from Marathi, Muslim and North Indian name banks. Noise is clerk-style: romanisation variants, initials, surname-first order, honorifics, upper case, and 18–45% of records in Devanagari. Ages are ±1–3 years, with a 10% chance of a different district. Ground truth is held in a field the API never returns.

Pairwise metrics over all true pairs (~930–965):

| Iteration | Changes | Auto only P / R / F1 | If every review is confirmed P / R / F1 |
|---|---|---|---|
| v1 | baseline matcher, hand-set prior 1e-4 | 0.998 / 0.509 / 0.674 | 0.984 / 0.677 / 0.802 |
| v2 | + patronymic awareness, initials blocking, anusvara rule, estimated prior, TF guard | 0.980 / 0.784 / 0.871 | 0.945 / 0.906 / 0.925 |
| v3 | + IAST schwa fix, ज्ञ rule, contradicting-initial rule; population-weighted districts* | **0.998 / 0.826 / 0.904** | **0.949 / 0.922 / 0.935** |

\* v3 also changed the data: people are now placed in districts by approximate Census 2011 population rather than uniformly, which is denser and therefore harder. So v2→v3 is not a pure model comparison.

The design doc's gate ("F1 ≥ 0.9 on synthetic data", Section 13.3) is met both with and without human review. Auto-link precision is 99.75%. That is the number that matters for safeguard "never auto-merge innocent people", and it is why recall is deliberately traded away at the auto threshold.

## Error analysis (v3, measured)

- **Missed true pairs (below 0.95): 230.** 116 of these land in the review band and 114 are dropped. By name level: phonetic 70, initials 64, subset 52, exact 39. In other words, **names usually agree; the misses come from too little corroborating evidence.** Typical case: a welfare-list record with only name and district against an FIR record with a different district.
- **Women's records dominate the misses.** In Maharashtra a married woman's middle name is usually her husband's, and her surname may change. "Manisha Anil Jadhav" vs "Manisha Jadhav" in another district scores p = 0.004. Better features would be husband's name as a separate field (FIRs record "w/o"), and linking through a shared address or phone. The generator should model surname change at marriage explicitly.
- **False positives at auto: 1 after v3.** "Nazia Aslam Inamdar" vs a Devanagari record with the same name and father's name in the same district, but a different person (age far). Small name banks make such collisions more common in synthetic data than in reality, but they do happen with common names. Age disagreement (–4.1) was not enough to pull it under 0.95.

## Recommendations

1. **Pilot data first.** Every m/u value here is hand-set. On real data, estimate them by EM (Splink 5) and label 1,000–2,000 pairs from a district's records to measure true precision before enabling auto-links at all.
2. **Keep auto-links narrow.** Consider raising the auto threshold to 0.99 for police use, and allowing auto-links only within a single source type (e.g. FIR ↔ FIR), sending cross-domain links (FIR ↔ welfare list) to review.
3. **Add IndicXlit** for Urdu (Perso-Arabic) and as a second opinion for Dravidian scripts, where rule-based romanisation (e.g. "suppiramaniyan" vs "Subramanian") misses.
4. **Model marriage and address.** Add `spouse_name`, address tokens and `resides_at` links as features. Add surname change to the generator.
5. **Use LLM matchers only in review**, as a second reader that explains disagreements, and log the prompt and output in the audit chain (design doc 12.4).
6. **Report quality back to sources.** The resolver already counts within-source links. For registries that must hold one record per person (ration cards, pensions), these are suspected duplicates, which is the welfare-leakage use case.

## v4 (16 Oct 2026): fewer false links, reconciliation, and scale

Two sessions worked on resolution this day: one on false links, one on scale. Every change below is covered by tests (`test_matcher_advanced.py`, `test_resolution_reconciliation.py`, `test_ml_evaluation.py`).

**False links.**
- **Name alignment.** It is now an order-independent maximum matching (augmenting paths), so the level no longer depends on which record is compared first. Contradictory initials ("N. Y. Sayyed" vs "Rukhsar Yoosuf Sayyed") are never a positive agreement.
- **Identifiers.** They are compared kind by kind, and a shared Aadhaar cannot hide a conflicting PAN. Two different values of one kind count as a conflict, even when another value also matches.
- **Cannot-link check.** Before a machine link joins two components, the resolver refuses the union if it would bring conflicting identifiers of one kind into an entity, or reconnect a pair a person rejected. The link goes to review with the reason, and the Review screen shows that reason first.
- **Reconciliation.** Every run now reconciles instead of only adding. A machine link whose evidence no longer passes is withdrawn, and its review item closed. Human decisions and other sources' assertions (for example an intake proposal's candidate) are never touched.

**Scale.** Measured on a 10,000-person world (11,327 person records):

| Change | Before | After |
|---|---|---|
| Blocking: small blocks compared as they are; a block that grows with the population split by overlapping 5-year birth windows, then district, then gender | 1,463,678 candidate pairs | 689,625 pairs at the same pair completeness (99.92%) |
| Name comparisons cached by tokens and phonetic keys (they repeat inside a surname block) | | |
| Prior estimate and scoring in one pass (the prior only shifts every pair's log-odds by a constant, so pairs are scored once under the largest admissible prior and shifted exactly) | two passes | identical results (same prior, same pairs, probability difference 0.0); 1.6x faster |
| Full-text index keyed by rowid, `identifiers(object_id)` indexed (world build) | more than 25 min | 88 s |
| Resolution end to end | more than 8 min | under 2 min |

**Tried and not adopted: meta-blocking.** Weighted node pruning (Papadakis et al., TKDE 2014) keeps, for each record, only the candidates sharing more blocks than that record's average. It cut candidates to 22-28%. It also dropped true pairs the scorer would have linked:
- **Shared-block count (CBS):** 0-6 reviewable true pairs per world, two of them scoring 0.998.
- **Rarity-weighted (ARCS):** 4-11 per world.

Resolution is an offline batch job, so DRISHTI spends the CPU time instead.

**Training the parameters without labels (Splink's procedure, corrected).** `drishti train matcher` estimates the hand-set Fellegi-Sunter m/u values from data (`drishti/resolve/train.py`).

- **u (agreement among different people):** uniform random sampling over all non-matching pairs.
- **m (agreement among records of one person):** expectation maximisation (EM), which needs no labels and is therefore the method for real data. It runs over distinct comparison vectors weighted by their counts, which equals per-pair EM (checked to 1e-13) and uses about a thousand patterns instead of millions of pairs.

**Defect found and fixed: a blocking-rule bias.** The first version ran EM on the matcher's own blocks, which are chosen by name similarity. Among those pairs names agree far more often than u (from random pairs) expects, so EM credited every name agreement to a match. Its match share hit the 0.5 cap, against a true share of about 0.8%. The fix follows the rule that a feature used to choose the candidate pairs, or correlated with one, cannot be estimated from them. There are now two sessions:

| Session | Candidate pairs | Features estimated |
|---|---|---|
| 1 | Name keys only, no birth, district or gender refinement; large blocks sampled | age, district |
| 2 | Same birth year and district | name, father's name, gender |

Exact identifiers (phone, Aadhaar/PAN/passport) keep their expert m in both sessions. Too few true pairs carry them on both records, and an estimate drifted to 0.88 TV on identity, which would have weakened the strongest evidence against a link. m is a MAP estimate under a Dirichlet prior centred on the hand-set values, worth 10 pairs.

**Result.** The table gives the total-variation distance from the true m, measured on synthetic labels the method never sees. It is the mean over all seven features.

| World | EM (no labels) | Hand-set | Name only: EM vs hand-set |
|---|---|---|---|
| seed 47 (1,800 people) | **0.003** | 0.114 | 0.011 vs 0.350 |
| seed 23 (1,200) | **0.002** | 0.126 | 0.005 vs 0.430 |
| seed 91 (1,500) | **0.006** | 0.120 | 0.019 vs 0.387 |

EM's match share among name-blocked pairs is now 0.7-1.3%, matching the truth. `tests/test_training.py` checks four things:
- the pattern and pair forms of EM agree;
- the share stays realistic;
- EM is at least three times closer to the truth than the hand-set values;
- identifiers keep their expert values.

**Adoption (16 Oct 2026).** `drishti train matcher --db var/scale.db --adopt` trained on the 30,000-person scale world (33,336 records, seed 101). It judged two candidates on four held-out worlds (seeds 11, 23, 47, 91), which share no identities with the training world, checked at load. Each candidate's review threshold is chosen on the training world only: the highest threshold that still sends essentially every reachable true pair to a person. The gate refuses a candidate that adds a false automatic link, lowers automatic precision, or lowers recall after review on any world, or that does not raise mean F1.

| Held-out world | Hand-set (review 0.70): false auto links / F1 / recall after review / queue | EM, no labels (review 0.20) | m from labelled pairs (review 0.05), **adopted** |
|---|---|---|---|
| seed 11 | 2 / 0.985 / 0.9946 / 20 | 8 / 0.977 / 0.9946 / 20 | **2 / 0.985 / 0.9946 / 23** |
| seed 23 | 6 / 0.982 / 0.9976 / 19 | 7 / 0.981 / 0.9976 / 21 | **2 / 0.987 / 0.9976 / 22** |
| seed 47 | 24 / 0.959 / 0.9956 / 43 | 8 / 0.976 / 0.9956 / 45 | **4 / 0.980 / 0.9956 / 49** |
| seed 91 | 8 / 0.982 / 0.9977 / 29 | 8 / 0.982 / 0.9977 / 36 | **2 / 0.988 / 0.9977 / 43** |

- **m from labelled pairs (adopted).** Combined with u from random sampling, it cuts false automatic links by 75% (40 to 10) at identical recall after review. The price is 23% more review items.
- **EM.** It lowers false links overall (40 to 31) but adds them on two worlds, so the gate refuses it.
- **What adoption means for deployment.** The labels here are synthetic truth. In a deployment they are an audited sample of 1,000-2,000 pairs per region (Recommendation 1), and the same command, gate and file (`models/matcher.json`, with its review threshold) apply.
- **Tests stay on the hand-set parameters** (`tests/conftest.py`), so they do not depend on what a machine has adopted.

**The learned review model, retrained at scale (16 Oct 2026).** The logistic linkage model (`drishti/ml/linkage.py`, `scripts/train_linkage.py`) proposes pairs for a person to compare; it never merges. It promises 98% precision at its review threshold, chosen on validation data. It was first trained on 1,581 records (426 identities) from the demo world. On held-out worlds it broke that promise: precision 0.88-0.93.

It was retrained on 9,000 identities sampled from the scale world (`--max-identities 9000`; identity-disjoint 60/20/20 splits). Both models were scored end to end with `scripts/compare_linkage.py` on the worlds neither was trained on (seeds 23, 47, 91). Seed 11 shares 702 identities with the demo world, so it is excluded for the old model.

| Model | Precision | Recall | F1 | False proposals | Missed true pairs |
|---|---|---|---|---|---|
| Demo-trained (lr-ac489d55dcff) | 0.902 | 0.997 | 0.947 | 142 | 4 |
| Scale-trained (lr-d044b7eb73e2), **active** | **0.997** | 0.968 | **0.982** | **4** | 42 |

The scale-trained model keeps its precision promise on every unseen world (0.9955-0.9976). It costs 3 points of recall. The old artifact is kept as `var/models/record_linkage-2026-10-14.json`, and the comparison is in `var/models/linkage-comparison.json`.

## v5 (16 Oct 2026): date of birth, address, twins and households

**New evidence.**
- **Date of birth.** A full date is now compared when both records carry one: exact, near (day/month swapped or one keying slip), or the same year with a different date. It sharpens the birth-year comparison rather than adding a second one, so the year is not counted twice. 1 January and 1 July count as year-only, because registers write them when only the year is known.
- **Address.** Addresses are compared as tokens ("4/B", "4-B" and "Flat No. 4B" are one flat) and sharpen the district comparison.
- **Blocking.** New blocks on the full date with the district, and with the house number, so records whose names were garbled can still meet.

**Two safety rules.**
- **Twins.** A pair whose given names genuinely conflict is never linked automatically. Twins share a father, a birth date, an address and a surname, and only the given name tells them apart. A typing slip is not a conflict: leftover tokens pairing at Jaro-Winkler ≥ 0.88 count as one name. Any initials keep the guard on. On the four held-out worlds, no true pair was ever auto-linked with conflicting given names, while 6 false auto-links (hand-set values) were exactly that, so the rule costs no recall.
- **Households.** People a generation apart (birth years more than 3 apart) at one address are a household, not one person. Grandfather and grandson often share a name, so the address then counts only as the same district. This came from a false link found in testing: "Dipak Manoj Sinh", born 1970, and "Singh Manoj Deepak", born 1996, at one flat.

**Correction found in testing.** The near-date level was first given u = 0.0003. Within a birth year, about one date in 16 is one keystroke from any given date, so the right value is about 0.0015 (4.3 bits, not 6.6). The higher weight had merged two women born in 2003 whose fathers were both named Dilip.

**Stress test on the Indian worlds** (`bench/dob_address_stress.py`). The worlds put a full date and an address on each person's main record only. The test copies them onto the person's other records with register errors: 7% day/month swapped, 5% one digit wrong, 8% placeholder dates, 25% reformatted addresses, 10% a neighbouring flat and 10% missing. Relatives keep their shared family address. Adopted parameters:

| World | False auto links: without the fields / with | Recall after review: without / with | Review queue: without / with |
|---|---|---|---|
| seed 11 | 2 / 2 | 0.9946 / **1.0000** | 23 / **17** |
| seed 23 | 2 / 2 | 0.9976 / 0.9976 | 22 / **17** |
| seed 47 | 4 / 4 | 0.9956 / **1.0000** | 49 / **31** |
| seed 91 | 2 / 2 | 0.9977 / 0.9977 | 43 / **22** |

There are no additional false links in any world, and review queues are 23-49% shorter. With the hand-set values the twin guard alone cuts false auto links in world 47 from 24 to 14 and in world 91 from 8 to 2.
