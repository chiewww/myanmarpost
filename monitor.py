import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar


BASE_URL = "https://myanmarpost.com.mm"
PRICING_URL = f"{BASE_URL}/pricing?tab=international"

# Ordinary letter maximum weight.
# 20 grams = 0.02 kg
MAX_LETTER_WEIGHT_KG = 0.02

# HTTP settings
REQUEST_TIMEOUT = 120
MAX_PRICING_ATTEMPTS = 3
RETRY_DELAYS = (1, 3, 6)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


class MyanmarPostClient:
    """
    Small HTTP client for Myanmar Post.

    The pricing page uses Inertia.  The old script hard-coded an
    X-Inertia-Version value, which can become invalid after the website
    deploys a new frontend.  This client first loads /pricing, discovers
    the current Inertia version, and then uses that version for the
    international pricing request.
    """

    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.inertia_version = None

    def _request(self, url, headers=None):
        request = urllib.request.Request(
            url,
            headers=headers or {},
            method="GET",
        )

        try:
            with self.opener.open(
                request,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                body = response.read()
                content_type = response.headers.get(
                    "Content-Type",
                    "",
                )

                return (
                    response.status,
                    content_type,
                    body,
                    dict(response.headers),
                )

        except urllib.error.HTTPError as e:
            body = e.read()

            print(f"HTTP error {e.code} for {url}")
            print(f"Reason: {e.reason}")
            print(f"Response body length: {len(body)} bytes")

            if body:
                print("Response body:")
                print(
                    body[:2000].decode(
                        "utf-8",
                        errors="replace",
                    )
                )
            else:
                print("Response body is empty.")

            print("Response headers:")
            for key, value in e.headers.items():
                print(f"  {key}: {value}")

            raise

    def _browser_headers(self, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html, "
                "application/xhtml+xml, "
                "application/json;q=0.9, "
                "*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        if referer:
            headers["Referer"] = referer

        return headers

    def _extract_inertia_version(self, body):
        """
        Extract the current Inertia version from the initial /pricing HTML.

        Inertia normally places its page data in a data-page attribute.
        This function also has a fallback regex in case the exact HTML
        structure changes slightly.
        """
        text = body.decode(
            "utf-8",
            errors="replace",
        )

        # First try the normal Inertia data-page attribute.
        match = re.search(
            r'data-page\s*=\s*(["\'])(.*?)\1',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            raw_page = html.unescape(match.group(2))

            try:
                page_data = json.loads(raw_page)
                version = page_data.get("version")

                if isinstance(version, str) and version.strip():
                    return version.strip()

            except json.JSONDecodeError:
                pass

            # If the attribute was valid HTML but the page JSON changed
            # slightly, search the decoded attribute for "version".
            version_match = re.search(
                r'"version"\s*:\s*"([^"]+)"',
                raw_page,
                flags=re.IGNORECASE,
            )

            if version_match:
                return version_match.group(1).strip()

        # Fallback: search the complete HTML.
        decoded_text = html.unescape(text)

        version_match = re.search(
            r'"version"\s*:\s*"([^"]+)"',
            decoded_text,
            flags=re.IGNORECASE,
        )

        if version_match:
            return version_match.group(1).strip()

        return None

    def refresh_inertia_version(self):
        """
        Load the normal pricing page and discover the current Inertia
        version.  This also establishes cookies/session state.
        """
        print("Loading Myanmar Post pricing page...")
        url = f"{BASE_URL}/pricing"

        status, content_type, body, response_headers = self._request(
            url,
            self._browser_headers(),
        )

        print(
            f"Pricing page: HTTP {status}, "
            f"{content_type}, {len(body)} bytes"
        )

        version = self._extract_inertia_version(body)

        if not version:
            print(
                "Could not find the current Inertia version in "
                "the /pricing HTML."
            )
            print("First 2000 characters of the page:")
            print(
                body[:2000].decode(
                    "utf-8",
                    errors="replace",
                )
            )
            raise RuntimeError(
                "Could not determine Myanmar Post's current "
                "Inertia version."
            )

        self.inertia_version = version
        print(
            f"Detected current Inertia version: "
            f"{self.inertia_version}"
        )

        return version

 def get_pricing_data(self):
    """
    Load the normal pricing page and extract its Inertia
    data-page payload.

    This avoids the /pricing?tab=international Inertia
    request, which currently returns HTTP 500.
    """
    print("Loading Myanmar Post pricing page...")

    url = f"{BASE_URL}/pricing"

    status, content_type, body, response_headers = self._request(
        url,
        self._browser_headers(),
    )

    print(
        f"Pricing page: HTTP {status}, "
        f"{content_type}, {len(body)} bytes"
    )

    text = body.decode(
        "utf-8",
        errors="replace",
    )

    # Find the Inertia data-page attribute.
    match = re.search(
        r'data-page\s*=\s*(["\'])(.*?)\1',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        raise RuntimeError(
            "Could not find Inertia data-page in /pricing HTML."
        )

    raw_page = html.unescape(match.group(2))

    try:
        page_data = json.loads(raw_page)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Could not decode Inertia page data: {e}"
        ) from e

    print("Successfully decoded Inertia page data.")

    # Show the top-level structure so we can verify
    # where Myanmar Post put the pricing data.
    if isinstance(page_data, dict):
        print(
            "Inertia page keys:",
            list(page_data.keys())
        )

        props = page_data.get("props")

        if isinstance(props, dict):
            print(
                "Inertia props keys:",
                list(props.keys())
            )

    return page_data

    def get_duration(self, country_code):
        """
        Get delivery duration information.

        Example:
            /deliver-duration/AU

        The response contains separate services:
            data.fp
            data.ems
        """
        url = (
            f"{BASE_URL}/deliver-duration/"
            f"{country_code}"
        )

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/json, "
                "text/plain, */*"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/pricing",
        }

        status, content_type, body, response_headers = self._request(
            url,
            headers,
        )

        print(
            f"Duration {country_code}: "
            f"HTTP {status}, "
            f"{content_type}, "
            f"{len(body)} bytes"
        )

        text = body.decode(
            "utf-8",
            errors="replace",
        )

        try:
            return json.loads(text)

        except json.JSONDecodeError as e:
            print(
                f"Invalid duration JSON "
                f"for {country_code}:"
            )

            print(text[:1000])

            raise RuntimeError(
                f"Invalid duration JSON for "
                f"{country_code}: {e}"
            ) from e


# ---------------------------------------------------------
# FIND COUNTRY LIST
# ---------------------------------------------------------

def find_country_list(obj):
    """
    Recursively find the list containing country records.

    Country records contain:
        alpha_2_code
    """
    if isinstance(obj, list):
        if obj and all(
            isinstance(item, dict)
            for item in obj
        ):
            if any(
                "alpha_2_code" in item
                for item in obj
            ):
                return obj

        for item in obj:
            result = find_country_list(item)

            if result:
                return result

    elif isinstance(obj, dict):
        for value in obj.values():
            result = find_country_list(value)

            if result:
                return result

    return []


# ---------------------------------------------------------
# ORDINARY LETTER PRICE
# ---------------------------------------------------------

def find_20g_letter_price(letter_rates):
    """
    Find the ordinary-letter price for
    20 g or less.

    Myanmar Post represents weight in kg.

        20 g = 0.02 kg

    If several rates are <= 20 g,
    use the highest available bracket.
    """
    if not isinstance(
        letter_rates,
        list,
    ):
        return None

    eligible = []

    for item in letter_rates:
        if not isinstance(
            item,
            dict,
        ):
            continue

        try:
            weight = float(
                item["weight"]
            )

            amount = int(
                item["amount"]
            )

        except (
            KeyError,
            ValueError,
            TypeError,
        ):
            continue

        if weight <= MAX_LETTER_WEIGHT_KG:
            eligible.append(
                (weight, amount)
            )

    if not eligible:
        return None

    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[-1][1]


# ---------------------------------------------------------
# EMS PRICE
# ---------------------------------------------------------

def find_ems_price(ems_rates):
    """
    Find the EMS price for an item weighing
    20 g or less.

    EMS pricing normally starts at a larger
    weight bracket, for example 0.5 kg.

    Therefore, for a 20 g item, use the
    smallest available EMS weight bracket.
    """
    if not isinstance(
        ems_rates,
        list,
    ):
        return None

    eligible = []

    for item in ems_rates:
        if not isinstance(
            item,
            dict,
        ):
            continue

        try:
            weight = float(
                item["weight"]
            )

            amount = int(
                item["amount"]
            )

        except (
            KeyError,
            ValueError,
            TypeError,
        ):
            continue

        # EMS bracket must cover 20 g.
        if weight >= MAX_LETTER_WEIGHT_KG:
            eligible.append(
                (weight, amount)
            )

    if not eligible:
        return None

    # Use the smallest EMS bracket that
    # covers a 20 g item.
    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[0][1]


# ---------------------------------------------------------
# COUNTRY PRICING
# ---------------------------------------------------------

def find_country_letter_price(country):
    """
    Get the ordinary-letter price from:

        country
            -> fp
                -> letter

    EMS is deliberately NOT used here.
    """
    fp = country.get(
        "fp",
        {},
    )

    if not isinstance(
        fp,
        dict,
    ):
        return None

    letter = fp.get(
        "letter",
        [],
    )

    return find_20g_letter_price(
        letter
    )


def find_country_ems_price(country):
    """
    Get the EMS price from:

        country
            -> ems

    This is completely separate from FP.
    """
    ems = country.get(
        "ems",
        [],
    )

    return find_ems_price(
        ems
    )


# ---------------------------------------------------------
# SERVICE AVAILABILITY
# ---------------------------------------------------------

def get_service_information(
    client,
    country_code,
):
    """
    Get FP and EMS availability separately.

    A service is considered available only when
    its days_en contains actual text.

    Example available:
        "between 3 and 10 days"

    Example unavailable:
        null

    This prevents EMS information from being
    incorrectly used as ordinary-letter
    information.
    """
    duration_data = client.get_duration(
        country_code
    )

    data = duration_data.get(
        "data",
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        data = {}

    fp = data.get(
        "fp",
        {},
    )

    ems = data.get(
        "ems",
        {},
    )

    if not isinstance(
        fp,
        dict,
    ):
        fp = {}

    if not isinstance(
        ems,
        dict,
    ):
        ems = {}

    fp_duration = fp.get(
        "days_en"
    )

    ems_duration = ems.get(
        "days_en"
    )

    # FP is available only when the API
    # actually provides a duration.
    fp_available = (
        isinstance(
            fp_duration,
            str,
        )
        and bool(
            fp_duration.strip()
        )
    )

    # EMS is available only when the API
    # actually provides a duration.
    ems_available = (
        isinstance(
            ems_duration,
            str,
        )
        and bool(
            ems_duration.strip()
        )
    )

    return {
        "fp_available": fp_available,
        "fp_duration": (
            fp_duration
            if fp_available
            else None
        ),
        "ems_available": ems_available,
        "ems_duration": (
            ems_duration
            if ems_available
            else None
        ),
    }


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    print(
        "Downloading Myanmar Post "
        "international pricing..."
    )

    client = MyanmarPostClient()

    data = client.get_pricing_data()

    countries = find_country_list(
        data
    )

    if not countries:
        raise RuntimeError(
            "Could not find the country list "
            "in the pricing response."
        )

    print(
        f"Found {len(countries)} countries."
    )

    output = []

    output.append(
        "Myanmar Post International "
        "Ordinary Letter / EMS Prices"
    )

    output.append(
        "Ordinary letter maximum weight: 20 g"
    )

    output.append("")

    output.append(
        "Generated: "
        + datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

    output.append("")

    # Sort countries alphabetically.
    countries_sorted = sorted(
        countries,
        key=lambda country: str(
            country.get(
                "name_en",
                "",
            )
        ).lower(),
    )

    fp_available_count = 0
    ems_available_count = 0

    for country in countries_sorted:
        if not isinstance(
            country,
            dict,
        ):
            continue

        country_code = str(
            country.get(
                "alpha_2_code",
                "",
            )
        ).upper()

        country_name = country.get(
            "name_en",
            country_code,
        )

        if not country_code:
            continue

        print(
            f"Processing {country_name} "
            f"({country_code})..."
        )

        # -------------------------------------------------
        # Get service availability first.
        # -------------------------------------------------

        try:
            service = get_service_information(
                client,
                country_code,
            )

        except Exception as e:
            print(
                f"Could not get duration "
                f"for {country_code}: {e}"
            )

            service = {
                "fp_available": False,
                "fp_duration": None,
                "ems_available": False,
                "ems_duration": None,
            }

        fp_available = service[
            "fp_available"
        ]

        fp_duration = service[
            "fp_duration"
        ]

        ems_available = service[
            "ems_available"
        ]

        ems_duration = service[
            "ems_duration"
        ]

        # -------------------------------------------------
        # Get prices.
        # -------------------------------------------------

        fp_price = find_country_letter_price(
            country
        )

        ems_price = find_country_ems_price(
            country
        )

        # -------------------------------------------------
        # Output country name.
        # -------------------------------------------------

        output.append(
            country_name
        )

        output.append(
            f"Country code: {country_code}"
        )

        # -------------------------------------------------
        # ORDINARY LETTER
        # -------------------------------------------------

        if fp_available:
            fp_available_count += 1

            if fp_price is not None:
                output.append(
                    "Ordinary letter "
                    "(20 g or less): "
                    f"{fp_price:,} Kyats"
                )

            else:
                output.append(
                    "Ordinary letter "
                    "(20 g or less): "
                    "price unavailable"
                )

            output.append(
                "Delivery duration: "
                f"{fp_duration}"
            )

        else:
            # IMPORTANT:
            # Do NOT show the FP price when
            # the service is suspended.
            output.append(
                "Ordinary letter "
                "(20 g or less): "
                "service suspended"
            )

        # -------------------------------------------------
        # EMS
        # -------------------------------------------------

        if ems_available:
            ems_available_count += 1

            if ems_price is not None:
                output.append(
                    "EMS (20 g or less): "
                    f"{ems_price:,} Kyats"
                )

            else:
                output.append(
                    "EMS (20 g or less): "
                    "price unavailable"
                )

            output.append(
                "EMS delivery duration: "
                f"{ems_duration}"
            )

        output.append("")

    # -----------------------------------------------------
    # WRITE FILE
    # -----------------------------------------------------

    result = "\n".join(
        output
    )

    with open(
        "myanmarpost_prices.txt",
        "w",
        encoding="utf-8",
    ) as file:
        file.write(result)

    # -----------------------------------------------------
    # DISPLAY RESULT
    # -----------------------------------------------------

    print("")
    print(
        "========================================"
    )

    print(result)

    print(
        "========================================"
    )

    print(
        "Ordinary-letter services available: "
        f"{fp_available_count}"
    )

    print(
        "EMS services available: "
        f"{ems_available_count}"
    )

    print(
        "Output file: myanmarpost_prices.txt"
    )


if __name__ == "__main__":
    main()
