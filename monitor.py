import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


BASE_URL = "https://myanmarpost.com.mm"

PRICING_URL = f"{BASE_URL}/pricing?tab=international"

# Ordinary letter maximum weight.
# 20 grams = 0.02 kg
MAX_LETTER_WEIGHT_KG = 0.02


def get_response(url, headers):
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


# ---------------------------------------------------------
# PRICING
# ---------------------------------------------------------

def get_pricing_data():
    """
    Download international pricing data.

    The website uses the international pricing page:
        /pricing?tab=international
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

        "X-Requested-With": "XMLHttpRequest",

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


# ---------------------------------------------------------
# DELIVERY DURATION
# ---------------------------------------------------------

def get_duration(country_code):
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

    print(
        f"Duration {country_code}: "
        f"HTTP {status}, "
        f"{content_type}, "
        f"{len(body)} bytes"
    )

    text = body.decode(
        "utf-8",
        errors="replace"
    )

    try:

        return json.loads(text)

    except json.JSONDecodeError as e:

        print(
            f"Invalid duration JSON "
            f"for {country_code}:"
        )

        print(text[:500])

        raise RuntimeError(
            f"Invalid duration JSON for "
            f"{country_code}: {e}"
        ) from e


# ---------------------------------------------------------
# FIND COUNTRY LIST
# ---------------------------------------------------------

def find_country_list(obj):
    """
    Recursively find the list containing
    country records.

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

    Example:

        0.5 kg -> 140,000 Kyats
        1 kg   -> 160,000 Kyats

    A 20 g EMS item falls into the first
    available EMS bracket.
    """

    if not isinstance(
        ems_rates,
        list
    ):
        return None

    eligible = []

    for item in ems_rates:

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
        []
    )

    return find_ems_price(
        ems
    )


# ---------------------------------------------------------
# SERVICE AVAILABILITY
# ---------------------------------------------------------

def get_service_information(
    country_code
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

    duration_data = get_duration(
        country_code
    )

    data = duration_data.get(
        "data",
        {}
    )

    if not isinstance(
        data,
        dict
    ):
        data = {}

    fp = data.get(
        "fp",
        {}
    )

    ems = data.get(
        "ems",
        {}
    )

    if not isinstance(
        fp,
        dict
    ):
        fp = {}

    if not isinstance(
        ems,
        dict
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
            str
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
            str
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
                ""
            )
        ).lower()
    )

    fp_available_count = 0
    ems_available_count = 0

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

        # -------------------------------------------------
        # Get service availability first.
        # -------------------------------------------------

        try:

            service = get_service_information(
                country_code
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
        encoding="utf-8"
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
