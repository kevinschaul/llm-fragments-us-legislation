import httpx
import os
import re
import llm

CONGRESS_API_KEY = os.environ.get("CONGRESS_API_KEY")


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

            # Most recent bill versions first
            sorted_versions = sorted(
                text_versions, key=lambda x: x.get("date", ""), reverse=True
            )

            for version in sorted_versions:
                for format_info in version.get("formats", []):
                    if format_info.get("type") == "Formatted Text":
                        text_url = format_info.get("url")
                        if text_url:
                            text_response = client.get(text_url)
                            text_response.raise_for_status()
                            return llm.Fragment(
                                content=text_response.text, source=text_url
                            )
            raise ValueError(f"No text available for bill {argument}")

    except Exception as e:
        raise ValueError(
            f"HTTP error fetching bill {argument}: {str(e)}"
        )
