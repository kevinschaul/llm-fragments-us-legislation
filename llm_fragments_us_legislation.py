"""
Congress.gov Bill Loader Plugin for LLM

This module provides functionality to load and parse bills from Congress.gov API.
Supports full text, table of contents, and specific sections.
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Literal, Optional, TypedDict, Union

import httpx
import llm


# Configuration
CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

# XML namespace for USLM documents
XML_NAMESPACE = {"uslm": "http://schemas.gpo.gov/xml/uslm"}


class ParsedArgument(TypedDict):
    """Typed dictionary for parsed bill arguments."""

    bill_type: Literal["s", "hr"]
    bill_number: str
    congress: str
    mode: Literal["full", "toc", "section"]
    section: Optional[List[str]]


class TOCItem(TypedDict):
    """Typed dictionary for table of contents items."""

    role: str
    designator: Optional[str]
    label: Optional[str]


@llm.hookimpl
def register_fragment_loaders(register):
    """Register the bill loader with the LLM framework."""
    if not CONGRESS_API_KEY:
        raise EnvironmentError("Missing CONGRESS_API_KEY environment variable")
    register("bill", bill_loader)


def parse_argument(argument: str) -> ParsedArgument:
    """
    Parse a bill argument string into its components.

    Args:
        argument: String in format "[type][number]-[congress][:section_spec]"
                 Examples: "hr1-119", "s123-118:toc", "hr456-119:section-1,2,3"

    Returns:
        ParsedArgument containing:
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
    parsed_bill = _parse_bill_id(bill_id)
    mode_info = _parse_section_spec(section_spec)

    return ParsedArgument(
        bill_type=parsed_bill["type"],
        bill_number=parsed_bill["number"],
        congress=parsed_bill["congress"],
        mode=mode_info["mode"],
        section=mode_info.get("sections"),
    )


def _parse_bill_id(bill_id: str) -> dict:
    """Parse and validate bill ID format."""
    bill_match = re.match(r"^(s|hr)(\d+)-(\d+)$", bill_id)
    if not bill_match:
        raise ValueError(
            f"Invalid bill ID format: '{bill_id}'. "
            "Expected format: [type][number]-[congress] (e.g., 'hr1-119')"
        )

    bill_type, bill_number, congress = bill_match.groups()
    if bill_type not in ("s", "hr"):
        raise ValueError(f"Invalid bill type: '{bill_type}'. Must be 's' or 'hr'")

    return {
        "type": bill_type,
        "number": bill_number,
        "congress": congress,
    }


def _parse_section_spec(section_spec: Optional[str]) -> dict:
    """Parse section specification into mode and sections."""
    if section_spec is None:
        return {"mode": "full"}

    if section_spec == "toc":
        return {"mode": "toc"}

    if section_spec.startswith("section-"):
        section_part = section_spec.removeprefix("section-")
        sections = [s.strip() for s in section_part.split(",")]
        return {"mode": "section", "sections": sections}

    raise ValueError(
        f"Invalid section specification: '{section_spec}'. "
        "Supported formats: 'toc', 'section-1', 'section-1,2,3'"
    )


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    return text.replace("\u2002", " ").strip()


def parse_xml_toc2(xml_content: str) -> str:
    """
    Parse the table of contents from bill XML and return as formatted string.

    Args:
        xml_content: String containing the USLM XML data

    Returns:
        Formatted string containing the table of contents
    """
    root = ET.fromstring(xml_content)
    toc_element = root.find(".//uslm:toc", XML_NAMESPACE)

    if toc_element is None:
        raise ValueError("No table of contents found in this bill.")

    toc_lines = ["TABLE OF CONTENTS", "=" * 18, ""]

    reference_items = toc_element.findall("uslm:referenceItem", XML_NAMESPACE)
    if not reference_items:
        return "Table of contents is empty."

    for item in reference_items:
        role = clean_text(item.get("role", ""))

        designator_element = item.find("uslm:designator", XML_NAMESPACE)
        designator_text = (
            clean_text(designator_element.text)
            if designator_element is not None and designator_element.text
            else ""
        )

        label_element = item.find("uslm:label", XML_NAMESPACE)
        label_text = (
            clean_text(label_element.text)
            if label_element is not None and label_element.text
            else ""
        )

        # Format the TOC entry
        if designator_text and label_text:
            toc_lines.append(f"{designator_text} {label_text}")
        elif designator_text:
            toc_lines.append(designator_text)
        elif label_text:
            toc_lines.append(f"[{role}] {label_text}")
        else:
            toc_lines.append(f"[{role}]")

    return "\n".join(toc_lines)


def parse_xml_toc(xml_content: str) -> str:
    """
    Parse the table of contents from bill XML and return as formatted string.

    Args:
        xml_content: String containing the USLM XML data

    Returns:
        Formatted string containing the table of contents
    """
    root = ET.fromstring(xml_content)
    # Try namespaced toc first, then fallback to non-namespaced toc
    toc_element = root.find(".//uslm:toc", XML_NAMESPACE)
    if toc_element is None:
        toc_element = root.find(".//toc")
    if toc_element is None:
        raise ValueError("No table of contents found in this bill.")

    toc_lines = ["TABLE OF CONTENTS", "=" * 18, ""]

    # Try namespaced referenceItem, then fallback to non-namespaced toc-entry
    reference_items = toc_element.findall("uslm:referenceItem", XML_NAMESPACE)
    if not reference_items:
        reference_items = toc_element.findall("toc-entry")
    if not reference_items:
        return "Table of contents is empty."

    for item in reference_items:
        # Try to extract designator and label, fallback to text content
        designator_element = (
            item.find("uslm:designator", XML_NAMESPACE)
            if item.tag.endswith("referenceItem")
            else None
        )
        designator_text = (
            clean_text(designator_element.text)
            if designator_element is not None and designator_element.text
            else ""
        )
        label_element = (
            item.find("uslm:label", XML_NAMESPACE)
            if item.tag.endswith("referenceItem")
            else None
        )
        label_text = (
            clean_text(label_element.text)
            if label_element is not None and label_element.text
            else ""
        )
        # For non-namespaced toc-entry, just use the text
        if not designator_text and not label_text and item.text:
            toc_lines.append(clean_text(item.text))
        elif designator_text and label_text:
            toc_lines.append(f"{designator_text} {label_text}")
        elif designator_text:
            toc_lines.append(designator_text)
        elif label_text:
            toc_lines.append(label_text)

    return "\n".join(toc_lines)


def parse_xml_section(xml_content: str, sections: list[str]) -> str:
    """
    Parse specific sections from bill XML and return plain text.
    Looks for <section> elements that start with "Sec. XXX", "Section XXX", or "XXX.".
    """
    root = ET.fromstring(xml_content)
    found = []

    # Helper function to get tag name without namespace
    def localname(tag):
        return tag.split("}")[-1] if "}" in tag else tag

    section_patterns = []
    for section_num in sections:
        patterns = [
            rf"^Sec\.\s+{re.escape(section_num)}\b",
            rf"^Section\s+{re.escape(section_num)}\b",
            rf"^{re.escape(section_num)}\.",
        ]
        section_patterns.append((section_num, patterns))

    for element in root.iter():
        if localname(element.tag) != "section":
            continue

        section_text = ET.tostring(element, encoding="unicode", method="text")
        found_match = False
        for section_num, patterns in section_patterns:
            for pattern in patterns:
                if re.search(pattern, section_text, re.IGNORECASE):
                    found.append(section_text)
                    found_match = True
                    break
            if found_match:
                break

    if len(found) < len(sections):
        found_section_nums = []
        for text in found:
            match = re.search(
                r"^(?:Sec\.|Section)\s+(\S+)|^(\S+)\.", text, re.IGNORECASE
            )
            if match:
                found_section_nums.append(match.group(1) or match.group(2))

        missing = set(sections) - set(found_section_nums)
        raise ValueError(f"Not all sections found. Missing: {', '.join(missing)}")

    return "\n\n".join(found)


def bill_loader(argument: str) -> llm.Fragment:
    """
    Load bill text from Congress.gov API.

    Args:
        argument: Bill ID in format [type][number]-[congress][:mode]
                 Examples: "hr1-119", "s1046-119:toc"

    Returns:
        llm.Fragment containing the requested bill content

    Raises:
        ValueError: If bill text is not available or argument format is invalid
        httpx.HTTPStatusError: If API request fails
    """
    parsed_argument = parse_argument(argument)

    with httpx.Client() as client:
        bill_data = _fetch_bill_data(client, parsed_argument, argument)
        return _process_bill_content(client, bill_data, parsed_argument, argument)


def _fetch_bill_data(
    client: httpx.Client, parsed_argument: ParsedArgument, argument: str
) -> dict:
    """Fetch bill metadata from Congress.gov API."""
    api_url = (
        f"https://api.congress.gov/v3/bill/"
        f"{parsed_argument['congress']}/{parsed_argument['bill_type']}/"
        f"{parsed_argument['bill_number']}/text"
        f"?api_key={CONGRESS_API_KEY}"
    )

    try:
        response = client.get(api_url)
        response.raise_for_status()
        data = response.json()

        _debug_save_response(data, f"{argument}_api.json")
        return data

    except httpx.HTTPStatusError as e:
        raise ValueError(f"Failed to fetch bill {argument}: {e}") from e


def _process_bill_content(
    client: httpx.Client,
    bill_data: dict,
    parsed_argument: ParsedArgument,
    argument: str,
) -> llm.Fragment:
    """Process bill data and return content based on requested mode."""
    text_versions = bill_data.get("textVersions", [])
    if not text_versions:
        raise ValueError(f"No text versions available for bill {argument}")

    # Get most recent version with XML format
    xml_url = _find_latest_xml_url(text_versions)
    if not xml_url:
        raise ValueError(f"No XML text format available for bill {argument}")

    return _fetch_and_parse_content(client, xml_url, parsed_argument, argument)


def _find_latest_xml_url(text_versions: List[dict]) -> Optional[str]:
    """Find XML format URL from the most recent text version."""
    # Sort versions by date (most recent first)
    sorted_versions = sorted(
        text_versions, key=lambda x: x.get("date") or "", reverse=True
    )

    # Find XML format in most recent versions
    for version in sorted_versions:
        xml_url = _extract_xml_url(version)
        if xml_url:
            return xml_url

    return None


def _extract_xml_url(version: dict) -> Optional[str]:
    """Extract XML format URL from a version dictionary."""
    for format_info in version.get("formats", []):
        if format_info.get("type") == "Formatted XML":
            return format_info.get("url")
    return None


def _fetch_and_parse_content(
    client: httpx.Client, text_url: str, parsed_argument: ParsedArgument, argument: str
) -> llm.Fragment:
    """Fetch XML content and parse according to specified mode."""
    try:
        response = client.get(text_url)
        response.raise_for_status()
        xml_content = response.text

        _debug_save_response(xml_content, f"{argument}_text.xml")

        # Process content based on mode
        content, source_suffix = _parse_content_by_mode(xml_content, parsed_argument)

        return llm.Fragment(content=content, source=text_url + source_suffix)

    except httpx.HTTPStatusError as e:
        raise ValueError(f"Failed to fetch bill text from {text_url}: {e}") from e


def _parse_content_by_mode(
    xml_content: str, parsed_argument: ParsedArgument
) -> tuple[str, str]:
    """Parse XML content according to the specified mode."""
    mode = parsed_argument["mode"]

    if mode == "full":
        return xml_content, "#full"

    elif mode == "toc":
        return parse_xml_toc(xml_content), "#toc"

    elif mode == "section":
        sections = parsed_argument["section"] or []
        content = parse_xml_section(xml_content, sections)
        return content, f"#section-{','.join(sections)}"

    else:
        raise ValueError(f"Unknown mode: {mode}")


def _debug_save_response(data: Union[dict, str], filename: str) -> None:
    """Save API response to file if DEBUG mode is enabled."""
    if not DEBUG:
        return

    os.makedirs("debug-responses", exist_ok=True)
    filepath = os.path.join("debug-responses", filename)

    if isinstance(data, str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(data)
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
