import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE_URL = "https://myanmarpost.com.mm"

PRICING_URL = f"{BASE_URL}/pricing?tab=international"

# Ordinary letters only.
# 0.02 kg = 20 grams.
MAX_WEIGHT_KG = 0.02

# Countries you want to monitor.
COUNTRIES = [
    "AU",
    # Add more country codes here if wanted:
    # "AT",
    # "US",
    # "GB",
    # "JP",
]


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
        print(body[:1000].decode("utf-8", errors="replace"))
        raise


def get_pricing_data():
    """
    Request the Myanmar Post pricing endpoint in the same
    general way as the browser's Inertia request.
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
        "X-Inertia-Version": "34e9d596c2ba005758a128ed0067da87",
        "Referer": f"{BASE_URL}/pricing",
    }

    status, content_type, body = get_response(PRICING_URL, headers)

    print(f"Pricing response: HTTP {status}")
    print(f"Content-Type: {content_type}")
    print(f"Response size: {len(body)} bytes")

    text = body.decode("utf-8", errors="replace")

    # Show the beginning if the response isn't JSON.
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
    url = f"{BASE_URL}/deliver-duration/{country_code}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/pricing",
    }

    status, content_type, body = get_response(url, headers)

    text = body.decode("utf-8", errors="replace")

    print(
        f"Duration {country_code}: "
        f"HTTP {status}, {content_type}, {len(body)} bytes"
    )

    return json.loads(text)


def find_country_list(obj):
    """
    Recursively find the list containing country records.
    """

    if isinstance(obj, list):

        if obj and isinstance(obj[0], dict):
            if any(
                "alpha_2_code" in item
                for item in obj
                if isinstance(item, dict)
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
    Find the ordinary-letter rate for 20 g or less.

    Myanmar Post represents 20 g as:
        weight = 0.02
    """

    eligible = []

    for item in letter_rates:

        try:
            weight = float(item["weight"])
            amount = int(item["amount"])
        except (KeyError, ValueError, TypeError):
            continue

        if weight <= MAX_WEIGHT_KG:
            eligible.append((weight, amount))

    if not eligible:
        return None

    # Select the highest available weight not exceeding 20 g.
    eligible.sort(key=lambda x: x[0])

    return eligible[-1][1]


def find_country_pricing(country):
    """
    Locate the ordinary-letter pricing data.

    The HAR data you provided shows this structure:

        "fp": {
            "letter": [
                {"amount":"11000","weight":0.02},
                ...
            ]
        }
    """

    fp = country.get("fp", {})

    if not isinstance(fp, dict):
        return None

    letter = fp.get("letter", [])

    if not isinstance(letter, list):
        return None

    return find_20g_price(letter)


def main():

    print("Downloading Myanmar Post international pricing...")

    data = get_pricing_data()

    countries = find_country_list(data)

    if not countries:
        raise RuntimeError(
            "Could not find the country list in the pricing response."
        )

    print(f"Found {len(countries)} countries.")

    output = []

    output.append(
        "Myanmar Post International Ordinary Letter Prices"
    )
    output.append("Maximum weight: 20 g")
    output.append("")
    output.append(
        "Generated: "
        + datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )
    output.append("")

    for country_code in COUNTRIES:

        country = None

        for item in countries:

            if not isinstance(item, dict):
                continue

            code = str(
                item.get("alpha_2_code", "")
            ).upper()

            if code == country_code:
                country = item
                break

        if not country:

            output.append(
                f"{country_code}: country data not found"
            )
            output.append("")
            continue

        name = country.get(
            "name_en",
            country_code
        )

        price = find_country_pricing(country)

        try:

            duration_data = get_duration(country_code)

            duration = (
                duration_data
                .get("data", {})
                .get("fp", {})
            )

            duration_text = duration.get(
                "days_en",
                "delivery duration unavailable"
            )

        except Exception as e:

            print(
                f"Could not get duration for {country_code}: {e}"
            )

            duration_text = "delivery duration unavailable"

        output.append(name)
        output.append(
            f"Country code: {country_code}"
        )

        if price is None:

            output.append(
                "Ordinary letter (20 g or less): "
                "price unavailable"
            )

        else:

            output.append(
                "Ordinary letter (20 g or less): "
                f"{price:,} Kyats"
            )

        output.append(
            f"Delivery duration: {duration_text}"
        )

        output.append("")

    result = "\n".join(output)

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


if __name__ == "__main__":
    main()
