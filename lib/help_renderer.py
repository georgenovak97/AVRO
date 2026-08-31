# -*- coding: utf-8 -*-
"""Small dependency-free Markdown renderer suitable for Obsidian notes."""
import re


def _escape(value):
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _inline(value):
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


def markdown_to_html(text, title="", base_path=""):
    lines = (text or "").replace("\r\n", "\n").split("\n")
    html = []
    in_code = False
    in_list = False
    code = []
    for line in lines:
        fence = re.match(r"^\s*```\s*(.*)$", line)
        if fence:
            if in_code:
                html.append("<pre><code>{}</code></pre>".format(
                    _escape("\n".join(code))))
                code = []
                in_code = False
            else:
                if in_list:
                    html.append("</ul>")
                    in_list = False
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            level = len(heading.group(1))
            value = heading.group(2).strip()
            html.append('<h{0} id="{1}">{2}</h{0}>'.format(
                level, _slug(value), _inline(value)))
            continue
        if re.match(r"^\s*[-*_](\s*[-*_]){2,}\s*$", line):
            html.append("<hr>")
            continue
        item = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if item:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append("<li>{}</li>".format(_inline(item.group(1))))
            continue
        if in_list:
            html.append("</ul>")
            in_list = False
        quote = re.match(r"^\s*>\s*(.*)$", line)
        if quote:
            callout = re.match(r"\[!(\w+)\]\s*(.*)$", quote.group(1))
            if callout:
                html.append('<div class="callout {}"><b>{}</b><br>{}</div>'.format(
                    callout.group(1).lower(), callout.group(1).title(),
                    _inline(callout.group(2))))
            else:
                html.append("<blockquote>{}</blockquote>".format(_inline(quote.group(1))))
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.match(r"^:?-+:?$", c) for c in cells):
                html.append("<p class=\"table-row\">{}</p>".format(
                    "".join("<span>{}</span>".format(_inline(c)) for c in cells)))
            continue
        if line.strip():
            html.append("<p>{}</p>".format(_inline(line)))
    if in_list:
        html.append("</ul>")
    if in_code:
        html.append("<pre><code>{}</code></pre>".format(_escape("\n".join(code))))
    base = ""
    if base_path:
        base = '<base href="file:///{}/">'.format(
            base_path.replace("\\", "/").replace(" ", "%20").rstrip("/"))
    return """<!doctype html><html><head><meta charset="utf-8">@@base@@<style>
body{font-family:'Segoe UI',Arial,sans-serif;background:@@bg@@;color:@@text@@;margin:26px 34px;line-height:1.55;font-size:14px}
h1,h2,h3,h4{color:@@text@@;font-weight:600}a{color:@@link@@}code,pre,blockquote{background:@@codebg@@}code{padding:2px 5px}pre{padding:14px;overflow:auto;border-left:3px solid @@link@@}blockquote{border-left:4px solid @@link@@;padding:4px 14px}mark{background:#d9b44a}.wikilink{color:@@link@@}img{max-width:100%}.table-row{display:flex;border-bottom:1px solid @@border@@}.table-row span{flex:1;padding:6px 9px}.callout{padding:10px 14px;margin:12px 0;border-left:4px solid @@link@@;background:@@codebg@@}
</style></head><body>@@content@@</body></html>""".replace(
        "@@base@@", base).replace("@@content@@", "\n".join(html))


def themed_html(text, palette, title="", base_path=""):
    html = markdown_to_html(text, title, base_path)
    for key, value in (("bg", palette["BgPanel"]), ("text", palette["TextMain"]),
                       ("link", palette["SelBorder"]), ("codebg", palette["BgToolbar"]),
                       ("border", palette["BorderLight"])):
        html = html.replace("@@" + key + "@@", value)
    return html
