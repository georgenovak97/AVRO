# -*- coding: utf-8 -*-
"""Small dependency-free Markdown renderer suitable for Obsidian notes."""
import os
import re


def _escape(value):
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _inline(value):
    # Obsidian escapes punctuation in headings and list-like text.
    value = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|~<>])", r"\1", value)
    value = _escape(value)
    value = re.sub(r"!\[\[([^]|]+)(?:\|([^]]+))?\]\]",
                   lambda m: '<img alt="{}" src="{}">'.format(
                       m.group(2) or m.group(1), m.group(1)), value)
    value = re.sub(r"!\[([^]]*)\]\(([^)]+)\)",
                   r'<img alt="\1" src="\2">', value)
    value = re.sub(r"\[([^]]+)\]\(([^)]+)\)",
                   r'<a href="\2">\1</a>', value)
    value = re.sub(r"\[\[([^]|]+)(?:\|([^]]+))?\]\]",
                   lambda m: '<span class="wikilink">{}</span>'.format(
                       m.group(2) or m.group(1)), value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"==(.+?)==", r"<mark>\1</mark>", value)
    value = re.sub(r"\*\*(.+?)\*\*|__(.+?)__",
                   lambda m: "<strong>{}</strong>".format(m.group(1) or m.group(2)), value)
    value = re.sub(r"~~(.+?)~~", r"<del>\1</del>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*|(?<!_)_([^_]+)_",
                   lambda m: "<em>{}</em>".format(m.group(1) or m.group(2)), value)
    return value


def _slug(value):
    return re.sub(r"[^a-z0-9а-яё]+", "-", value.lower()).strip("-")


def _table_row(line):
    value = line.strip()
    if not value.startswith("|") or not value.endswith("|"):
        return None
    return [cell.strip() for cell in value[1:-1].split("|")]


def _is_separator(cells):
    return bool(cells) and all(re.match(r"^:?-+:?$", cell) for cell in cells)


def _render_table(rows):
    if len(rows) < 2 or _is_separator(rows[0]):
        return ""
    has_header = _is_separator(rows[1])
    header = rows[0] if has_header else []
    body = rows[2:] if has_header else rows
    result = ["<table>"]
    if header:
        result.append("<thead><tr>{}</tr></thead>".format(
            "".join("<th>{}</th>".format(_inline(cell)) for cell in header)))
    result.append("<tbody>")
    for row in body:
        result.append("<tr>{}</tr>".format(
            "".join("<td>{}</td>".format(_inline(cell)) for cell in row)))
    result.append("</tbody></table>")
    return "".join(result)


def markdown_to_html(text, title="", base_path="", scroll_to=""):
    lines = (text or "").replace("\r\n", "\n").split("\n")
    html = []
    index = 0
    in_code = False
    code = []
    list_type = None
    while index < len(lines):
        line = lines[index]
        fence = re.match(r"^\s*(```|~~~)\s*(.*)$", line)
        if fence:
            if in_code:
                html.append("<pre><code>{}</code></pre>".format(_escape("\n".join(code))))
                code = []
                in_code = False
            else:
                if list_type:
                    html.append("</{}>".format(list_type))
                    list_type = None
                in_code = True
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue

        cells = _table_row(line)
        if cells is not None:
            rows = []
            while index < len(lines) and _table_row(lines[index]) is not None:
                rows.append(_table_row(lines[index]))
                index += 1
            table = _render_table(rows)
            if table:
                html.append(table)
            continue

        heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            if list_type:
                html.append("</{}>".format(list_type))
                list_type = None
            level = len(heading.group(1))
            value = heading.group(2).strip()
            html.append('<h{0} id="{1}">{2}</h{0}>'.format(
                level, _slug(value), _inline(value)))
            index += 1
            continue
        if re.match(r"^\s*[-*_](\s*[-*_]){2,}\s*$", line):
            html.append("<hr>")
            index += 1
            continue

        numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        bulleted = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if numbered or bulleted:
            wanted = "ol" if numbered else "ul"
            if list_type != wanted:
                if list_type:
                    html.append("</{}>".format(list_type))
                html.append("<{}>".format(wanted))
                list_type = wanted
            html.append("<li>{}</li>".format(_inline((numbered or bulleted).group(1))))
            index += 1
            continue
        if list_type:
            html.append("</{}>".format(list_type))
            list_type = None
        quote = re.match(r"^\s*>\s*(.*)$", line)
        if quote:
            callout = re.match(r"\[!(\w+)\]\s*(.*)$", quote.group(1))
            if callout:
                html.append('<div class="callout {}"><b>{}</b><br>{}</div>'.format(
                    callout.group(1).lower(), callout.group(1).title(),
                    _inline(callout.group(2))))
            else:
                html.append("<blockquote>{}</blockquote>".format(_inline(quote.group(1))))
            index += 1
            continue
        if line.strip():
            html.append("<p>{}</p>".format(_inline(line)))
        index += 1
    if list_type:
        html.append("</{}>".format(list_type))
    if in_code:
        html.append("<pre><code>{}</code></pre>".format(_escape("\n".join(code))))
    base = ""
    if base_path:
        base = '<base href="file:///{}/">'.format(
            base_path.replace("\\", "/").replace(" ", "%20").rstrip("/"))
    scroll_script = ""
    if scroll_to:
        scroll_script = "<script>window.onload=function(){var e=document.getElementById('" \
            + scroll_to + "');if(e){e.scrollIntoView();}}</script>"
    return """<!doctype html><html><head><meta charset="utf-8">@@base@@<style>
body{font-family:'Segoe UI',Arial,sans-serif;background:@@bg@@;color:@@text@@;margin:26px 34px;line-height:1.45;font-size:14px}
h1,h2,h3,h4,h5,h6{color:@@text@@;font-weight:600;margin:1.15em 0 .45em}h1{font-size:28px}h2{font-size:22px}h3{font-size:18px}
p{margin:.55em 0}ol,ul{margin:8px 0;padding-left:26px}li{margin:1px 0;line-height:1.35}a{color:@@link@@}code,pre,blockquote{background:@@codebg@@}code{padding:2px 5px;border-radius:3px}pre{padding:14px;overflow:auto;border-left:3px solid @@link@@}blockquote{border-left:4px solid @@link@@;margin:12px 0;padding:4px 14px}mark{background:#d9b44a}.wikilink{color:@@link@@}img{max-width:100%}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13px}th,td{border:1px solid @@border@@;padding:7px 10px;text-align:left;vertical-align:top}th{background:@@codebg@@;font-weight:600}.callout{padding:10px 14px;margin:12px 0;border-left:4px solid @@link@@;background:@@codebg@@}
</style></head><body>@@content@@@@scroll@@</body></html>""".replace(
        "@@base@@", base).replace("@@content@@", "\n".join(html)).replace(
        "@@scroll@@", scroll_script)


def themed_html(text, palette, title="", base_path="", scroll_to=""):
    html = markdown_to_html(text, title, base_path, scroll_to)
    for key, value in (("bg", palette["BgPanel"]), ("text", palette["TextMain"]),
                       ("link", palette["SelBorder"]), ("codebg", palette["BgToolbar"]),
                       ("border", palette["BorderLight"])):
        html = html.replace("@@" + key + "@@", value)
    return html


def search_results_html(results, query, palette, title="Search", no_results="No matching documents.", count_label="Documents found: {n}"):
    """Render the Help home page search results with the shared palette."""
    if not (query or "").strip():
        return themed_html("", palette)
    query = _escape(query or "")
    blocks = []
    if not results:
        blocks.append("<p class=\"empty\">{}</p>".format(_escape(no_results)))
    else:
        blocks.append("<p class=\"count\">{}</p>".format(
            _escape(count_label.format(n=len(results)))))
        for path, snippet in results:
            href = path.replace("\\", "/").replace(" ", "%20")
            blocks.append("<article class=\"search-result\"><a href=\"help://open?path={0}\">{1}</a><p>{2}</p></article>".format(
                _escape(href), _escape(os.path.splitext(os.path.basename(path))[0]),
                _inline(snippet)))

    html = markdown_to_html("", base_path="")
    html = html.replace("</style>", "article.search-result{font-size:12px;border-bottom:1px solid @@border@@;padding:7px 0;margin:0}article.search-result a{font-size:12px;font-weight:600;text-decoration:none}article.search-result p{font-size:11px;margin:3px 0 0}</style>")
    html = html.replace("<body></body>", "<body>{}</body>".format("\n".join(blocks)))
    for key, value in (("bg", palette["BgPanel"]), ("text", palette["TextMain"]),
                       ("link", palette["SelBorder"]), ("codebg", palette["BgToolbar"]),
                       ("border", palette["BorderLight"])):
        html = html.replace("@@" + key + "@@", value)
    return html


def recent_results_html(results, palette):
    """Render recently viewed documents without a search header."""
    return search_results_html(results, "recent", palette,
                               no_results="", count_label="")
