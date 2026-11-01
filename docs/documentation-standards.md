# Documentation standards and research

The repository documentation is organised for two readers: a person evaluating Mosaic and a developer trying to run or change it. The root README answers what the project does and how to start. Detailed workflows, architecture, deployment notes, and publication sources live under `docs/`.

## Research informing the structure

| Primary source | Principle applied here |
| --- | --- |
| [GitHub: About READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) | Explain purpose, use, setup, help, and ownership; use repository-relative links and images. |
| [GitHub: Repository best practices](https://docs.github.com/en/repositories/creating-and-managing-repositories/best-practices-for-repositories) | Include contribution guidance, licensing, and a maintainable repository structure. |
| [Google: README guidance](https://google.github.io/styleguide/docguide/READMEs.html) | Keep a useful entry point at the project root and link to deeper documentation. |
| [Google: Documentation best practices](https://google.github.io/styleguide/docguide/best_practices.html) | Keep documentation close to the code and avoid duplicating details that will drift. |
| [Microsoft VS Code README](https://github.com/microsoft/vscode/blob/main/README.md) | Establish the repository’s identity and direct development work to dedicated contribution material. |
| [Excalidraw README](https://github.com/excalidraw/excalidraw/blob/master/README.md) | Show the actual product, distinguish product scope, and provide direct setup and documentation paths. |

The examples informed structure and navigation. Mosaic’s prose, commands, screenshots, and implementation claims come from this repository and its own publications.

## Product sources

The [Mosaic brochure](Mosaic-Brochure.pdf), dated 22 October 2026, is the primary company and product introduction. The [product guide](Mosaic-Product-Guide.pdf) and [product book](Mosaic-Product-Book.pdf) provide the detailed workflow narrative. Current source files determine technical setup, package names, dependencies, and implemented interfaces.

## Editing rules

1. Use **Mosaic** for the product and **Weirwood** for the company. Keep `drishti` in commands, module names, environment variables, and API headers until an explicit compatibility migration occurs.
2. Put copyable setup commands near the start. Separate Windows activation from macOS/Linux activation.
3. Use the supplied brand assets. Provide useful image alt text and preserve the full product screenshot.
4. Identify synthetic screenshots and demonstration records. Do not imply agency endorsement, deployed customers, certification, or measured operational outcomes.
5. Describe optional dependencies where the feature is introduced. Do not label the entire application offline if external maps or identity services are still configured.
6. Link to dated research instead of promoting old benchmark results into current product guarantees.
7. Describe the checks that actually ship. Do not advertise a passing test suite whose files are absent.
8. Preserve source licenses and attribution. Keep secrets, runtime databases, and downloaded tools out of Git.
9. Update links, screenshots, and the relevant guide when behaviour changes. Review internal links before merging.

## Review checklist

- Can a new developer follow the installation instructions from a clean clone?
- Does every local link resolve, including case-sensitive paths on Linux?
- Do images render on GitHub in both themes, with meaningful alternatives?
- Are optional features and current limitations clear?
- Are historical claims labelled, and current claims supported by source or verification?
- Are company identity and product naming consistent?
