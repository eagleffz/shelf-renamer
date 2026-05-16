import pytest
from app.models import Author, BookMetadata
from app.renamer import render_template, sanitize_filename, safe_rename, RenameError
import os
import tempfile


def _book(**kwargs) -> BookMetadata:
    defaults = dict(
        id="1",
        library_id="lib1",
        title="Guards! Guards!",
        authors=[Author(id="a1", name="Terry Pratchett")],
        series="Discworld",
        series_index=8.0,
        published_year="1989",
        narrator="Nigel Planer",
        abs_path="/abs/books/Guards Guards",
        abs_library_root="/abs/books",
    )
    defaults.update(kwargs)
    return BookMetadata(**defaults)


def test_basic_template():
    book = _book()
    result = render_template("{author} - {title} ({year})", book)
    assert result == "Terry Pratchett - Guards! Guards! (1989)"


def test_author_lf():
    book = _book()
    result = render_template("{author_lf} - {title}", book)
    assert result == "Pratchett, Terry - Guards! Guards!"


def test_series_index_integer():
    book = _book(series_index=8.0)
    result = render_template("{series} {series_index}", book)
    assert result == "Discworld 8"


def test_series_index_float():
    book = _book(series_index=1.5)
    result = render_template("{series_index}", book)
    assert result == "1.5"


def test_missing_year_cleans_empty_parens():
    book = _book(published_year=None)
    result = render_template("{author} - {title} ({year})", book)
    assert "(" not in result
    assert ")" not in result
    assert "Terry Pratchett" in result


def test_missing_series_no_garbage():
    book = _book(series=None, series_index=None)
    result = render_template("{author} - {title} [{series}]", book)
    assert "[" not in result
    assert result.endswith(book.title) or result.endswith(book.title.replace(":", "-"))


def test_multiple_authors():
    book = _book(authors=[
        Author(id="a1", name="Terry Pratchett"),
        Author(id="a2", name="Neil Gaiman"),
    ])
    result = render_template("{authors} - {title}", book)
    assert "Terry Pratchett & Neil Gaiman" in result


def test_sanitize_forbidden_chars():
    assert "/" not in sanitize_filename("AC/DC: Live")
    assert ":" not in sanitize_filename("AC/DC: Live")


def test_sanitize_strips_leading_trailing():
    assert sanitize_filename("  hello.  ") == "hello"


def test_unknown_variable_becomes_empty():
    book = _book()
    # should not raise
    result = render_template("{unknown_var} - {title}", book)
    assert "unknown_var" not in result


def test_safe_rename_success():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "old_name")
        dst = os.path.join(tmp, "new_name")
        os.makedirs(src)
        safe_rename(src, dst)
        assert os.path.exists(dst)
        assert not os.path.exists(src)


def test_safe_rename_missing_source():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(RenameError, match="Source does not exist"):
            safe_rename(os.path.join(tmp, "nonexistent"), os.path.join(tmp, "dst"))


def test_safe_rename_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src")
        dst = os.path.join(tmp, "dst")
        os.makedirs(src)
        os.makedirs(dst)
        with pytest.raises(RenameError, match="Target already exists"):
            safe_rename(src, dst)
