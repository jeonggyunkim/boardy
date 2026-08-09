from boardy.web.rules import RULEBOOKS, render_markdown, render_rulebook_page


def test_headers_and_paragraph():
    html = render_markdown("# Title\n\nSome text.\n")
    assert "<h1>Title</h1>" in html
    assert "<p>Some text.</p>" in html


def test_bold_spanning_a_wrapped_line():
    # a single list item wrapped across two source lines, with the **bold**
    # span crossing the wrap -- each line's raw text must be joined before
    # inline markup is applied, or the ** markers end up split apart and
    # never turn into <strong> (see render_markdown's block-based design).
    md = "- some **bold\n  words** here\n"
    html = render_markdown(md)
    assert "<strong>bold words</strong>" in html
    assert "**" not in html


def test_unordered_and_ordered_lists_dont_merge():
    md = "- a\n- b\n\n1. x\n2. y\n"
    html = render_markdown(md)
    assert html.count("<ul>") == 1
    assert html.count("<ol>") == 1
    assert "<li>a</li>" in html and "<li>x</li>" in html


def test_table():
    md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    html = render_markdown(md)
    assert "<table>" in html
    assert "<th>a</th><th>b</th>" in html
    assert "<td>1</td><td>2</td>" in html


def test_html_is_escaped():
    html = render_markdown("- <script>evil()</script>\n")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_rulebook_page_known_slugs():
    for slug in RULEBOOKS:
        page = render_rulebook_page(slug)
        assert page is not None
        assert "<html" in page


def test_render_rulebook_page_unknown_slug():
    assert render_rulebook_page("not_a_real_game") is None
