# llm-fragments-us-legislation

[![PyPI](https://img.shields.io/pypi/v/llm-fragments-us-legislation.svg)](https://pypi.org/project/llm-fragments-us-legislation/)
[![Changelog](https://img.shields.io/github/v/release/kevinschaul/llm-fragments-us-legislation?include_prereleases&label=changelog)](https://github.com/kevinschaul/llm-fragments-us-legislation/releases)
[![Tests](https://github.com/kevinschaul/llm-fragments-us-legislation/actions/workflows/test.yml/badge.svg)](https://github.com/kevinschaul/llm-fragments-us-legislation/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/kevinschaul/llm-fragments-us-legislation/blob/main/LICENSE)

Load bills from Congress.gov as LLM fragments

## Installation

Install this plugin in the same environment as [LLM](https://llm.datasette.io/).

```bash
llm install llm-fragments-us-legislation
```

## Usage

First set the environment variable `CONGRESS_API_KEY` ([sign up for a key here](https://api.congress.gov/sign-up/)).

Then you can load in a bill like so:

```bash
# This bill is yuge, so use a model with enough context!
llm -f bill:hr1-119 'Summarize this bill' -m gemini-2.5-pro-preview-05-06
```

### Bill fragment format

```
bill:BILL_ID[:OPTION]
```

Where:

- `BILL_ID` follows the format `[type][number]-[congress]`
  - `type`: `hr` (House) or `s` (Senate)
  - `number`: Bill number
  - `congress`: Congress session number
- `OPTION` (optional): Specifies what content to retrieve

### Basic Examples

```bash
# Load full bill text
llm -f bill:hr1-119 'Summarize this bill' -m gemini-2.5-pro-preview-05-06

# Load table of contents only
llm -f bill:hr1-119:toc 'What are the main sections of this bill?'

# Load a specific section
llm -f bill:hr1-119:section-110101 'Is there language in here to prevent fraud?'

# Load multiple sections
llm -f bill:hr1-119:section-80101,80121 'What does this Alaska section do differently than the non-Alaska sections?'

# Store local responses of API calls with DEBUG=1
DEBUG=1 llm -f bill:hr1-119:section-80101,80121 'What does this Alaska section do differently than the non-Alaska sections?'
```

### Available Options

| Option          | Description                  | Example                      |
| --------------- | ---------------------------- | ---------------------------- |
| (none)          | Full bill text in XML format | `bill:hr1-119`               |
| `toc`           | Table of contents only       | `bill:hr1-119:toc`           |
| `section-N`     | Specific section by number   | `bill:hr1-119:section-1`     |
| `section-N,M,P` | Multiple sections            | `bill:hr1-119:section-1,3,5` |

### Bill ID Examples

- `hr1-119` - House Resolution 1 from the 119th Congress
- `s1046-118` - Senate Bill 1046 from the 118th Congress
- `hr2-117` - House Resolution 2 from the 117th Congress

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:

```bash
cd llm-fragments-us-legislation
python -m venv venv
source venv/bin/activate
```

Now install the dependencies and test dependencies:

```bash
python -m pip install -e '.[test]'
```

To run the tests:

```bash
python -m pytest
```
