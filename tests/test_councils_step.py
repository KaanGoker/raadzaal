from raadzaal import councils


def test_current_members_merges_roles_and_drops_ended_mandates():
    rows = [
        {"m": "a", "rol": "Gemeenteraadslid", "voornaam": "Jos", "naam": "Sypré", "start": "2024-12-01T23:00:00Z", "fractie": "cd&v"},
        {"m": "b", "rol": "Burgemeester", "voornaam": "Jos", "naam": "Sypré", "start": "2025-01-15T00:00:00Z", "fractie": None},
        {"m": "c", "rol": "Aangewezen burgemeester", "voornaam": "Jos", "naam": "Sypré", "start": "2024-12-01T23:00:00Z",
         "einde": "2025-01-14T23:59:59Z", "fractie": None},
        {"m": "d", "rol": "Gemeenteraadslid", "voornaam": "Piet", "naam": "Oud", "start": "2024-12-01T23:00:00Z",
         "einde": "2026-05-21T21:59:59Z", "fractie": "N-VA"},
        {"m": "e", "rol": "Voorzitter van de gemeenteraad", "voornaam": "Kris", "naam": "Vincke", "start": "2025-01-02T00:00:00Z", "fractie": "cd&v"},
    ]
    out = councils.current_members(rows, "2026-09-24")
    by = {m["name"]: m for m in out}
    assert set(by) == {"Jos Sypré", "Kris Vincke"}
    assert by["Jos Sypré"]["role"] == "burgemeester" and by["Jos Sypré"]["party"] == "CD&V"
    assert by["Kris Vincke"]["role"] == "voorzitter"
    assert out[0]["name"] == "Jos Sypré"  # mayor first


def test_party_label():
    assert councils.party_label("VLAAMS BELANG") == "Vlaams Belang"
    assert councils.party_label("Vooruit Beernem") == "Vooruit"
    assert councils.party_label("Tervuren Unie + Volt") == "Tervuren Unie + Volt"
    assert councils.party_label(None) is None
