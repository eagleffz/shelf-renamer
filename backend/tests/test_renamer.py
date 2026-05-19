import os
import tempfile
import pytest
from app.models import Author, BookMetadata
from app.renamer import render_path_template, sanitize_filename, safe_rename, RenameError

LIB = "/media"


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
        is_file=False,
        file_extension="",
    )
    defaults.update(kwargs)
    return BookMetadata(**defaults)


def rpt(template: str, book: BookMetadata) -> str:
    return render_path_template(template, book, LIB)


def test_flat_template():
    book = _book()
    result = rpt("{author} - {title} ({year})", book)
    assert result == "/media/Terry Pratchett - Guards! Guards! (1989)"


def test_path_template_with_series():
    book = _book()
    result = rpt("{author}/{series}/{title} ({year})", book)
    assert result == "/media/Terry Pratchett/Discworld/Guards! Guards! (1989)"


def test_path_template_no_series_drops_segment():
    book = _book(series=None, series_index=None)
    result = rpt("{author}/{series}/{title}", book)
    assert result == "/media/Terry Pratchett/Guards! Guards!"


def test_author_lf():
    book = _book()
    result = rpt("{author_lf}/{title}", book)
    assert result == "/media/Pratchett, Terry/Guards! Guards!"


def test_series_index_integer():
    book = _book()
    result = rpt("{series}/{series_index} - {title}", book)
    assert result == "/media/Discworld/8 - Guards! Guards!"


def test_series_index_float():
    book = _book(series_index=1.5)
    result = rpt("{series_index}", book)
    assert result == "/media/1.5"


def test_missing_year_cleans_empty_parens():
    book = _book(published_year=None)
    result = rpt("{author}/{title} ({year})", book)
    assert "(" not in result
    assert ")" not in result
    assert "Terry Pratchett" in result


def test_multiple_authors():
    book = _book(authors=[
        Author(id="a1", name="Terry Pratchett"),
        Author(id="a2", name="Neil Gaiman"),
    ])
    result = rpt("{authors}/{title}", book)
    assert "Terry Pratchett & Neil Gaiman" in result


def test_file_item_extension_appended():
    book = _book(is_file=True, file_extension=".m4b")
    result = rpt("{author}/{title}", book)
    assert result == "/media/Terry Pratchett/Guards! Guards!.m4b"


def test_file_item_extension_only_on_last_segment():
    book = _book(is_file=True, file_extension=".m4b")
    result = rpt("{author}/{series}/{title}", book)
    parts = result.split("/")
    assert parts[-1].endswith(".m4b")
    assert not parts[-2].endswith(".m4b")


def test_sanitize_forbidden_chars():
    assert "/" not in sanitize_filename("AC/DC: Live")
    assert ":" not in sanitize_filename("AC/DC: Live")


def test_sanitize_strips_leading_trailing():
    assert sanitize_filename("  hello.  ") == "hello"


def test_unknown_variable_becomes_empty():
    book = _book()
    result = rpt("{unknown_var}/{title}", book)
    assert "unknown_var" not in result
    assert "Guards" in result


def test_safe_rename_success():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "old_name")
        dst = os.path.join(tmp, "new_name")
        os.makedirs(src)
        safe_rename(src, dst)
        assert os.path.exists(dst)
        assert not os.path.exists(src)


def test_safe_rename_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "old_name")
        dst = os.path.join(tmp, "Author", "Series", "new_name")
        os.makedirs(src)
        safe_rename(src, dst)
        assert os.path.exists(dst)


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
