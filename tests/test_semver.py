from nodus.runtime.semver import Version, VersionRange


def test_version_parse_and_compare():
    v1 = Version.parse("1.2.3")
    v2 = Version.parse("1.2.4")
    v3 = Version.parse("1.2")
    assert v1 < v2
    assert v3 == Version(1, 2, 0)


def test_caret_range():
    rng = VersionRange.parse("^1.2.3")
    assert rng.matches(Version.parse("1.2.3"))
    assert rng.matches(Version.parse("1.9.9"))
    assert not rng.matches(Version.parse("2.0.0"))


def test_tilde_range():
    rng = VersionRange.parse("~1.3")
    assert rng.matches(Version.parse("1.3.0"))
    assert rng.matches(Version.parse("1.3.9"))
    assert not rng.matches(Version.parse("1.4.0"))


def test_comparator_range():
    rng = VersionRange.parse(">=1.0,<2.0")
    assert rng.matches(Version.parse("1.0.0"))
    assert rng.matches(Version.parse("1.9.9"))
    assert not rng.matches(Version.parse("2.0.0"))
