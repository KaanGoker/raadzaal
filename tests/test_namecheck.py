from raadzaal.namecheck import Checked, outsiders, resolve

ALLOWED = ["Kris Vincke", "Claudio Saelens"]


def test_members_are_not_outsiders():
    assert outsiders(Checked(key="1.nl", persons=["Claudio Saelens", "Vincke"], text=""), ALLOWED) == []
    assert outsiders(Checked(key="1.nl", persons=["Inga Goethals"], text=""), ALLOWED) == ["Inga Goethals"]


def test_rewrite_is_used_only_when_the_name_is_gone():
    orig = "Mevrouw Inga Goethals vroeg naar het fietspad."
    assert resolve(orig, "Een inwoner vroeg naar het fietspad.", ["Inga Goethals"], verbatim=False) == "Een inwoner vroeg naar het fietspad."
    assert resolve(orig, "Mevrouw Goethals vroeg naar het fietspad.", ["Inga Goethals"], verbatim=False) is None
    assert resolve(orig, None, ["Inga Goethals"], verbatim=False) is None
    assert resolve(orig, "x", [], verbatim=False) == orig


def test_a_quote_naming_an_outsider_is_dropped():
    assert resolve("Tine heeft dat opgevolgd.", "Een medewerker heeft dat opgevolgd.", ["Tine"], verbatim=True) is None


def test_a_surname_from_a_title_does_not_make_a_member_ambiguous():
    from raadzaal.namecheck import is_allowed
    allowed = ["Bram Peters", "Geoffroy de Visscher", "de Visscher", "Peeters"]
    assert is_allowed("Bram Peters", allowed) and is_allowed("de Visscher", allowed)
    assert not is_allowed("Inga Goethals", allowed)


def test_titled_names_are_always_candidates():
    from raadzaal.namecheck import titled_names
    assert titled_names("met de aanduiding van de heer André Matheuse als effectief en mevrouw Inga Goedhals als plaatsvervanger") == ["André Matheuse", "Inga Goedhals"]
    assert titled_names("Meneer Van der Dien vroeg iets") == ["Van der Dien"]
    assert titled_names("Mevrouw de voorzitter") == []
