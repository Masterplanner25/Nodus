from nodus.tooling.formatter import format_source

def test_format_foreach():
    src = """
for item in items {
total = total + item
}
"""
    out = format_source(src)

    assert "for item in items {" in out