import json
import xml.etree.ElementTree as ET
import httpx
import os
import re
import llm

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


@llm.hookimpl
def register_fragment_loaders(register):
    if not CONGRESS_API_KEY:
        raise EnvironmentError("Missing CONGRESS_API_KEY environment variable")
    register("bill", bill_loader)


def parse_argument(argument: str):
    match = re.match(r"^([a-z]+)(\d+)-(\d+)$", argument.lower())
    if not match:
        raise ValueError(
            f"Invalid bill ID format: {argument}. Expected format: [type][number]-[congress] (e.g., 'hr1-119')"
        )

    bill_type, bill_number, congress = match.groups()

    return {
        "bill_type": bill_type,
        "bill_number": bill_number,
        "congress": congress,
    }


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
    try:
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

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

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
