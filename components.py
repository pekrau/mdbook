"Page components."

import psutil

from fasthtml.common import *

import constants
import utils
from book import Book
from utils import Tx


NAV_STYLE_TEMPLATE = "outline-color: {color}; outline-width:8px; outline-style:solid; padding:0px 10px; border-radius:5px;"


def metadata(item):
    n_words = f"{utils.thousands(item.n_words)}"
    n_characters = f"{utils.thousands(len(item))}"
    items = [
        Tx(item.status),
        f'{n_words} {Tx("words")}; {n_characters} {Tx("characters")}',
    ]
    if isinstance(item, Book) and item.frontmatter.get("language"):
        items.append(item.frontmatter["language"])
    return "; ".join(items)


def header(book=None, item=None, title=None, actions=None):
    "The standard page header with navigation bar."
    if book is None:
        entries = [Ul(Li(A(Img(src="/mdbook.png"), href="/")))]
    else:
        entries = [
            Ul(
                Li(A(Img(src="/mdbook.png", width=32, height=32), href="/")),
                Li(A(book.title, href=f"/book/{book.id}")),
            )
        ]
    if item is not None:
        entries.append(
            Ul(
                Li(
                    Strong(item.fullname),
                    Br(),
                    Small(metadata(item)),
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=item.status.color)
    elif book is not None:
        entries.append(
            Ul(
                Li(
                    Small(metadata(book)),
                )
            )
        )
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    elif title:
        entries.append(Ul(Li(Strong(title))))
        if book is None:
            nav_style = NAV_STYLE_TEMPLATE.format(color="black")
        else:
            nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    elif book is not None:
        entries.append(Ul(Li(f'{Tx("Status")}: {Tx(book.status)}')))
        nav_style = NAV_STYLE_TEMPLATE.format(color=book.status.color)
    else:
        nav_style = NAV_STYLE_TEMPLATE.format(color="black")
    pages = []
    if item is not None:
        if item.parent:
            if item.parent.level == 0:  # Book.
                url = f"/book/{book.id}"
            else:
                url = f"/book/{book.id}/{item.parent.urlpath}"
            pages.append(A(NotStr(f"&ShortUpArrow; {item.parent.title}"), href=url))
        if item.prev:
            url = f"/book/{book.id}/{item.prev.urlpath}"
            pages.append(A(NotStr(f"&ShortLeftArrow; {item.prev.title}"), href=url))
        if item.next:
            url = f"/book/{book.id}/{item.next.urlpath}"
            pages.append(A(NotStr(f"&ShortRightArrow; {item.next.title}"), href=url))
    if book is not None:
        pages.append(A(Tx("Title"), href=f"/title/{book.id}"))
        pages.append(A(Tx("Index"), href=f"/index/{book.id}"))
        pages.append(A(Tx("Status list"), href=f"/statuslist/{book.id}"))
    pages.append(A(Tx("References"), href="/references"))
    pages.append(A(Tx("Information"), href="/information"))
    items = [
        Li(Details(Summary(Tx("Pages")), Ul(*[Li(p) for p in pages]), cls="dropdown"))
    ]
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
                A(NotStr("&ShortUpArrow;"), href=f"/up/{book.id}/{item.urlpath}"),
                NotStr("&nbsp;"),
                A(NotStr("&ShortDownArrow;"), href=f"/down/{book.id}/{item.urlpath}"),
            ]
        else:
            arrows = []
        parts.append(
            Li(
                A(
                    str(item),
                    style=f"color: {item.status.color};",
                    href=f"/book/{book.id}/{item.urlpath}",
                ),
                NotStr("&nbsp;&nbsp;&nbsp;"),
                Small(metadata(item)),
                *arrows,
            )
        )
        if item.is_section:
            parts.append(toc(book, item.items, show_arrows=show_arrows))
    return Ol(*parts)
