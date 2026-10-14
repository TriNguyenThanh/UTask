import pytest

from common.content import clean_content


@pytest.mark.unit
@pytest.mark.parametrize(
    "html",
    [
        '<script>x</script><p onclick="x">Nội dung</p>',
        '<p>Nội dung</p><iframe src="evil"></iframe>',
    ],
)
def test_sanitize_excludes_active_content(html):
    safe, text, mentions = clean_content(html)
    assert safe == "<p>Nội dung</p>"
    assert text == "Nội dung"
    assert mentions == set()
