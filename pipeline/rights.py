"""Rights gate: Indian public-domain test on the metadata you enter in songs.yaml.

Indian Copyright Act: sound recordings run 60 years from the start of the calendar year after
publication; lyrics/music run for the author's life + 60 years from the start of the calendar year
after death. So in year T something is out of copyright if its year (publication / death) <= T - 61.

This checks YOUR entered data only. It does not verify it, and it says nothing about US or
platform (Meta) claims.
"""
import datetime


def check(song, today_year=None):
    """-> (allowed: bool, evidence: list[str]). Allowed also when a license_note is given."""
    limit = (today_year or datetime.date.today().year) - 61
    problems, evidence = [], []

    def test(label, year):
        if not isinstance(year, int):
            problems.append(f"{label}: year missing")
        elif year <= limit:
            evidence.append(f"{label} {year} <= {limit}: ok")
        else:
            problems.append(f"{label} {year} > {limit}: still protected in India")

    test("recording published", song.get("recording_year"))
    lyr = song.get("lyricist") or {}
    test(f"lyricist {lyr.get('name', '?')} died", lyr.get("death_year"))
    composers = song.get("composers") or []
    if not composers:
        problems.append("no composer listed")
    for c in composers:
        test(f"composer {c.get('name', '?')} died", c.get("death_year"))

    note = (song.get("license_note") or "").strip()
    if not problems:
        return True, evidence
    if note:
        return True, evidence + problems + [f"allowed on licence note: {note}"]
    return False, evidence + problems
