import time
from pathlib import Path

import requests


BASE_URL = "https://myanmarpost.com.mm"
PRICING_URL = f"{BASE_URL}/pricing?tab=international"

OUTPUT_FILE = "myanmarpost_prices.txt"

# 20 grams = 0.02 kg
MAX_WEIGHT_KG = 0.02

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def get_pricing_data():
    """Download the international pricing JSON from Myanmar Post."""

    headers = {
        **HEADERS,
        "Accept": "text/html, application/xhtml+xml",
        "X-Inertia": "true",
        "X-Inertia-Version": "34e9d596c2ba005758a128ed0067da87",
    }

    response = requests.get(
        PRICING_URL,
        headers=headers,
        timeout=60,
    )

    response.raise_for_status()
    return response.json()


def find_countries(data):
    """
    Find the country list inside the Myanmar Post pricing response.
    """

    if isinstance(data, list):

        if data and all(isinstance(item, dict) for item in data):

            country_count = sum(
                1
                for item in data
                if "alpha_2_code" in item
                and ("name_en" in item or "country" in item)
            )

            if country_count > 0:
                return data

        for item in data:
            result = find_countries(item)

            if result:
                return result

    elif isinstance(data, dict):

        # Check likely locations first.
        for key in (
            "countries",
            "country",
            "data",
            "pricing",
            "international",
        ):

            if key in data:

                result = find_countries(data[key])

                if result:
                    return result

        # Search the rest of the object.
        for value in data.values():

            result = find_countries(value)

            if result:
                return result

    return []


def get_letter_price(country):
    """
    Get the ordinary-letter price for 20 g or less.

    EMS is deliberately ignored.
    """

    fp = country.get("fp")

    if not isinstance(fp, dict):
        return None

    letter_prices = fp.get("letter")

    if not isinstance(letter_prices, list):
        return None

    # Prefer an exact 20 g / 0.02 kg price.
    for item in letter_prices:

        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue

        if abs(weight - MAX_WEIGHT_KG) < 0.000001:
            return item.get("amount")

    # If 0.02 kg is not present, use the smallest
    # available weight that is greater than 20 g.
    candidates = []

    for item in letter_prices:

        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue

        if weight >= MAX_WEIGHT_KG:
            candidates.append(
                (
                    weight,
                    item.get("amount"),
                )
            )

    if candidates:

        candidates.sort(key=lambda x: x[0])

        return candidates[0][1]

    return None


def format_price(amount):
    """Convert 11000 into '11,000 Kyats'."""

    if amount is None:
        return "N/A"

    try:
        return f"{int(float(amount)):,} Kyats"

    except (TypeError, ValueError):
        return f"{amount} Kyats"


def get_delivery_duration(country_code):
    """
    Get ordinary-letter delivery duration.

    The 'fp' section is used.
    EMS is ignored.
    """

    url = f"{BASE_URL}/deliver-duration/{country_code}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return data.get("data", {}).get("fp", {})


def main():

    print()
    print("Myanmar Post international ordinary-letter monitor")
    print("=" * 55)
    print("Maximum weight: 20 g")
    print()

    print("Downloading pricing information...")

    pricing_data = get_pricing_data()

    countries = find_countries(pricing_data)

    if not countries:

        raise RuntimeError(
            "Could not find the country list in the pricing response."
        )

    print(f"Found {len(countries)} countries.")
    print()

    results = []

    for number, country in enumerate(
        countries,
        start=1,
    ):

        country_name = (
            country.get("name_en")
            or country.get("country")
            or "Unknown"
        )

        country_code = country.get("alpha_2_code")

        if not country_code:
            continue

        print(
            f"[{number}/{len(countries)}] "
            f"{country_name} ({country_code})"
        )

        # -------------------------------------------------
        # Ordinary letter price
        # -------------------------------------------------

        amount = get_letter_price(country)

        price = format_price(amount)

        # -------------------------------------------------
        # Ordinary letter delivery duration
        # -------------------------------------------------

        try:

            duration = get_delivery_duration(
                country_code
            )

            days = duration.get(
                "days_en",
                "N/A",
            )

        except requests.RequestException as error:

            print(
                f"    Warning: could not get delivery duration: "
                f"{error}"
            )

            days = "N/A"

        results.append(
            {
                "country": country_name,
                "code": country_code,
                "price": price,
                "delivery": days,
            }
        )

        # Small delay so we do not hammer the server.
        time.sleep(0.2)

    # Sort alphabetically.
    results.sort(
        key=lambda item: item["country"].lower()
    )

    # -----------------------------------------------------
    # Create text file
    # -----------------------------------------------------

    lines = []

    lines.append(
        "Myanmar Post - International Ordinary Letter Prices"
    )

    lines.append(
        "Maximum weight: 20 grams"
    )

    lines.append(
        "Service: Ordinary Letter (FP)"
    )

    lines.append(
        "=" * 80
    )

    lines.append("")

    for item in results:

        lines.append(
            f"{item['country']} ({item['code']}) | "
            f"{item['price']} | "
            f"Delivery: {item['delivery']}"
        )

    lines.append("")

    lines.append(
        f"Total countries: {len(results)}"
    )

    Path(OUTPUT_FILE).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("=" * 55)
    print("Finished!")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 55)


if __name__ == "__main__":
    main()
