# Mosaic documentation

Mosaic is Weirwood’s investigation and intelligence workspace. This directory holds the product publications, engineering guides, original product captures, and research behind the implementation.

## Start with your task

| I want to… | Read |
| --- | --- |
| Understand the product and company | [Mosaic brochure](Mosaic-Brochure.pdf), 48 pages. |
| Walk through the main capabilities | [Product guide](Mosaic-Product-Guide.pdf), 30 pages. |
| Inspect individual screens and workflows | [Product book](Mosaic-Product-Book.pdf), 120 pages. |
| Run the application locally | [Getting started](getting-started.md). |
| Understand the code | [Architecture](architecture.md) and [development](development.md). |
| Configure a deployment | [Deployment](deployment.md). |
| View product images | [Screenshot gallery](screenshots.md). |
| Understand included data and assets | [Repository assets](repository-assets.md). |
| Review design and evaluation history | [Research index](research/README.md). |
| Edit documentation | [Documentation standards](documentation-standards.md). |

## Product publications

The three publications serve different reading depths. Their original content and source assets are retained:

- [brochure/](brochure/README.md): company introduction and product overview in a case-file format; includes its builder, fonts, and brand assets.
- [product-guide/](product-guide/README.md): concise capabilities guide, manuscript, page coverage map, and build instructions.
- [product-book/](product-book/README.md): detailed reference, screenshot inventory, editorial sources, and verification scripts.

The publications are dated October 2026. Product screenshots depict synthetic investigations. Geographic reference information and public alerts can contain real place and agency names.

## Naming and historical material

**Mosaic** is the product; **Weirwood** is the company. `drishti` remains the Python package and CLI name. Environment variables use `DRISHTI_`, and existing API headers use `X-DRISHTI-`. These identifiers are intentional compatibility details.

Some research and design documents describe earlier implementations. For example, older material mentions Cytoscape, unavailable evidence exports, or missing OIDC UI support. The current application and engineering guides take precedence for setup and implementation details. Historical measurements remain attributed to the build in which they were obtained.

Some reports also reference `tests/` and `bench/`; those directories are not present in this source snapshot. Their reported results have not been reproduced merely by publishing the repository.

[Return to the project README](../README.md).
