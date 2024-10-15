# mdbook

Web display of a book written in Markdown.

- Contents partitionen into sections and texts.
- Indexing of terms.
- Reference handling.
- Footnotes.
- Write contents to DOCX or PDF file.

## Installation notes

Requires environment variables:

- MDBOOK_DIR: Absolute path to the directory containing the mdbook books.
- MDBOOK_USER: User name for the administrator user.
- MDBOOK_PASSWORD: Password for the administrator user.
- MDBOOK_DEVELOPMENT: When defined, puts app into development mode.

Written in Python using:

- [FastHTML](https://docs.fastht.ml/)
- [pico CSS](https://picocss.com/)
- [Marko](https://marko-py.readthedocs.io/)
- [python-docx](https://python-docx.readthedocs.io/en/latest/)
- [fpdf2](https://py-pdf.github.io/fpdf2/index.html)
- [pyyaml](https://pypi.org/project/PyYAML/)
- [bibtexparser](https://pypi.org/project/bibtexparser/)
