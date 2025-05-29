import textwrap
import pytest
import httpx
import respx
from pathlib import Path
from llm.plugins import load_plugins, pm

from llm_fragments_us_legislation import bill_loader, parse_argument, parse_xml_toc


def test_plugin_is_installed():
    load_plugins()
    names = [mod.__name__ for mod in pm.get_plugins()]
    assert "llm_fragments_us_legislation" in names


@pytest.mark.parametrize(
    "input_arg,expected_bill_type,expected_bill_number,expected_congress",
    [
        ("hr1-119", "hr", "1", "119"),
        ("s5-118", "s", "5", "118"),
    ],
)
def test_parse_argument(
    input_arg, expected_bill_type, expected_bill_number, expected_congress
):
    actual = parse_argument(input_arg)
    assert actual["bill_type"] == expected_bill_type
    assert actual["bill_number"] == expected_bill_number
    assert actual["congress"] == expected_congress


@pytest.mark.parametrize(
    "invalid_input",
    [
        "hr",
        "hr1",
        "1-119",
        "hr-119",
        "hr1-",
        "",
    ],
)
def test_parse_argument_invalid(invalid_input):
    with pytest.raises(ValueError):
        parse_argument(invalid_input)


@respx.mock
def test_bill_loader_success():
    text_versions_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    formatted_text_url = "https://some.text.url"

    respx.get(text_versions_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2020-05-01",
                        "formats": [
                            {"type": "Old version formatted Text", "url": "old url"}
                        ],
                    },
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "Formatted Text", "url": formatted_text_url}
                        ],
                    },
                ]
            },
        )
    )

    respx.get(formatted_text_url).mock(
        return_value=httpx.Response(200, text="Full bill text here")
    )

    fragment = bill_loader("hr1-119")
    assert "Full bill text here" in str(fragment)
    assert fragment.source == formatted_text_url


@respx.mock
def test_bill_loader_no_text_versions():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"

    respx.get(api_url).mock(return_value=httpx.Response(200, json={"textVersions": []}))

    with pytest.raises(ValueError, match="No text available for bill hr1-119"):
        bill_loader("hr1-119")


class TestParseXML:
    @pytest.fixture
    def hr1968_119_text(self):
        with open(Path(__file__).parent / "fixtures/hr1968-119_text.xml") as f:
            return "\n".join(f.readlines())

    def test_parse_xml_toc(self, hr1968_119_text):
        actual = parse_xml_toc(hr1968_119_text)
        assert actual[0] == {
            "designator": "Sec. 1.",
            "label": "Short title.",
            "role": "section",
        }
