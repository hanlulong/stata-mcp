#!/usr/bin/env python3
"""Graph auto-naming and cls filtering are pure text transforms; no Stata needed."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import stata_mcp_server as server
import stata_worker
from utils import auto_name_graph_lines, comment_out_cls_lines, insert_graph_name


def name_one(line: str) -> str:
    lines, _ = auto_name_graph_lines([line], 0)
    return lines[0]


@pytest.mark.parametrize(
    "line, expected",
    [
        # A comma inside a function call is not the option comma.
        (
            "scatter price mpg if inrange(mpg, 20, 30)",
            "scatter price mpg if inrange(mpg, 20, 30), name(graph1, replace)",
        ),
        (
            "histogram price if inlist(rep78, 3, 4), frequency",
            "histogram price if inlist(rep78, 3, 4), name(graph1, replace) frequency",
        ),
        (
            "twoway (scatter price mpg, mcolor(red)) (lfit price mpg)",
            "twoway (scatter price mpg, mcolor(red)) (lfit price mpg), name(graph1, replace)",
        ),
        # A comma inside a // comment is not an option comma either.
        (
            "histogram price // distribution, by origin",
            "histogram price, name(graph1, replace) // distribution, by origin",
        ),
        (
            'scatter y x, title("a, b")',
            'scatter y x, name(graph1, replace) title("a, b")',
        ),
        (
            'scatter y x if s == "a, b"',
            'scatter y x if s == "a, b", name(graph1, replace)',
        ),
        # // inside a string is not a comment.
        (
            'scatter y x, title("http://x")',
            'scatter y x, name(graph1, replace) title("http://x")',
        ),
        (
            'scatter y x if s == "http://x"',
            'scatter y x if s == "http://x", name(graph1, replace)',
        ),
        # Compound quotes, including nested ones and plain quotes inside.
        (
            'scatter y x, title(`"He said "a, b""\')',
            'scatter y x, name(graph1, replace) title(`"He said "a, b""\')',
        ),
        (
            'scatter y x if s == `"a `"b, c"\' d"\'',
            'scatter y x if s == `"a `"b, c"\' d"\', name(graph1, replace)',
        ),
        # Same as before the fix: first top-level comma.
        (
            "twoway scatter y x, mcolor(red) || lfit y x",
            "twoway scatter y x, name(graph1, replace) mcolor(red) || lfit y x",
        ),
        (
            "scatter y x, by(foreign)",
            "scatter y x, name(graph1, replace) by(foreign)",
        ),
        (
            "graph bar price, over(foreign)",
            "graph bar price, name(graph1, replace) over(foreign)",
        ),
        # Inline block comment before the options.
        (
            "scatter y x /* note, here */, title(a)",
            "scatter y x /* note, here */, name(graph1, replace) title(a)",
        ),
        (
            "  scatter y x",
            "  scatter y x, name(graph1, replace)",
        ),
    ],
)
def test_auto_name_inserts_name_at_the_option_comma(line, expected):
    assert name_one(line) == expected


def test_existing_name_is_unchanged_and_counter_not_advanced():
    lines, counter = auto_name_graph_lines(
        ["scatter y x, name(mine, replace)", "scatter y z"], 0
    )
    assert lines == ["scatter y x, name(mine, replace)", "scatter y z, name(graph1, replace)"]
    assert counter == 1


@pytest.mark.parametrize(
    "line",
    [
        'scatter y x, title("abc)',
        "scatter y x, title(abc",
        "scatter y x) , title(a)",
        'scatter y x, title(`"abc")',
    ],
)
def test_unbalanced_lines_are_left_unchanged(line):
    lines, counter = auto_name_graph_lines([line], 0)
    assert lines == [line]
    assert counter == 0
    assert insert_graph_name(line.split(" ", 1)[1], "graph1") is None


def test_delimit_semicolon_block_is_unchanged_and_naming_resumes_after_cr():
    lines = [
        "#delimit ;",
        "twoway (scatter price mpg)",
        "       (lfit price mpg), legend(off);",
        "#delimit cr",
        "scatter price mpg",
    ]
    out, counter = auto_name_graph_lines(lines, 0)
    assert out[:4] == lines[:4]
    assert out[4] == "scatter price mpg, name(graph1, replace)"
    assert counter == 1


@pytest.mark.parametrize("directive", ["#d ;", "#del ;", "#delim ;", "#DELIMIT ;", "#delimit;"])
def test_delimit_abbreviations(directive):
    out, counter = auto_name_graph_lines([directive, "scatter y x;", "#d cr", "scatter y x"], 0)
    assert out[1] == "scatter y x;"
    assert out[3] == "scatter y x, name(graph1, replace)"
    assert counter == 1


def test_graph_command_inside_block_comment_is_unchanged():
    lines = [
        "/* old version:",
        "scatter price mpg",
        "*/",
        "scatter price weight",
    ]
    out, counter = auto_name_graph_lines(lines, 0)
    assert out[:3] == lines[:3]
    assert out[3] == "scatter price weight, name(graph1, replace)"
    assert counter == 1


def test_counter_continues_from_start_counter():
    out, counter = auto_name_graph_lines(["scatter y x", "histogram y"], 3)
    assert out == ["scatter y x, name(graph4, replace)", "histogram y, name(graph5, replace)"]
    assert counter == 5


@pytest.mark.parametrize(
    "code, expected, count",
    [
        ("cls\n", "* COMMENTED OUT BY MCP: cls\n", 1),
        ("  CLS  \n", "* COMMENTED OUT BY MCP:   CLS  \n", 1),
        ('display "cls"\n', 'display "cls"\n', 0),
        ("di 1 ///\ncls\n", "di 1 ///\ncls\n", 0),
        ("sysuse auto\r\ncls\r\nsum", "sysuse auto\r\n* COMMENTED OUT BY MCP: cls\r\nsum", 1),
        ("cls", "* COMMENTED OUT BY MCP: cls", 1),
        ("", "", 0),
    ],
)
def test_comment_out_cls_lines(code, expected, count):
    assert comment_out_cls_lines(code) == (expected, count)


def test_preprocess_do_file_end_to_end(tmp_path):
    do_file = tmp_path / "graphs.do"
    do_file.write_text(
        "sysuse auto, clear\n"
        "scatter price mpg if inrange(mpg, 20, 30)\n"
        "histogram price if inlist(rep78, 3, 4), ///\n"
        "    frequency\n"
        "scatter price weight, name(graph2, replace)\n"
        "#delimit ;\n"
        "twoway (scatter price mpg)\n"
        "       (lfit price mpg);\n"
        "#delimit cr\n"
        "kdensity price\n",
        encoding="utf-8",
    )
    processed = server.preprocess_do_file_for_graphs(str(do_file))
    try:
        assert processed != str(do_file)
        with open(processed, encoding="utf-8") as f:
            content = f.read()
    finally:
        if processed != str(do_file):
            os.unlink(processed)

    assert content == (
        "sysuse auto, clear\n"
        "scatter price mpg if inrange(mpg, 20, 30), name(graph3, replace)\n"
        # /// continuations are joined first; the continued line keeps its indent.
        "histogram price if inlist(rep78, 3, 4), name(graph4, replace)     frequency\n"
        "scatter price weight, name(graph2, replace)\n"
        "#delimit ;\n"
        "twoway (scatter price mpg)\n"
        "       (lfit price mpg);\n"
        "#delimit cr\n"
        "kdensity price, name(graph5, replace)\n"
    )


def test_fixture_do_file_is_processed_without_errors():
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "graph_autoname.do")
    processed = server.preprocess_do_file_for_graphs(fixture)
    try:
        assert processed != fixture
        with open(processed, encoding="utf-8") as f:
            content = f.read()
    finally:
        if processed != fixture:
            os.unlink(processed)
    # The known-bad forms from before the fix must not appear.
    assert "inrange(mpg, name(" not in content
    assert "inlist(rep78, name(" not in content
    assert "(scatter price mpg, name(" not in content


def test_worker_filters_cls_in_both_execute_paths():
    # Multi-session runs (MCP stata_run_selection, /v1/tools and Run File)
    # go through the worker, which inlines the code; both paths must filter cls.
    import inspect

    source = inspect.getsource(stata_worker)
    assert source.count("comment_out_cls_lines(") >= 2
    assert "code, cls_commands_found = comment_out_cls_lines(code)" in source
    assert "original_code, cls_commands_found = comment_out_cls_lines(original_code)" in source
