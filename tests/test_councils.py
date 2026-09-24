from pathlib import Path

import yaml

from raadzaal import config


def test_every_council_file_parses_with_sourced_members():
    files = sorted(config.COUNCILS.glob("*.yaml"))
    assert {f.stem for f in files} >= {"haacht", "tervuren", "beernem"}
    for f in files:
        c = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert c["source"] and c["mayor"] and c["seats"]
        for m in c["members"]:
            assert m["name"] and m["party"] and m["role"]
        assert any(m["role"] == "burgemeester" for m in c["members"])
