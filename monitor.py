import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE_URL = "https://myanmarpost.com.mm"

PRICING_URL = f"{BASE_URL}/pricing?tab=international"

# Ordinary letters only.
# 0.02 kg = 20 grams.
MAX_WEIGHT_KG = 0.02


def get_response(url, headers):
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            return response.status, content_type, body

    except urllib.error.HTTPError as e:
        body = e.read()

        print(f"HTTP error {e.code} for {url}")
        print(
            body[:1000].decode(
                "utf-8",
                errors="replace"
            )
        )

        raise


def get_pricing_data():
    """
    Download the international pricing data from Myanmar Post.

    This is the same endpoint used by the pricing page:
        /pricing?tab=international
    """

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "Accept": "text/html, application/xhtml+xml",

        "X-Inertia": "true",

        "X-Requested-With": "XMLHttpRequest",

        "X-Inertia-Version":
            "34e9d596c2ba005758a128ed0067da87",

        "Referer": f"{BASE_URL}/pricing",
    }

    status, content_type, body = get_response(
        PRICING_URL,
        headers
    )

    print(f"Pricing response: HTTP {status}")
    print(f"Content-Type: {content_type}")
    print(f"Response size: {len(body)} bytes")

    text = body.decode(
        "utf-8",
        errors="replace"
    )

    stripped = text.lstrip()

    if not stripped.startswith("{") and not stripped.startswith("["):

        print("Pricing response is not JSON.")

        print("First 500 characters:")
        print(text[:500])

        raise RuntimeError(
            "Myanmar Post pricing endpoint did not return JSON."
        )

    try:

        return json.loads(text)

    except json.JSONDecodeError as e:

        print("Could not decode pricing response as JSON.")

        print(text[:1000])

        raise RuntimeError(
            f"Invalid JSON returned by Myanmar Post: {e}"
        ) from e


def get_duration(country_code):
    """
    Get the ordinary-letter delivery duration for a country.

    Example:
        /deliver-duration/AU
    """

    url = f"{BASE_URL}/deliver-duration/{country_code}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "application/json, text/plain, */*"
        ),

        "X-Requested-With": "XMLHttpRequest",

        "Referer": f"{BASE_URL}/pricing",
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
            f"Invalid duration JSON for {country_code}:"
        )

        print(text[:500])

        raise RuntimeError(
            f"Invalid duration JSON for {country_code}: {e}"
        ) from e


def find_country_list(obj):
    """
    Recursively search the pricing JSON for the list
    containing country records.

    A country record contains alpha_2_code.
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


def find_20g_price(letter_rates):
    """
    Find the ordinary-letter price for 20 g or less.

    Myanmar Post uses kilograms in the JSON.

    Therefore:
        20 g = 0.02 kg

    If multiple rates are <= 20 g, use the highest
    available weight not exceeding 20 g.
    """

    if not isinstance(letter_rates, list):
        return None

    eligible = []

    for item in letter_rates:

        if not isinstance(item, dict):
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
                (weight, amount)
            )

    if not eligible:
        return None

    # Select the highest available rate
    # that is still 20 g or less.
    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[-1][1]


def find_country_pricing(country):
    """
    Get the ordinary-letter price from:

        country
          -> fp
              -> letter

    We deliberately DO NOT use:
        EMS
        parcel
        package
        other services
    """

    fp = country.get(
        "fp",
        {}
    )

    if not isinstance(fp, dict):
        return None

    letter = fp.get(
        "letter",
        []
    )

    return find_20g_price(
        letter
    )


def get_duration_text(country_code):
    """
    Return the ordinary-letter delivery duration.

    The API response has this structure:

    {
        "data": {
            "alpha_2_code": "AU",
            "country": "Australia",
            "fp": {
                "dispatch": 3,
                "final": 10,
                "days_en": "between 3 and 10 days"
            },
            "ems": {
                ...
            }
        }
    }

    We use ONLY data.fp.days_en.
    """

    try:

        duration_data = get_duration(
            country_code
        )

        data = duration_data.get(
            "data",
            {}
        )

        fp = data.get(
            "fp",
            {}
        )

        duration_text = fp.get(
            "days_en"
        )

        if duration_text:

            return duration_text

        return "delivery duration unavailable"

    except Exception as e:

        print(
            f"Could not get duration for "
            f"{country_code}: {e}"
        )

        return "delivery duration unavailable"


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

    # Sort countries alphabetically.
    countries_sorted = sorted(
        countries,
        key=lambda country: str(
            country.get(
                "name_en",
                ""
            )
        ).lower()
    )

    successful = 0

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

        # Ordinary letter price only.
        price = find_country_pricing(
            country
        )

        # Ordinary letter delivery duration only.
        duration_text = get_duration_text(
            country_code
        )

        output.append(
            country_name
        )

        output.append(
            f"Country code: {country_code}"
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

            successful += 1

        output.append(
            "Delivery duration: "
            f"{duration_text}"
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
    print("========================================")
    print(result)
    print("========================================")

    print(
        f"Countries with a 20 g "
        f"ordinary-letter price: {successful}"
    )


if __name__ == "__main__":
    main()
