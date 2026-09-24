from raadzaal.fetch import same_audio_as


def test_same_audio_as_finds_byte_identical_files(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    x = tmp_path / "a" / "x.m4a"; x.write_bytes(b"council" * 1000)
    y = tmp_path / "b" / "y.m4a"; y.write_bytes(b"council" * 1000)
    z = tmp_path / "b" / "z.m4a"; z.write_bytes(b"counciL" * 1000)
    assert same_audio_as(x, tmp_path) == y
    assert same_audio_as(z, tmp_path) is None
