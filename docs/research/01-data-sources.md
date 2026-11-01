# 01 · Data sources: what they are really like to ingest

The design doc lists the open sources DRISHTI can use without permission (Section 10.1). This file records what we found when we actually connected to them on 14 Oct 2026.

## 1. NDMA SACHET (Common Alerting Protocol)

**Feed.** `https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml` is RSS 2.0. Its channel declares `<copyright>public domain</copyright>`. Each `<item>` links to one CAP 1.2 XML file at `FetchXMLFile?identifier=<id>`. The feed URL was first spotted in a [Windy community thread](https://community.windy.com/topic/43097/weather-warning-problem/16); everything below is *measured* from the live feed.

**What one fetch contained (14 Oct 2026, 99 items):**

| Sender | Items |
|---|---|
| Andhra Pradesh SDMA | 50 |
| CWC (Central Water Commission) | 19 |
| IMD Chennai | 18 |
| IMD Dehradun / Jaipur / Visakhapatnam / Patna / Kolkata | 5 / 3 / 2 / 1 / 1 |

Every item had `<category>Met</category>`, including CWC river floods, so the RSS category is not a reliable hazard type. Use CAP `<event>` instead (`Lightning`, `Flood`, `Moderate Rain`, `Thunderstorm with Lightning` …).

**Structure of a CAP file:**

- Usually **two `<info>` blocks**: `en-IN` plus a regional language (`TL` Telugu, `HI` Hindi …). The RSS `<title>` is often the regional one. DRISHTI keeps the English block for display and stores the regional headline as `headline_original`. This matches the design doc's "English UI, original kept" rule (Section 12).
- **No inline `<polygon>`, `<circle>` or coordinates** in any sampled file. Instead there is a `<parameter>` named `Polygon URL` pointing to `FetchPolygonXMLFile?identifier=…`. That endpoint returned **HTTP 403** to our client, even with browser-like headers.
- **Some alerts carry `<geocode>` values named `LGD District Code`.** IMD Chennai's rain alerts listed 12–14 codes each, and Rajasthan SDMA's "6 districts of Rajasthan" was only resolvable through its geocodes. This is the authoritative location when present.
- `areaDesc` text varies by issuer:
  - IMD: `"Cuddalore, Krishnagiri, … districts of Tamil Nadu"`
  - CWC: `"Bagmati, Benibad, Muzaffarpur, Bihar"` (river, station, district, state)
  - AP SDMA: mandal lists with district prefixes, e.g. `"tpt-tada, tpt-penagalur, ysr-nandalur mandals"`, where `tpt` = Tirupati and `ysr` = YSR Kadapa
  - Uttarakhand: `"pauri almora chamoli"` (space-separated, abbreviated)
  - Bihar SDMA: `"tslg"`, which we could not interpret

**CWC flood alerts** embed gauge readings in a fixed sentence: *"River Bagmati at Benibad in Muzaffarpur district of Bihar … flowing at a level of 48.06 m with falling trend … Warning Level of 47.68 m … Danger Level of 48.68 m."* One regular expression extracts river, station, district, state, level, trend, warning and danger levels, so CWC alerts double as a river-gauge feed.

**Geocoding results** for the 25-alert snapshot in `data/samples/sachet/`, using the order LGD geocode → inline polygon → district name → sub-district (mandal) name → token match:

| Method | Alerts |
|---|---|
| LGD geocode in CAP | 4 |
| Sub-district (mandal) name → parent district | 10 |
| District name | 5 |
| District tokens ("pauri almora chamoli") | 1 |
| Unresolved | 5 |

That is **80% placed**. The unresolved alerts were "6 Mandals", "tslg", and three AP mandals missing from Wikidata's sub-district list (e.g. Chillakur).

**Recommendations**

- Ask NDMA (or the State EOC, under an MoU) for (a) polygon access for registered consumers, and (b) `LGD District Code` / `LGD Subdistrict Code` geocodes on every alert. Item (b) costs issuers nothing and would make every alert machine-placeable.
- Poll the RSS every 5 minutes and fetch only unseen identifiers. CAP `<msgType>Update/Cancel` and `<references>` should supersede earlier alerts; v0.1 does not handle this yet.
- Keep the raw CAP XML as the evidence record; hazards in DRISHTI are derived objects.

## 2. Local Government Directory (LGD)

- The official site offers bulk download by state, district or sub-district, including "modifications since" (the [LGD download page](https://lgdirectory.gov.in/downloadDirectory.do)).
- **There is no public API for villages.** data.gov.in lists [LGD – Villages](https://www.data.gov.in/resource/local-government-directory-lgd-villages) and [Sub-Districts](https://www.data.gov.in/resource/local-government-directory-lgd-sub-districts) with "API for this resource does not exist" and a "Request API" button. Datasets refresh on the 1st of each month. A real-time REST interface exists for state revenue departments, election commissions and licensed software ([IMPRI summary](https://www.impriindia.com/insights/policy-update/localgovernmentdirectory/)); access is through government channels.
- A community archive of daily dumps is at [ramseraph.github.io/opendata/lgd](https://ramseraph.github.io/opendata/lgd/) (7-Zip format). It also syncs entities into Wikidata.
- **Wikidata now carries official LGD codes:** `P12747` state, `P12746` district, `P12748` sub-district, `P12745` village, `P12717` block, `P6425` local body. One SPARQL query gave **36 states, 788 districts and 7,221 sub-districts** (*measured*). Wikidata is CC0. Two traps:
  - districts usually sit under an administrative *division*, so the state join needs the transitive `wdt:P131+` path;
  - coordinates are uneven. We found 3 Maharashtra districts whose Wikidata coordinate falls **outside** their own polygon (Jalgaon at 18.65°N, though the district centroid is near 20.9°N; Dharashiv given Solapur's coordinate; Sangli), and 136 districts with conflicting coordinates. DRISHTI reports these as data-quality issues and uses polygon centroids instead.
- **Duplicate names across states** (*measured*): Aurangabad (Maharashtra, Bihar), Bilaspur (Himachal, Chhattisgarh), Hamirpur (Himachal, Uttar Pradesh), Pratapgarh (Uttar Pradesh, Rajasthan). Any name-based geocoder must constrain by state.
- **Renames** that source text keeps using for years: Ahmednagar→Ahilyanagar (2024), Aurangabad→Chhatrapati Sambhajinagar (2023), Osmanabad→Dharashiv (2023), plus older ones (Gurgaon→Gurugram, Allahabad→Prayagraj, Hoshangabad→Narmadapuram). The gazetteer carries an alias table.

## 3. District boundaries

- **geoBoundaries IND ADM2** ([API](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/), [HDX](https://data.humdata.org/m/dataset/geoboundaries-admin-boundaries-for-india)). The API metadata (*measured*) gives licence **ODbL 1.0**, source "Pathways Data Pvt. Ltd., lgdirectory.gov.in", vintage 2021, and 735 units. Some third-party wrappers claim CC BY 4.0; the official metadata says ODbL, so we follow that and share the derived file under ODbL (see NOTICE).
- The file has **no state field and no LGD codes**, only `shapeName`, and uses pre-rename spellings (Ahmadnagar, Bid, Buldana, Gondiya, Osmanabad, Raigarh for Raigad). We joined the 36 Maharashtra districts to LGD codes with an explicit table plus a bounding-box check, because "Aurangabad" and "Raigarh" also exist elsewhere.
- 788 LGD districts vs 735 polygons: **about 53 newer districts have no open polygon** (*inference from counts*). Production needs Survey of India / Bhuvan administrative boundaries. That is also a legal requirement for political maps (see 03).

## 4. OpenStreetMap via Overpass

- The public Overpass instance timed out (HTTP 504) on a statewide query; a mirror succeeded. Usage guidance is roughly under 10,000 queries and 1 GB a day, divided by 100 for regular or app use, with a pause after 429/406 responses ([OSM wiki](https://wiki.openstreetmap.org/wiki/Overpass_API)). The fetch script rotates mirrors, and production should self-host Overpass or use Geofabrik extracts.
- **Data quality for disaster use** (*measured*, 8,190 `amenity=hospital` objects in Maharashtra):

| Attribute | Count |
|---|---|
| With a name | 8,033 (157 unnamed) |
| With a `beds` value | **2** |
| `emergency=yes` | 225 |
| `operator:type` government / public | 23 / 17 |

Good for "where are hospitals", useless for "how many beds are free". Capacity must come from departmental systems (state NHM/HMIS dashboards; the ABDM Health Facility Registry is worth evaluating — *inference, access terms unverified*).

## 5. Central Water Commission

Public flood data is published as **daily PDF bulletins**, about 200 level-forecast sites, each with danger level, warning level, highest flood level, forecast and trend ([example bulletin](https://cwc.gov.in/sites/default/files/cfcrcwcdfb13.05.2024.pdf)). We found no documented open API. The SACHET CWC alerts (above) are the easiest machine-readable route for sites currently above warning level.

## 6. Other sources to wire next

| Source | Use | Notes |
|---|---|---|
| data.gov.in OGD API | scheme progress, NCRB tables | free API key; Government Open Data License – India |
| IMD district warnings | nowcasts beyond CAP | public pages; check for CAP coverage first |
| Bhuvan WMS (ISRO) | official base layers, flood inundation | free registration |
| OpenSanctions | watchlist matching | FollowTheMoney format; non-commercial terms |
| MCA21 company master | procurement-fraud graph | public search; bulk access terms to verify |
