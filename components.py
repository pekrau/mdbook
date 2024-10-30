"Page components and functions."

from http import HTTPStatus as HTTP
import psutil
import string

from fasthtml.common import *

import books
import constants
import utils
from utils import Tx, Error


NAV_STYLE_TEMPLATE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"


def header(book=None, item=None, title=None, actions=None, references=True, state_url=None):
    "The standard page header with navigation bar."
    # The first cell: icon and book title (if any).
    if book:
        entries = [
            Ul(
                Li(A(Img(src="/mdbook.png", width=32, height=32), href="/")),
                Li(A(Strong(book.title), href=f"/book/{book.bid}")),
            )
        ]
    else:
        entries = [Ul(Li(A(Img(src="/mdbook.png"), href="/")))]

    # The second cell: title, or item info, or book info.
    if title:
        entries.append(Ul(Li(Strong(title))))
        if book is None:
            nav_style = NAV_STYLE_TEMPLATE.format(color="black")
        else:
            nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)

    elif item:
        entries.append(Ul(Li(Strong(item.fulltitle))))
        nav_style = NAV_STYLE_TEMPLATE.format(color=item.status.color)

    elif book:
        entries.append(Ul(Li(Tx("Contents"))))
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)

    else:
        nav_style = NAV_STYLE_TEMPLATE.format(color="black")

    pages = []
    if item is not None:
        if item.parent:
            if item.parent.level == 0:  # Book.
                url = f"/book/{book.bid}"
            else:
                url = f"/book/{book.bid}/{item.parent.path}"
            pages.append(A(NotStr(f"&ShortUpArrow; {item.parent.title}"), href=url))
        if item.prev:
            url = f"/book/{book.bid}/{item.prev.path}"
            pages.append(A(NotStr(f"&ShortLeftArrow; {item.prev.title}"), href=url))
        if item.next:
            url = f"/book/{book.bid}/{item.next.path}"
            pages.append(A(NotStr(f"&ShortRightArrow; {item.next.title}"), href=url))
    if book is not None:
        pages.append(A(Tx("Index"), href=f"/index/{book.bid}"))
        pages.append(A(Tx("Information"), href=f"/information/{book.bid}"))
        pages.append(A(Tx("Status list"), href=f"/statuslist/{book.bid}"))
    if state_url:
        pages.append(A(Tx("State"), href=state_url))
    if not book and not item:
        pages.append(A(Tx("System"), href="/system"))
    items = []
    if references:
        items.append(Li(A(Tx("References"), href="/references")))
    items.append(
        Li(Details(Summary(Tx("Pages")), Ul(*[Li(p) for p in pages]), cls="dropdown"))
    )
    if actions:
        items.append(
            Li(
                Details(
                    Summary(Tx("Actions")),
                    Ul(*[Li(c) for c in actions]),
                    cls="dropdown",
                )
            )
        )
    entries.append(Ul(*items))
    return Header(Nav(*entries, style=nav_style), cls="container")


def toc(book, items, show_arrows=False):
    "Recursive lists of sections and texts."
    parts = []
    for item in items:
        if show_arrows:
            arrows = [
                NotStr("&nbsp;"),
                A(NotStr("&ShortUpArrow;"), href=f"/up/{book.bid}/{item.path}"),
                NotStr("&nbsp;"),
                A(NotStr("&ShortDownArrow;"), href=f"/down/{book.bid}/{item.path}"),
            ]
        else:
            arrows = []
        parts.append(
            Li(
                A(
                    str(item),
                    style=f"color: {item.status.color};",
                    href=f"/book/{book.bid}/{item.path}",
                ),
                NotStr("&nbsp;&nbsp;&nbsp;"),
                Small(
                    f"{Tx(item.type)}; ",
                    f"{Tx(repr(item.status))}; ",
                    f'{utils.thousands(item.n_words)} {Tx("words")}; ',
                    f'{utils.thousands(item.n_characters)} {Tx("characters")}',
                ),
                *arrows,
            )
        )
        if item.is_section:
            parts.append(toc(book, item.items, show_arrows=show_arrows))
    return Ol(*parts)


def footer(item):
    return Footer(
        Hr(),
        Div(
            Div(Tx(item.status)),
            Div(item.modified),
            Div(
                f'{utils.thousands(item.n_words)} {Tx("words")}; ',
                f'{utils.thousands(item.n_characters)} {Tx("characters")}',
            ),
            cls="grid",
        ),
        cls="container",
    )


def get_reference_fields(ref=None, type=None):
    "Return list of input fields for adding or editing a reference."
    if type is None:
        return Fieldset(
            Legend(Tx("Type")),
            Select(
                *[
                    Option(Tx(t.capitalize()), value=t)
                    for t in constants.REFERENCE_TYPES
                ],
                name="type",
            ),
        )

    else:
        result = [Input(type="hidden", name="type", value=type)]
    if ref is None:
        ref = {}
        autofocus = True
    else:
        autofocus = False
    result.append(
        Fieldset(
            Legend(Tx("Authors"), required()),
            Textarea(
                "\n".join(ref.get("authors") or []),
                name="authors",
                required=True,
                autofocus=autofocus,
            ),
        )
    )
    result.append(
        Fieldset(
            Legend(Tx("Title"), required()),
            Input(name="title", value=ref.get("title") or "", required=True),
        )
    )
    if type == constants.BOOK:
        result.append(
            Fieldset(
                Legend(Tx("Subtitle")),
                Input(name="subtitle", value=ref.get("subtitle") or ""),
            )
        )
    # The year cannot be edited once the reference has been created.
    if ref:
        result.append(Input(type="hidden", name="year", value=ref["year"]))
    else:
        result.append(
            Fieldset(
                Legend(Tx("Year"), required()),
                Input(name="year", value=ref.get("year") or "", required=True),
            )
        )
    # Both a book and an article may have been reprinted.
    if type in (constants.BOOK, constants.ARTICLE):
        result.append(
            Fieldset(
                Legend(Tx("Edition published")),
                Input(
                    name="edition_published", value=ref.get("edition_published") or ""
                ),
            )
        )
    result.append(
        Fieldset(Legend(Tx("Date")), Input(name="date", value=ref.get("date") or ""))
    )
    if type == constants.ARTICLE:
        result.append(
            Fieldset(
                Legend(Tx("Journal")),
                Input(name="journal", value=ref.get("journal") or ""),
            )
        )
        result.append(
            Fieldset(
                Legend(Tx("Volume")),
                Input(name="volume", value=ref.get("volume") or ""),
            )
        )
        result.append(
            Fieldset(
                Legend(Tx("Number")),
                Input(name="number", value=ref.get("number") or ""),
            )
        )
        result.append(
            Fieldset(
                Legend(Tx("Pages")), Input(name="pages", value=ref.get("pages") or "")
            )
        )
        result.append(
            Fieldset(
                Legend(Tx("ISSN")), Input(name="issn", value=ref.get("issn") or "")
            )
        )
        result.append(
            Fieldset(
                Legend(Tx("PubMed")), Input(name="pmid", value=ref.get("pmid") or "")
            )
        )
    if type == constants.BOOK:
        result.append(
            Fieldset(
                Legend(Tx("ISBN")), Input(name="isbn", value=ref.get("isbn") or "")
            )
        )
    if type in (constants.BOOK, constants.ARTICLE):
        result.append(
            Fieldset(Legend(Tx("DOI")), Input(name="doi", value=ref.get("doi") or ""))
        )
    result.append(
        Fieldset(Legend(Tx("URL")), Input(name="url", value=ref.get("url") or ""))
    )
    result.append(
        Fieldset(
            Legend(Tx("Publisher")),
            Input(name="publisher", value=ref.get("publisher") or ""),
        )
    )
    result.append(
        Fieldset(
            Legend(Tx("Language")),
            Input(name="language", value=ref.get("language") or ""),
        )
    )
    result.append(
        Fieldset(
            Legend(Tx("Keywords")),
            Input(name="keywords", value="; ".join(ref.get("keywords") or [])),
        )
    )
    if ref:
        content = ref.content or ""
        autofocus = True
    else:
        content = ""
        autofocus = False
    result.append(
        Fieldset(
            Legend(Tx("Notes")),
            Textarea(content, name="notes", rows=10, autofocus=autofocus),
        )
    )
    return result


def required():
    return Span(NotStr("&nbsp;*"), style="color: red")


def get_reference_from_form(form, ref=None):
    "Set the values of the reference from a form."
    if ref is None:
        type = form.get("type", "").strip()
        if type not in constants.REFERENCE_TYPES:
            raise Error(f"invalid reference type '{type}'", HTTP.BAD_REQUEST)
    authors = [s.strip() for s in form.get("authors", "").split("\n") if s.strip()]
    if not authors:
        raise Error("no author(s) provided", HTTP.BAD_REQUEST)
    title = utils.cleanup_whitespaces(form.get("title", ""))
    if not title:
        raise Error("no title provided", HTTP.BAD_REQUEST)
    year = form.get("year", "").strip()
    if not year:
        raise Error("no year provided", HTTP.BAD_REQUEST)

    if ref is None:
        author = authors[0].split(",")[0].strip()
        for char in [""] + list(string.ascii_lowercase):
            name = f"{author} {year}{char}"
            refid = utils.nameify(name)
            if books.get_references().get(refid) is None:
                break
        else:
            raise Error(f"could not form unique id for {name} {year}", HTTP.BAD_REQUEST)
        try:
            ref = books.get_references().create_text(name)
        except ValueError as message:
            raise Error(message, HTTP.BAD_REQUEST)
        ref.set("type", type)
        ref.set("id", refid)
        ref.set("name", name)

    # Don't bother selecting keys to add according to type...
    ref.set("authors", authors)
    ref.set("title", title)
    ref.set("year", year)
    ref.set("subtitle", utils.cleanup_whitespaces(form.get("subtitle", "")))
    ref.set("edition_published", form.get("edition_published", "").strip())
    ref.set("date", form.get("date", "").strip())
    ref.set("journal", utils.cleanup_whitespaces(form.get("journal", "")))
    ref.set("volume", form.get("volume", "").strip())
    ref.set("number", form.get("number", "").strip())
    ref.set("pages", form.get("pages", "").strip())
    ref.set("language", form.get("language", "").strip())
    ref.set("publisher", form.get("publisher", "").strip())
    ref.set("keywords", [s.strip() for s in form.get("keywords", "").split(";") if s.strip()]),
    ref.set("issn", form.get("issn", "").strip())
    ref.set("isbn", form.get("isbn", "").strip())
    ref.set("pmid", form.get("pmid", "").strip())
    ref.set("doi", form.get("doi", "").strip())
    ref.set("url", form.get("url", "").strip())
    ref.write(content=form.get("notes", "").strip())
    return ref


if __name__ == "__main__":
    h = Html(Div("blah"))
    print(to_xml(h))
