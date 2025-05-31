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
    "input_arg,expected_bill_type,expected_bill_number,expected_congress,expected_mode,expected_section",
    [
        ("hr1-119", "hr", "1", "119", "full", None),
        ("s5-118", "s", "5", "118", "full", None),
        ("hr1-119:toc", "hr", "1", "119", "toc", None),
        ("hr1-119:section-1", "hr", "1", "119", "section", ["1"]),
        ("hr1-119:section-1,3,5", "hr", "1", "119", "section", ["1", "3", "5"]),
        ("s5-118:section-42", "s", "5", "118", "section", ["42"]),
        (
            "hr100-117:section-1,2,3,4",
            "hr",
            "100",
            "117",
            "section",
            ["1", "2", "3", "4"],
        ),
    ],
)
def test_parse_argument(
    input_arg,
    expected_bill_type,
    expected_bill_number,
    expected_congress,
    expected_mode,
    expected_section,
):
    actual = parse_argument(input_arg)
    assert actual["bill_type"] == expected_bill_type
    assert actual["bill_number"] == expected_bill_number
    assert actual["congress"] == expected_congress
    assert actual["mode"] == expected_mode
    assert actual["section"] == expected_section


@pytest.mark.parametrize(
    "invalid_input",
    [
        "hr",
        "hr1",
        "1-119",
        "hr-119",
        "hr1-",
        "h1-119",
        "",
        "hr-119:",
        "hr-119:invalid",
        "hr-119:section-",
    ],
)
def test_parse_argument_invalid(invalid_input):
    with pytest.raises(ValueError):
        parse_argument(invalid_input)


@respx.mock
def test_bill_loader_success():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    formatted_text_url = "https://some.text.url"

    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2020-05-01",
                        "formats": [{"type": "Formatted XML", "url": "old url"}],
                    },
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "Formatted XML", "url": formatted_text_url}
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
    assert fragment.source == formatted_text_url + "#full"


@respx.mock
def test_bill_loader_no_text_versions():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    respx.get(api_url).mock(return_value=httpx.Response(200, json={"textVersions": []}))

    with pytest.raises(ValueError, match="No text versions available for bill hr1-119"):
        bill_loader("hr1-119")


@respx.mock
def test_bill_loader_no_xml_format():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "PDF", "url": "https://some.pdf.url"},
                            {"type": "HTML", "url": "https://some.html.url"},
                        ],
                    },
                ]
            },
        )
    )

    with pytest.raises(
        ValueError, match="No XML text format available for bill hr1-119"
    ):
        bill_loader("hr1-119")


@respx.mock
def test_bill_loader_toc_mode():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    formatted_text_url = "https://some.text.url"
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <bill xmlns:uslm="http://schemas.gpo.gov/xml/uslm">
        <uslm:toc>
            <uslm:referenceItem role="section">
                <uslm:designator>Sec. 1.</uslm:designator>
                <uslm:label>Short title.</uslm:label>
            </uslm:referenceItem>
            <uslm:referenceItem role="section">
                <uslm:designator>Sec. 2.</uslm:designator>
                <uslm:label>Definitions.</uslm:label>
            </uslm:referenceItem>
        </uslm:toc>
    </bill>"""

    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "Formatted XML", "url": formatted_text_url}
                        ],
                    },
                ]
            },
        )
    )

    respx.get(formatted_text_url).mock(
        return_value=httpx.Response(200, text=xml_content)
    )

    fragment = bill_loader("hr1-119:toc")
    assert "TABLE OF CONTENTS" in str(fragment)
    assert "Sec. 1. Short title." in str(fragment)
    assert "Sec. 2. Definitions." in str(fragment)
    assert fragment.source == formatted_text_url + "#toc"


@respx.mock
def test_bill_loader_section_mode():
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    formatted_text_url = "https://some.text.url"
    xml_content = "<bill>Sample XML content</bill>"

    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "Formatted XML", "url": formatted_text_url}
                        ],
                    },
                ]
            },
        )
    )

    respx.get(formatted_text_url).mock(
        return_value=httpx.Response(200, text=xml_content)
    )

    fragment = bill_loader("hr1-119:section-1,2")
    # Since parse_xml_section is a TODO, we expect the placeholder message
    assert "TODO: Extract sections 1, 2 from XML content" in str(fragment)
    assert fragment.source == formatted_text_url + "#section-1,2"


class TestParseXML:
    @pytest.fixture
    def hr1_119_text(self):
        with open(Path(__file__).parent / "fixtures/hr1-119_text.xml") as f:
            return "\n".join(f.readlines())

    @pytest.fixture
    def hr1968_119_text(self):
        with open(Path(__file__).parent / "fixtures/hr1968-119_text.xml") as f:
            return "\n".join(f.readlines())

    def test_parse_xml_toc_hr1_119(self, hr1_119_text):
        actual = parse_xml_toc(hr1_119_text)
        assert isinstance(actual, str)
        assert "TABLE OF CONTENTS" in actual
        assert "Sec. 1. Short title." in actual

    def test_parse_xml_toc_hr1_119_simplified(self):
        """Test parsing TOC with missing designator or label elements."""
        xml_content = """
            <?xml version="1.0"?>
            <?xml-stylesheet type="text/xsl" href="billres.xsl"?>
            <!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN" "bill.dtd">
            <bill bill-stage="Engrossed-in-House" dms-id="H1A4CA848BA0D4E44B871A725917D2613" public-private="public" key="H" bill-type="olc" stage-count="1"> 
            <form> 
            <distribution-code display="no">I</distribution-code> 
            <congress>119th CONGRESS</congress> <session>1st Session</session> 
            <legis-num>H. R. 1</legis-num> 
            <current-chamber display="no">IN THE HOUSE OF REPRESENTATIVES</current-chamber> 
            <legis-type>AN ACT</legis-type> 
            <official-title display="yes">To provide for reconciliation pursuant to title II of H. Con. Res. 14.</official-title> 
            </form> 
            <legis-body id="H48AB3B4D6A6844059B8764EE4AE54038" style="OLC"> 
            <section id="H2131D31F49754E41B3D41DA67FCD59A1" section-type="section-one"><enum>1.</enum><header>Short title</header><text display-inline="no-display-inline">This Act may be cited as the <quote>One Big Beautiful Bill Act</quote>.</text></section> 
            <section id="HBC5BE06C78A1437D86ED974E239EC662"><enum>2.</enum><header>Table of contents</header><text display-inline="no-display-inline">The table of contents of this Act is as follows:</text>
            <toc container-level="legis-body-container" quoted-block="no-quoted-block" lowest-level="section" regeneration="yes-regeneration" lowest-bolded-level="division-lowest-bolded">
            <toc-entry idref="H2131D31F49754E41B3D41DA67FCD59A1" level="section">Sec. 1. Short title.</toc-entry> 

        """

        actual = parse_xml_toc(xml_content)
        assert "TABLE OF CONTENTS" in actual
        assert "Sec. 1." in actual
        assert "[subsection] Missing designator." in actual
        assert "[title]" in actual

    def test_parse_xml_toc(self, hr1968_119_text):
        actual = parse_xml_toc(hr1968_119_text)
        assert isinstance(actual, str)
        assert "TABLE OF CONTENTS" in actual
        assert "Sec. 1. Short title." in actual

    def test_parse_xml_toc_empty(self):
        """Test parsing XML without a table of contents."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <bill xmlns:uslm="http://schemas.gpo.gov/xml/uslm">
            <body>
                <section>Content without TOC</section>
            </body>
        </bill>"""

        with pytest.raises(
            ValueError, match="No table of contents found in this bill."
        ):
            parse_xml_toc(xml_content)

    def test_parse_xml_toc_with_missing_elements(self):
        """Test parsing TOC with missing designator or label elements."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <bill xmlns:uslm="http://schemas.gpo.gov/xml/uslm">
            <uslm:toc>
                <uslm:referenceItem role="section">
                    <uslm:designator>Sec. 1.</uslm:designator>
                </uslm:referenceItem>
                <uslm:referenceItem role="subsection">
                    <uslm:label>Missing designator.</uslm:label>
                </uslm:referenceItem>
                <uslm:referenceItem role="title">
                </uslm:referenceItem>
            </uslm:toc>
        </bill>"""

        actual = parse_xml_toc(xml_content)
        assert "TABLE OF CONTENTS" in actual
        assert "Sec. 1." in actual
        assert "[subsection] Missing designator." in actual
        assert "[title]" in actual


@respx.mock
def test_bill_loader_api_error():
    """Test handling of API errors."""
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    respx.get(api_url).mock(return_value=httpx.Response(404))

    with pytest.raises(ValueError, match="Failed to fetch bill hr1-119"):
        bill_loader("hr1-119")


@respx.mock
def test_bill_loader_text_fetch_error():
    """Test handling of text fetch errors."""
    api_url = "https://api.congress.gov/v3/bill/119/hr/1/text"
    formatted_text_url = "https://some.text.url"

    respx.get(api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "textVersions": [
                    {
                        "date": "2024-05-01",
                        "formats": [
                            {"type": "Formatted XML", "url": formatted_text_url}
                        ],
                    },
                ]
            },
        )
    )

    # Mock text URL to return 404
    respx.get(formatted_text_url).mock(return_value=httpx.Response(404))

    with pytest.raises(
        ValueError, match=f"Failed to fetch bill text from {formatted_text_url}"
    ):
        bill_loader("hr1-119")
