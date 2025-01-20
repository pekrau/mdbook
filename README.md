# mdbook

*This repo has been discontinued. See: https://github.com/pekrau/writethatbook*

Web display of a book written in Markdown.

- Contents hierarchically organized into sections and texts.
- Indexing of terms.
- Reference handling.
- Footnotes.
- Export contents to DOCX or PDF file.

## Installation notes

Environment variables:

- MDBOOK_DIR: Absolute path to the directory containing the mdbook books. Required.
- MDBOOK_USER: User name for the administrator user. Required.
- MDBOOK_PASSWORD: Password for the administrator user. Required.
- MDBOOK_DEVELOPMENT: When defined, puts app into development mode. Optional.
- MDBOOK_APIKEY: When defined, allows using a http request header entry
  'mdbook_apikey' for access. Optional.

## Software

This code has been lovingly hand-crafted. No AI tools were used in its development.

Written in [Python](https://www.python.org/) using:

- [FastHTML](https://fastht.ml/)
- [pico CSS](https://picocss.com/)
- [Marko](https://marko-py.readthedocs.io/)
- [python-docx](https://python-docx.readthedocs.io/en/latest/)
- [fpdf2](https://py-pdf.github.io/fpdf2/)
- [PyYAML](https://pypi.org/project/PyYAML/)
- [bibtexparser](https://pypi.org/project/bibtexparser/)
