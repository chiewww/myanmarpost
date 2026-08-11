import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


BASE_URL = "https://myanmarpost.com.mm"

PRICING_URL = (
    f"{BASE_URL}/pricing?tab=international"
)

# Ordinary letters only.
#
# 0.02 kg = 20 grams.
MAX_WEIGHT_KG = 0.02


def get_response(url, headers):
    """
    Send an HTTP request and return:
        status, content_type, body
    """

    request = urllib.request.Request(
        url,
        headers=headers
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=120
        ) as response:

            body = response.read()

            content_type = response.headers.get(
                "Content-Type",
                ""
            )

            return (
                response.status,
                content_type,
                body
            )

    except urllib.error.HTTPError as e:

        body = e.read()

        print(
            f"HTTP error {e.code} for {url}"
        )

        print(
            body[:1000].decode(
                "utf-8",
                errors="replace"
            )
        )

        raise


def get_pricing_data():
    """
    Download international pricing data
    from Myanmar Post.
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "text/html, "
            "application/xhtml+xml"
        ),

        "X-Inertia": "true",

        "X-Requested-With":
            "XMLHttpRequest",

        "X-Inertia-Version":
            "34e9d596c2ba005758a128ed0067da87",

        "Referer":
            f"{BASE_URL}/pricing",
    }

    status, content_type, body = get_response(
        PRICING_URL,
        headers
    )

    print(
        f"Pricing response: HTTP {status}"
    )

    print(
        f"Content-Type: {content_type}"
    )

    print(
        f"Response size: {len(body)} bytes"
    )

    text = body.decode(
        "utf-8",
        errors="replace"
    )

    stripped = text.lstrip()

    if (
        not stripped.startswith("{")
        and not stripped.startswith("[")
    ):

        print(
            "Pricing response is not JSON."
        )

        print(
            "First 500 characters:"
        )

        print(text[:500])

        raise RuntimeError(
            "Myanmar Post pricing endpoint "
            "did not return JSON."
        )

    try:

        return json.loads(text)

    except json.JSONDecodeError as e:

        print(
            "Could not decode pricing response "
            "as JSON."
        )

        print(text[:1000])

        raise RuntimeError(
            f"Invalid JSON returned by "
            f"Myanmar Post: {e}"
        ) from e


def get_duration(country_code):
    """
    Get delivery-duration information
    for a country.

    IMPORTANT:
    The fp section is ordinary letter.
    The ems section is EMS.

    We only use fp.
    """

    url = (
        f"{BASE_URL}/deliver-duration/"
        f"{country_code}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "application/json, "
            "text/plain, */*"
        ),

        "X-Requested-With":
            "XMLHttpRequest",

        "Referer":
            f"{BASE_URL}/pricing",
    }

    status, content_type, body = get_response(
        url,
        headers
    )

    text = body.decode(
        "utf-8",
        errors="replace"
    )

    print(
        f"Duration {country_code}: "
        f"HTTP {status}, "
        f"{content_type}, "
        f"{len(body)} bytes"
    )

    try:

        return json.loads(text)

    except json.JSONDecodeError as e:

        print(
            f"Invalid duration JSON for "
            f"{country_code}:"
        )

        print(text[:500])

        raise RuntimeError(
            f"Invalid duration JSON for "
            f"{country_code}: {e}"
        ) from e


def get_fp_duration(country_code):
    """
    Return the ordinary-letter delivery duration.

    IMPORTANT:
        fp = ordinary letter
        ems = EMS

    We NEVER use ems here.

    A valid ordinary-letter service must have
    a non-empty fp.days_en value.

    Examples of valid values:

        "between 3 and 10 days"
        "between 21 and 30 days"
        "between 30 and 45 days"

    Examples of unavailable values:

        null
        ""
        "-"
    """

    try:

        duration_data = get_duration(
            country_code
        )

    except Exception as e:

        print(
            f"Could not retrieve duration "
            f"for {country_code}: {e}"
        )

        return None

    data = duration_data.get(
        "data",
        {}
    )

    if not isinstance(
        data,
        dict
    ):
        return None

    # ------------------------------------------------
    # IMPORTANT:
    # Use ONLY fp.
    #
    # Do NOT fall back to ems.
    # ------------------------------------------------

    fp = data.get(
        "fp",
        {}
    )

    if not isinstance(
        fp,
        dict
    ):
        return None

    duration = fp.get(
        "days_en"
    )

    # null
    if duration is None:
        return None

    duration = str(
        duration
    ).strip()

    # Empty string
    if duration == "":
        return None

    # Explicit unavailable marker
    if duration == "-":
        return None

    return duration


def find_country_list(obj):
    """
    Recursively search the pricing JSON
    for the list containing country records.
    """

    if isinstance(
        obj,
        list
    ):

        if obj and all(
            isinstance(
                item,
                dict
            )
            for item in obj
        ):

            if any(
                "alpha_2_code" in item
                for item in obj
            ):

                return obj

        for item in obj:

            result = find_country_list(
                item
            )

            if result:
                return result

    elif isinstance(
        obj,
        dict
    ):

        for value in obj.values():

            result = find_country_list(
                value
            )

            if result:
                return result

    return []


def find_20g_price(letter_rates):
    """
    Find the ordinary-letter price for
    20 g or less.

    Myanmar Post uses kilograms.

        20 g = 0.02 kg

    If several rates are <= 20 g,
    use the highest available weight
    not exceeding 20 g.
    """

    if not isinstance(
        letter_rates,
        list
    ):
        return None

    eligible = []

    for item in letter_rates:

        if not isinstance(
            item,
            dict
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
            TypeError
        ):
            continue

        if weight <= MAX_WEIGHT_KG:

            eligible.append(
                (
                    weight,
                    amount
                )
            )

    if not eligible:
        return None

    # Highest available weight <= 20 g.
    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[-1][1]


def find_country_pricing(country):
    """
    Get ordinary-letter pricing.

    ONLY:
        fp -> letter

    We never use EMS pricing.
    """

    fp = country.get(
        "fp",
        {}
    )

    if not isinstance(
        fp,
        dict
    ):
        return None

    letter = fp.get(
        "letter",
        []
    )

    return find_20g_price(
        letter
    )


def main():

    print(
        "Downloading Myanmar Post "
        "international pricing..."
    )

    data = get_pricing_data()

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
        "Ordinary Letter Prices"
    )

    output.append(
        "Maximum weight: 20 g"
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

    # Sort alphabetically.
    countries_sorted = sorted(
        countries,
        key=lambda country: str(
            country.get(
                "name_en",
                ""
            )
        ).lower()
        if isinstance(
            country,
            dict
        )
        else ""
    )

    available_count = 0
    unavailable_count = 0

    for country in countries_sorted:

        if not isinstance(
            country,
            dict
        ):
            continue

        country_code = str(
            country.get(
                "alpha_2_code",
                ""
            )
        ).upper()

        country_name = country.get(
            "name_en",
            country_code
        )

        if not country_code:
            continue

        print(
            f"Processing {country_name} "
            f"({country_code})..."
        )

        # ------------------------------------------------
        # STEP 1
        #
        # Check ordinary-letter duration FIRST.
        # ------------------------------------------------

        duration = get_fp_duration(
            country_code
        )

        # ------------------------------------------------
        # STEP 2
        #
        # If fp.days_en is missing/null/"-",
        # ordinary-letter service is unavailable.
        #
        # IMPORTANT:
        # We do NOT show the pricing data.
        # We also do NOT use EMS duration.
        # ------------------------------------------------

        if duration is None:

            output.append(
                country_name
            )

            output.append(
                f"Country code: "
                f"{country_code}"
            )

            output.append(
                "Ordinary letter "
                "(20 g or less): "
                "service unavailable"
            )

            output.append(
                "Delivery duration: -"
            )

            output.append("")

            unavailable_count += 1

            print(
                f"  {country_name}: "
                f"ordinary-letter service "
                f"unavailable"
            )

            continue

        # ------------------------------------------------
        # STEP 3
        #
        # Only now look at the price.
        # ------------------------------------------------

        price = find_country_pricing(
            country
        )

        output.append(
            country_name
        )

        output.append(
            f"Country code: "
            f"{country_code}"
        )

        if price is None:

            output.append(
                "Ordinary letter "
                "(20 g or less): "
                "price unavailable"
            )

        else:

            output.append(
                "Ordinary letter "
                "(20 g or less): "
                f"{price:,} Kyats"
            )

            available_count += 1

        output.append(
            "Delivery duration: "
            f"{duration}"
        )

        output.append("")

    result = "\n".join(
        output
    )

    with open(
        "myanmarpost_prices.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(result)

    print("")
    print(
        "========================================"
    )

    print(result)

    print(
        "========================================"
    )

    print(
        "Countries with available "
        "ordinary-letter service: "
        f"{available_count}"
    )

    print(
        "Countries with unavailable "
        "ordinary-letter service: "
        f"{unavailable_count}"
    )


if __name__ == "__main__":
    main()
