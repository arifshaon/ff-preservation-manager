from registry_builder.utils import read_uri


def test_read_uri_reads_plain_local_path(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("hello", encoding="utf-8")

    data, headers = read_uri(str(path))

    assert data == b"hello"
    assert headers == {}


def test_read_uri_reads_file_uri_with_escaped_spaces(tmp_path):
    directory = tmp_path / "folder with spaces"
    directory.mkdir()
    path = directory / "source file.txt"
    path.write_text("hello from file uri", encoding="utf-8")

    data, headers = read_uri(path.as_uri())

    assert data == b"hello from file uri"
    assert headers == {}
