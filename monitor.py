import json
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://myanmarpost.com.mm"

PRICING_URL = f"{BASE_URL}/pricing?tab=international"

# Countries to monitor.
# Add/remove country codes as needed.
COUNTRIES = [
    "AU",
    # "AT",
    # "US",
    # "GB",
    # "JP",
]

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get_duration(country_code):
    url = f"{BASE_URL}/deliver-duration/{country_code}"
    result = get_json(url)
    return result.get("data", {}).get("fp", {})


def find_20g_price(letter_rates):
    """
    Find the ordinary-letter price for 20g or less.

    The website uses weights such as:
      0.02 = 20g
      0.1  = 100g
      0.25 = 250g

    We therefore select the highest available letter rate
    whose weight is <= 0.02 kg.
    """

    eligible = []

    for item in letter_rates:
        try:
            weight = float(item["weight"])
            amount = int(item["amount"])
        except (KeyError, ValueError, TypeError):
            continue

        if weight <= 0.02:
            eligible.append((weight, amount))

    if not eligible:
        return None

    eligible.sort(key=lambda x: x[0])
    return eligible[-1][1]


def main():
    data = get_json(PRICING_URL)

    # The exact nesting can vary depending on the API response.
    countries = data.get("props", {}).get("pricing", {}).get("countries", [])

    # Fallback: recursively search for country-like records.
    if not countries:
        countries = find_country_list(data)

    output = []

    output.append("Myanmar Post International Ordinary Letter Prices")
    output.append("Maximum weight: 20 g")
    output.append("")
    output.append(
        "Generated: "
        + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )
    output.append("")

    for country_code in COUNTRIES:
        country = None

        for item in countries:
            if str(item.get("alpha_2_code", "")).upper() == country_code:
                country = item
                break

        if not country:
            output.append(f"{country_code}: country data not found")
            output.append("")
            continue

        name = country.get("name_en", country_code)

        fp = country.get("fp", {})
        letter_rates = fp.get("letter", [])

        price = find_20g_price(letter_rates)

        try:
            duration = get_duration(country_code)
            duration_text = duration.get(
                "days_en",
                "delivery duration unavailable"
            )
        except Exception as e:
            duration_text = f"delivery duration unavailable ({e})"

        output.append(name)
        output.append(f"Country code: {country_code}")
        output.append(
            f"Ordinary letter (20 g or less): "
            + (f"{price:,} Kyats" if price is not None else "price unavailable")
        )
        output.append(f"Delivery duration: {duration_text}")
        output.append("")

    with open("myanmarpost_prices.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))

    print("\n".join(output))


def find_country_list(obj):
    """
    Recursively find a list containing country records.
    This makes the script more tolerant of changes to the
    JSON structure returned by Myanmar Post.
    """

    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            if any(
                "alpha_2_code" in x or "country_code" in x
                for x in obj
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


if __name__ == "__main__":
    main()
