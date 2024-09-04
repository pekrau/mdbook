"View of Markdown book contents."

from icecream import ic

import os.path

import yaml
from fasthtml.common import *

import constants
import docx_writer
import pdf_writer
import utils

from book import Book

Tx = utils.Tx

ABSDIRPATH = "/home/pekrau/Dropbox/texter/lejonen"
SETTINGSPATH = os.path.join(ABSDIRPATH, constants.SETTINGS_FILENAME)


app, rt = fast_app(live=True)

def get_book(reload=False):
    "Get the book contents, cached."
    global _book
    if reload:
        try:
            del _book
        except NameError:
            pass
    try:
        return _book
    except NameError:
        ic("reloading book")
        _book = Book(ABSDIRPATH)
        _book.apply_settings(read_settings())
        return _book

def read_settings():
    try:
        with open(SETTINGSPATH) as infile:
            return yaml.safe_load(infile)
    except FileNotFoundError:
        return None

def write_settings(settings):
    settings["book"] = get_book().get_settings()
    with open(SETTINGSPATH, "wb") as outfile:
        outfile.write(yaml.dump(settings, encoding="utf-8", allow_unicode=True))

def get_references(reload=False):
    "Get the references book, cached."
    global _references
    if reload:
        try:
            del _references
        except NameError:
            pass
    try:
        return _references
    except NameError:
        ic("reloading references")
        _references = Book(constants.REFERENCES_DIRPATH)
        return _references


def nav(item=None, label=None, actions=None):
    "The standard navigation bar."
    NAV_STYLE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"
    entries = [Ul(Li(Img(src="/favicon.ico")),
                  Li(A(get_book().title, href="/")))]
    if item:
        entries.append(Ul(Li(item.fullname,
                             Br(),
                             Small(f'{Tx("Status")}: {Tx(item.status)}'))))
        nav_style = NAV_STYLE.format(color=item.status.color)
    elif label:
        entries.append(Ul(Li(label)))
        nav_style = NAV_STYLE.format(color=get_book().status.color)
    else:
        entries.append(Ul(Li(f"Status: {Tx(get_book().status)}")))
        nav_style = NAV_STYLE.format(color=get_book().status.color)
    items = [Li(A(Tx("Title"), href="/title")),
             Li(A(Tx("References"), href="/references")),
             Li(A(Tx("Index"), href="/index"))]
    if actions:
        items.append(Li(Details(Summary(Tx("Actions")),
                                Ul(*[Li(c) for c in actions], dir="rtl"),
                                cls="dropdown")))
    entries.append(Ul(*items))
    return Nav(*entries, style=nav_style)

@rt("/")
def get(reload:str=None):
    "Home page; list of sections and texts."
    return (Title("mdbook"),
            Header(nav(actions=[A(Tx("Update"), href="/?reload=yes"),
                                A(f'{Tx("Write")} DOCX', href="/docx"),
                                A(f'{Tx("Write")} PDF', href="/pdf"),
                                ]),
                   cls="container"),
            Main(toc(get_book(reload=reload).items), cls="container")
            )

def toc(items):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        n_words = f"{utils.thousands(item.n_words)}"
        n_characters = f"{utils.thousands(len(item))}"
        length = f'{n_words} {Tx("words")}; {n_characters} {Tx("characters")}'
        if item.is_section:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/section/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;"),
                            style=f"color: {item.status.color};",))
            parts.append(toc(item.items))
        else:
            parts.append(Li(A(str(item),
                              style=f"color: {item.status.color};",
                              href=f"/text/{item.urlpath}"),
                            NotStr("&nbsp;&nbsp;&nbsp;"),
                            Small(length, style="color: silver;")))
    return Ol(*parts)

@rt("/text/{path:path}", methods=["get", "post"])
def view_text(path:str, content:str=None, status:str=None, title:str=None):
    "View the text, or edit and save."
    text = get_book()[path]
    text.read()
    if content is not None:
        text.write(content=content)
        text.read()
    if status is not None:
        text.status = status
        text.write()
    return (Title(text.title),
            Header(nav(text, actions=[A(Tx("Edit"), href=f"/edit/{path}"),
                                      A(Tx("Settings"), href=f"/settings/{path}")]),
                   cls="container"),
            Main(NotStr(text.html), cls="container")
            )

@rt("/edit/{path:path}")
def get(path:str):
    "Edit the text."
    text = get_book()[path]
    assert text.is_text
    text.read()
    return (Title("mdbook"),
            Header(nav(label=f'{Tx("Edit")} {text.fullname}'), cls="container"),
            Main(Form(Textarea(NotStr(text.content), name="content", rows="36"),
                      Button("Save"),
                      action=f"/text/{path}",
                      method="post"),
                 cls="container"),
            )

@rt("/section/{path:path}", methods=["get", "post"])
def view_section(path:str,title:str=None):
    "View the section, or edit and save."
    section = get_book()[path]
    assert section.is_section
    return (Title(section.title),
            Header(nav(section), cls="container"),
            Main(toc(section.items), cls="container")
            )

@rt("/settings/{path:path}")
def get(path:str):
    text = get_book()[path]
    text.read()
    labels = []
    for status in constants.STATUSES:
        if status == text.status:
            labels.append(Label(Input(type="radio", name="status", value=str(status), checked=True),
                                Span(Tx(str(status)), style=f"color: {status.color};")))
        else:
            labels.append(Label(Input(type="radio", name="status", value=str(status)),
                                Span(Tx(str(status)), style=f"color: {status.color};")))
    return (Title("mdbook"),
            Header(nav(label=f'{Tx("Settings")} {text.fullname}'), cls="container"),
            Main(Form(Fieldset(Legend("Status"), *labels),
                      Button("Save"),
                      action=f"/text/{path}",
                      method="post"),
                 cls="container"),
            )

@rt("/title")
def get():
    "Title page."
    segments = [H1(get_book().title)]
    if get_book().subtitle:
        segments.append(H2(get_book().subtitle))
    for author in get_book().authors:
        segments.append(H3(author))
    segments.append(Table(
        Tr(Td(Tx("Words")), Td(utils.thousands(get_book().n_words))),
        Tr(Td(Tx("Characters")), Td(utils.thousands(len(get_book()))))
    ))
    return (Title(Tx("Title")),
            Header(nav(label=Tx("Title")), cls="container"),
            Main(*segments, cls="container")
            )

@rt("/references")
def get(reload:str=None):
    "List of references."
    items = []
    for ref in get_references(reload=reload).items:
        parts = [Img(src="/clipboard.svg",
                     title="Refid to clipboard",
                     style="cursor: pointer;",
                     cls="to_clipboard", 
                     data_clipboard_text=f'[@{ref["id"]}]'),
                 NotStr("&nbsp;"),
                 A(Strong(ref["id"], style="color: royalblue;"),
                   href=f'/reference/{ref["id"].replace(" ", "_")}'),
                 NotStr("&nbsp;"),
                 ]
        if ref.get("authors"):
            authors = [utils.short_name(a) for a in ref["authors"]]
            if len(authors) > 4:
                authors = authors[:4] + ["..."]
            parts.append(", ".join(authors))
        if ref.get("year"):
            parts.append(f'({ref["year"]})')
        if ref.get("edition_published"):
            parts.append(f'[{ref["edition_published"]}]')
        if ref.get("title"):
            parts.append(Br())
            parts.append(ref["title"])

        links = []
        if ref.get("type") == "article":
            parts.append(Br())
            parts.append(I(ref["journal"]))
            if ref.get("volume"):
                parts.append(ref["volume"])
            if ref.get("number"):
                parts.append(f'({ref["number"]})')
            if ref.get("pages"):
                parts.append(":")
                parts.append(f'pp. {ref["pages"].replace("--", "-")}.')
        elif ref.get("type") == "book":
            parts.append(Br())
            if ref.get("publisher"):
                parts.append(f'{ref["publisher"]}.')
            if ref.get("isbn"):
                symbol, url = constants.REFERENCE_LINKS["isbn"]
                url = url.format(value=ref["isbn"])
                if links:
                    links.append(", ")
                links.append(A(f'{symbol}:{ref["isbn"]}', 
                               href=url.format(value=ref["isbn"])))

        if ref.get("url"):
            parts.append(Br())
            parts.append(A(ref["url"], href=ref["url"]))
            if ref.get("accessed"):
                parts.append(f'(Accessed: {ref["accessed"]})')
        if ref.get("doi"):
            symbol, url = constants.REFERENCE_LINKS["doi"]
            url = url.format(value=ref["doi"])
            if links:
                links.append(", ")
            links.append(A(f'{symbol}:{ref["doi"]}', 
                           href=url.format(value=ref["doi"])))
        if ref.get("pmid"):
            symbol, url = constants.REFERENCE_LINKS["pmid"]
            url = url.format(value=ref["pmid"])
            if links:
                links.append(", ")
            links.append(A(f'{symbol}:{ref["pmid"]}', 
                           href=url.format(value=ref["pmid"])))

        if links:
            parts.extend(links)

        xrefs = []
        texts = get_book().references.get(ref["id"], [])
        for text in sorted(texts, key=lambda t: t.ordinal):
            if xrefs:
                xrefs.append(Br())
            xrefs.append(A(text.fullname,
                           cls="secondary",
                           href=f"/text/{text.fullname}"))
        if xrefs:
            parts.append(Small(Br(), *xrefs))
        items.append(P(*parts, id=ref["id"].replace(" ", "_")))

    return (Title(Tx("References")),
            Script(src="/clipboard.min.js"),
            Script("new ClipboardJS('.to_clipboard');"),
            Header(nav(label=Tx("References"),
                       actions=[A(Tx("Update"), href="/references?reload=yes"),]),
                   cls="container"),
            Main(*items, cls="container")
            )

@rt("/reference/{refid:str}")
def get(refid:str, reload:str=None):
    "Reference details."
    ref = get_references(reload)[refid.replace("_", " ")]
    rows = [Tr(Td(Tx("Authors")), Td("; ".join(ref.get("authors") or [])))]
    for key in ["year", "title", "type", "edition_published", "language", "date",
                "keywords", "journal", "volume", "number", "pages", "publisher"]:
        value = ref.get(key)
        if value:
            rows.append(Tr(Td((Tx(key.replace("_", " ")).title())), Td(value)))
    if ref.get("issn"):
        rows.append(Tr(Td("ISSN"), Td(ref["issn"])))
    if ref.get("isbn"):
        url = constants.REFERENCE_LINKS["isbn"][1].format(value=ref["isbn"])
        rows.append(Tr(Td("ISBN"), Td(A(ref["isbn"], href=url))))
    if ref.get("pmid"):
        url = constants.REFERENCE_LINKS["pmid"][1].format(value=ref["pmid"])
        rows.append(Tr(Td("PubMed"), Td(A(ref["pmid"], href=url))))
    if ref.get("doi"):
        url = constants.REFERENCE_LINKS["doi"][1].format(value=ref["doi"])
        rows.append(Tr(Td("DOI"), Td(A(ref["doi"], href=url))))
    if ref.get("url"):
        rows.append(Tr(Td("Url"), Td(A(ref["url"], href=ref["url"]))))
    return (Title(refid),
            Script(src="/clipboard.min.js"),
            Script("new ClipboardJS('.to_clipboard');"),
            Header(nav(label=ref["id"],
                       actions=[A(Tx("Update"), 
                                  href=f"/reference/{refid}?reload=yes"),
                                A(Tx("Clipboard"),
                                  href="#",
                                  cls="to_clipboard", 
                                  data_clipboard_text=f'[@{ref["id"]}]')
                                ]),
                   cls="container"),
            Main(Table(*rows),
                 Div(NotStr(ref.html)),
                 cls="container"))

@rt("/index")
def get():
    "Index page."
    items = []
    for key, texts in sorted(get_book().indexed.items(), key=lambda tu: tu[0].lower()):
        links = []
        for text in sorted(texts, key=lambda t: t.ordinal):
            if links:
                links.append(NotStr(",&nbsp; "))
            links.append(A(text.fullname, cls="secondary", href=f"/text/{text.fullname}"))
        items.append(Li(key, Br(), Small(*links)))
    return (Title(Tx("Index")),
            Header(nav(label=Tx("Index")), cls="container"),
            Main(Ul(*items), cls="container")
            )

@rt("/docx", methods=["get", "post"])
def docx_write(filename:str=None,
               page_break_level:int=None,
               footnotes:str=None,
               reference_font:str=None,
               indexed_font:str=None):
    settings = read_settings()
    docx_settings = settings.setdefault("creator", {}).setdefault("docx", {})
    if filename is None:
        filename = docx_settings.get("filename", "book.docx")
        page_break_level = docx_settings.get("page_break_level", 1)
        page_break_options = []
        for value in range(0, 7):
            if value == page_break_level:
                page_break_options.append(Option(str(value), selected=True))
            else:
                page_break_options.append(Option(str(value)))
        footnotes = docx_settings.get("footnotes", constants.FOOTNOTES_EACH_TEXT)
        footnotes_options = []
        for value in constants.FOOTNOTES_DISPLAY:
            if value == footnotes:
                footnotes_options.append(Option(Tx(value.capitalize()),
                                                value=value, selected=True))
            else:
                footnotes_options.append(Option(Tx(value.capitalize()), value=value))
        reference_font = docx_settings.get("reference_font", constants.NORMAL)
        reference_options = []
        for value in constants.FONT_STYLES:
            if value == reference_font:
                reference_options.append(Option(Tx(value.capitalize()),
                                                value=value, selected=True))
            else:
                reference_options.append(Option(Tx(value.capitalize())))
        indexed_font = docx_settings.get("indexed_font", constants.NORMAL)
        indexed_options = []
        for value in constants.FONT_STYLES:
            if value == indexed_font:
                indexed_options.append(Option(Tx(value.capitalize()), 
                                              value=value, selected=True))
            else:
                indexed_options.append(Option(Tx(value.capitalize()),
                                              value=value))
        return (Title(f'{Tx("Write")} DOCX'),
                Header(nav(label=f'{Tx("Write")} DOCX'), cls="container"),
                Main(Form(
                    Fieldset(
                        Legend(Tx("File name")),
                        Input(type="text", name="filename", value=filename),
                    ),
                    Fieldset(
                        Legend(Tx("Page break level")),
                        Select(*page_break_options, name="page_break_level")
                    ),
                    Fieldset(
                        Legend(Tx("Footnotes")),
                        Select(*footnotes_options, name="footnotes")
                    ),
                    Fieldset(
                        Legend(Tx("Reference font")),
                        Select(*reference_options, name="reference_font")
                    ),
                    Fieldset(
                        Legend(Tx("Indexed font")),
                        Select(*indexed_options, name="indexed_font")
                    ),
                    Button(f'{Tx("Create")} DOCX'),
                    action="/docx",
                    method="post"),
                     cls="container")
                )
    else:
        docx_settings["filename"] = filename
        docx_settings["page_break_level"] = page_break_level
        docx_settings["footnotes"] = footnotes
        docx_settings["reference_font"] = reference_font
        docx_settings["indexed_font"] = indexed_font
        write_settings(settings)
        writer = docx_writer.Writer(get_book(), get_references(), settings)
        writer.write(os.path.join(ABSDIRPATH, filename))
        return (Title(f'{Tx("Written")} DOCX'),
                Header(nav(label=f'{Tx("Written")} DOCX'), cls="container"),
                Main(P(f'{Tx("File name")}: {filename}'),
                     P(f'{Tx("Page break level")}: {page_break_level}'),
                     P(f'{Tx("Footnotes")}: {Tx(footnotes.capitalize())}'),
                     P(f'{Tx("Reference font")}: {Tx(reference_font.capitalize())}'),
                     P(f'{Tx("Indexed font")}: {Tx(indexed_font.capitalize())}'),
                     cls="container")
                )

@rt("/pdf", methods=["get", "post"])
def pdf_write(filename:str=None,
              page_break_level:int=None,
              contents_pages:bool=False,
              footnotes:str=None,
              indexed_xref:str=None):
    settings = read_settings()
    pdf_settings = settings.setdefault("write", {}).setdefault("pdf", {})
    if filename is None:
        filename = pdf_settings.get("filename", "book.pdf")
        page_break_level = pdf_settings.get("page_break_level", 1)
        page_break_options = []
        for value in range(0, 7):
            if value == page_break_level:
                page_break_options.append(Option(str(value), selected=True))
            else:
                page_break_options.append(Option(str(value)))
        contents_pages = pdf_settings.get("contents_pages", True)

        footnotes = pdf_settings.get("footnotes", constants.FOOTNOTES_EACH_TEXT)
        footnotes_options = []
        for value in constants.FOOTNOTES_DISPLAY:
            if value == footnotes:
                footnotes_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
            else:
                footnotes_options.append(Option(Tx(value.capitalize()), value=value))

        indexed_xref = pdf_settings.get("indexed_xref", constants.PDF_PAGE_NUMBER)
        indexed_options = []
        for value in constants.PDF_INDEXED_XREF_DISPLAY:
            if value == indexed_xref:
                indexed_options.append(Option(Tx(value.capitalize()), value=value, selected=True))
            else:
                indexed_options.append(Option(Tx(value.capitalize()), value=value))

        return (Title(f'{Tx("Write")} PDF'),
                Header(nav(label=f'{Tx("Write")} PDF'), cls="container"),
                Main(Form(
                    Fieldset(
                        Legend(Tx("File name")),
                        Input(type="text", name="filename", value=filename),
                    ),
                    Fieldset(
                        Legend(Tx("Page break level")),
                        Select(*page_break_options, name="page_break_level"),
                    ),
                    Fieldset(
                        Legend(Tx("Contents pages")),
                        Label(
                            Input(type="checkbox",
                                  name="contents_pages",
                                  role="switch",
                                  checked=bool(contents_pages)),
                            Tx("Display")
                        )
                    ),
                    Fieldset(
                        Legend(Tx("Footnotes")),
                        Select(*footnotes_options, name="footnotes")
                    ),
                    Fieldset(
                        Legend(Tx("Display of indexed term reference")),
                        Select(*indexed_options, name="indexed_xref")
                    ),
                    Button(f'{Tx("Create")} PDF'),
                    action="/pdf",
                    method="post"),
                     cls="container")
                )
    else:
        pdf_settings["filename"] = filename
        pdf_settings["page_break_level"] = page_break_level
        pdf_settings["footnotes"] = footnotes
        pdf_settings["indexed_xref"] = indexed_xref
        write_settings(settings)
        writer = pdf_writer.Writer(get_book(), get_references(), settings)
        writer.write(os.path.join(ABSDIRPATH, filename))
        return (Title(f'{Tx("Written")} PDF'),
                Header(nav(label=f'{Tx("Written")} PDF'), cls="container"),
                Main(P(f'{Tx("File name")}: {filename}'),
                     P(f'{Tx("Page break level")}: {page_break_level}'),
                     P(f'{Tx("Contents pages")}: {Tx(str(contents_pages))}'),
                     P(f'{Tx("Footnotes")}: {Tx(footnotes.capitalize())}'),
                     P(f'{Tx("Indexed reference display")}: {Tx(indexed_xref.capitalize())}'),
                     cls="container")
                )


if __name__ == "__main__":
    serve()
