import json
import xml.etree.ElementTree as ET
import httpx
import os
import re
import llm
from typing import List, Literal, Optional, TypedDict


CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


class ParsedArgument(TypedDict):
    bill_type: Literal["s", "hr"]
    bill_number: str
    congress: str
    mode: Literal["full", "toc", "section"]
    # Only present when mode="section"
    section: Optional[List[str]]


@llm.hookimpl
def register_fragment_loaders(register):
    if not CONGRESS_API_KEY:
        raise EnvironmentError("Missing CONGRESS_API_KEY environment variable")
    register("bill", bill_loader)


def parse_argument(argument: str) -> ParsedArgument:
    """
    Parse a bill argument string into its components.

    Args:
        argument: String in format "[type][number]-[congress][:section_spec]"
                 e.g., "hr1-119", "s123-118:toc", "hr456-119:section-1,2,3"

    Returns:
        Dictionary containing parsed components:
        - bill_type: 's' or 'hr'
        - bill_number: Bill number as string
        - congress: Congress number as string
        - mode: 'full', 'toc', or 'section'
        - section: List of section numbers (only when mode='section')

    Raises:
        ValueError: If bill ID format or section specification is invalid
    """
    # Split on first colon to separate bill ID from section specifier
    parts = argument.lower().split(":", 1)
    bill_id = parts[0]
    section_spec = parts[1] if len(parts) > 1 else None

    # Parse and validate bill ID format
    bill_match = re.match(r"^(s|hr)(\d+)-(\d+)$", bill_id)
    if not bill_match:
        raise ValueError(
            f"Invalid bill ID format: '{bill_id}'. "
            f"Expected format: [type][number]-[congress] (e.g., 'hr1-119')"
        )

    bill_type, bill_number, congress = bill_match.groups()
    if not bill_type in (
        "s",
        "hr",
    ):
        raise ValueError(
            f"Invalid bill type: '{bill_type}'. "
            f"Expected format: [type][number]-[congress] (e.g., 'hr1-119')"
        )

    # Parse section specification
    if section_spec is None:
        return ParsedArgument(
            bill_type=bill_type,
            bill_number=bill_number,
            congress=congress,
            mode="full",
            section=None,
        )
    elif section_spec == "toc":
        return ParsedArgument(
            bill_type=bill_type,
            bill_number=bill_number,
            congress=congress,
            mode="toc",
            section=None,
        )
    elif section_spec.startswith("section-"):
        section_part = section_spec.removeprefix("section-")
        sections = [s.strip() for s in section_part.split(",")]
        return ParsedArgument(
            bill_type=bill_type,
            bill_number=bill_number,
            congress=congress,
            mode="section",
            section=sections,
        )
    else:
        raise ValueError(
            f"Invalid section specification: '{section_spec}'. "
            f"Supported formats: 'toc', 'section-1', 'section-1,2,3'"
        )


def clean_str(s):
    return s.replace("\u2002", " ").strip()


def parse_xml_toc(xml_content: str):
    """
    Parse the table of contents from the bill XML

    Args:
        xml_content: A string containing the USLM XML data.

    Returns:
        A list of dictionaries, where each dictionary represents an item
        in the table of contents and contains 'role', 'designator', and 'label'.
        Returns an empty list if the table of contents is not found or is empty.
    """
    toc_items = []
    ns = {"uslm": "http://schemas.gpo.gov/xml/uslm"}
    root = ET.fromstring(xml_content)

    toc_element = root.find(".//uslm:toc", ns)
    if toc_element is not None:
        reference_items = toc_element.findall("uslm:referenceItem", ns)
        for item in reference_items:
            role = clean_str(item.get("role"))

            designator_element = item.find("uslm:designator", ns)
            designator_text = (
                clean_str(designator_element.text)
                if designator_element is not None and designator_element.text
                else None
            )

            label_element = item.find("uslm:label", ns)
            label_text = (
                clean_str(label_element.text)
                if label_element is not None and label_element.text
                else None
            )

            toc_items.append(
                {"role": role, "designator": designator_text, "label": label_text}
            )

    return toc_items


def bill_loader(argument: str) -> llm.Fragment:
    """
    Load bill text from Congress.gov
    Argument is a bill ID in the format [type][number]-[congress], e.g. "hr1-119" or "s1046-119"
    """

    bill = parse_argument(argument)
    api_url = f"https://api.congress.gov/v3/bill/{bill['congress']}/{bill['bill_type']}/{bill['bill_number']}/text?api_key={CONGRESS_API_KEY}"

    try:
        with httpx.Client() as client:
            response = client.get(api_url)
            response.raise_for_status()

            data = response.json()
            text_versions = data.get("textVersions", [])

            if DEBUG:
                os.makedirs("debug-responses", exist_ok=True)
                with open(f"debug-responses/{argument}_api.json", "w") as f:
                    json.dump(data, f)

            # Most recent bill versions first
            sorted_versions = sorted(
                text_versions, key=lambda x: x.get("date") or "", reverse=True
            )

            for version in sorted_versions:
                for format_info in version.get("formats", []):
                    if format_info.get("type") == "Formatted XML":
                        text_url = format_info.get("url")
                        if text_url:
                            text_response = client.get(text_url)
                            text_response.raise_for_status()

                            if DEBUG:
                                with open(
                                    f"debug-responses/{argument}_text.xml", "w"
                                ) as f:
                                    f.write(text_response.text)

                            return llm.Fragment(
                                content=text_response.text, source=text_url
                            )
            raise ValueError(f"No text available for bill {argument}")

    except Exception as e:
        raise ValueError(f"HTTP error fetching bill {argument}: {str(e)}")
