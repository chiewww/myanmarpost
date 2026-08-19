import html
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.cookiejar import CookieJar


BASE_URL = "https://myanmarpost.com.mm"
PRICING_URL = f"{BASE_URL}/pricing"

# Ordinary letter maximum weight.
# 20 grams = 0.02 kg
MAX_LETTER_WEIGHT_KG = 0.02

# HTTP settings
REQUEST_TIMEOUT = 60
MAX_REQUEST_ATTEMPTS = 3
RETRY_DELAYS = (2, 5, 10)

# Number of countries to query at the same time.
# 8 is deliberately conservative for the Myanmar Post server.
MAX_WORKERS = 8

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)


# =========================================================
# MYANMAR POST CLIENT
# =========================================================

class MyanmarPostClient:
    """
    HTTP client for Myanmar Post.

    The normal /pricing page contains the Inertia page
    data used to obtain the international country pricing.

    Country delivery durations are retrieved separately.

    Requests include retries for:
        - SSL errors
        - connection errors
        - timeouts
        - HTTP 500
        - HTTP 502
        - HTTP 503
        - HTTP 504
    """

    def __init__(self):
        self.cookie_jar = CookieJar()

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(
                self.cookie_jar
            )
        )

        self.inertia_version = None

    def _request(self, url, headers=None):
        """
        Perform a GET request with retries.
        """

        last_error = None

        for attempt in range(
            1,
            MAX_REQUEST_ATTEMPTS + 1,
        ):
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

                print(
                    f"HTTP error {e.code} for {url}"
                )

                if body:
                    print(
                        f"Response body length: "
                        f"{len(body)} bytes"
                    )

                # Retry temporary server errors.
                if (
                    e.code in (
                        500,
                        502,
                        503,
                        504,
                    )
                    and attempt
                    < MAX_REQUEST_ATTEMPTS
                ):
                    delay = RETRY_DELAYS[
                        min(
                            attempt - 1,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

                    print(
                        f"Temporary HTTP {e.code}. "
                        f"Retrying in {delay} seconds..."
                    )

                    time.sleep(delay)
                    continue

                raise

            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
            ) as e:

                last_error = e

                print(
                    f"Connection/SSL error "
                    f"for {url} "
                    f"(attempt "
                    f"{attempt}/"
                    f"{MAX_REQUEST_ATTEMPTS}): "
                    f"{repr(e)}"
                )

                if attempt < MAX_REQUEST_ATTEMPTS:
                    delay = RETRY_DELAYS[
                        min(
                            attempt - 1,
                            len(RETRY_DELAYS) - 1,
                        )
                    ]

                    time.sleep(delay)
                    continue

                raise

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            f"Request failed: {url}"
        )

    def _browser_headers(self, referer=None):
        """
        Browser-style request headers.
        """

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
        Extract the current Inertia version from HTML.
        """

        text = body.decode(
            "utf-8",
            errors="replace",
        )

        match = re.search(
            r'data-page\s*=\s*(["\'])(.*?)\1',
            text,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )

        if match:
            raw_page = html.unescape(
                match.group(2)
            )

            try:
                page_data = json.loads(
                    raw_page
                )

                version = page_data.get(
                    "version"
                )

                if (
                    isinstance(
                        version,
                        str,
                    )
                    and version.strip()
                ):
                    return version.strip()

            except json.JSONDecodeError:
                pass

            version_match = re.search(
                r'"version"\s*:\s*"([^"]+)"',
                raw_page,
                flags=re.IGNORECASE,
            )

            if version_match:
                return (
                    version_match.group(1)
                    .strip()
                )

        decoded_text = html.unescape(
            text
        )

        version_match = re.search(
            r'"version"\s*:\s*"([^"]+)"',
            decoded_text,
            flags=re.IGNORECASE,
        )

        if version_match:
            return (
                version_match.group(1)
                .strip()
            )

        return None

    def _extract_inertia_page(self, body):
        """
        Extract the Inertia data-page JSON.
        """

        text = body.decode(
            "utf-8",
            errors="replace",
        )

        match = re.search(
            r'data-page\s*=\s*(["\'])(.*?)\1',
            text,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )

        if not match:
            return None

        raw_page = html.unescape(
            match.group(2)
        )

        try:
            return json.loads(
                raw_page
            )

        except json.JSONDecodeError:
            return None

    def get_pricing_data(self):
        """
        Download and decode the normal pricing page.
        """

        print(
            "Loading Myanmar Post "
            "pricing page..."
        )

        (
            status,
            content_type,
            body,
            response_headers,
        ) = self._request(
            PRICING_URL,
            self._browser_headers(),
        )

        print(
            f"Pricing page: HTTP {status}, "
            f"{content_type}, "
            f"{len(body)} bytes"
        )

        version = (
            self._extract_inertia_version(
                body
            )
        )

        if version:
            self.inertia_version = version

            print(
                "Detected current Inertia "
                f"version: {version}"
            )

        page_data = (
            self._extract_inertia_page(
                body
            )
        )

        if page_data is None:
            raise RuntimeError(
                "Could not find or decode "
                "the Inertia data-page "
                "payload in /pricing HTML."
            )

        print(
            "Successfully decoded "
            "Inertia page data."
        )

        return page_data

    def get_duration(self, country_code):
        """
        Get delivery duration for one country.
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
            "X-Requested-With": (
                "XMLHttpRequest"
            ),
            "Referer": (
                f"{BASE_URL}/pricing"
            ),
        }

        (
            status,
            content_type,
            body,
            response_headers,
        ) = self._request(
            url,
            headers,
        )

        text = body.decode(
            "utf-8",
            errors="replace",
        )

        try:
            return json.loads(
                text
            )

        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid duration JSON "
                f"for {country_code}: {e}"
            ) from e


# =========================================================
# FIND COUNTRY LIST
# =========================================================

def find_country_list(obj):
    """
    Recursively find the list containing country records.

    Country records contain:
        alpha_2_code
    """

    if isinstance(
        obj,
        list,
    ):

        if obj and all(
            isinstance(
                item,
                dict,
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
        dict,
    ):

        for value in obj.values():
            result = find_country_list(
                value
            )

            if result:
                return result

    return []


# =========================================================
# ORDINARY LETTER PRICE
# =========================================================

def find_20g_letter_price(letter_rates):
    """
    Find the ordinary-letter price for
    20 g or less.
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

        if (
            weight
            <= MAX_LETTER_WEIGHT_KG
        ):
            eligible.append(
                (
                    weight,
                    amount,
                )
            )

    if not eligible:
        return None

    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[-1][1]


# =========================================================
# EMS PRICE
# =========================================================

def find_ems_price(ems_rates):
    """
    Find the smallest EMS price bracket
    that covers a 20 g item.
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

        if (
            weight
            >= MAX_LETTER_WEIGHT_KG
        ):
            eligible.append(
                (
                    weight,
                    amount,
                )
            )

    if not eligible:
        return None

    eligible.sort(
        key=lambda x: x[0]
    )

    return eligible[0][1]


# =========================================================
# COUNTRY PRICING
# =========================================================

def find_country_letter_price(country):
    """
    Get ordinary-letter price from:

        country
            -> fp
                -> letter
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
    Get EMS price from:

        country
            -> ems
    """

    ems = country.get(
        "ems",
        [],
    )

    return find_ems_price(
        ems
    )


# =========================================================
# SERVICE AVAILABILITY
# =========================================================

def parse_service_information(
    duration_data,
):
    """
    Parse FP and EMS service availability.
    """

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

    fp_available = (
        isinstance(
            fp_duration,
            str,
        )
        and bool(
            fp_duration.strip()
        )
    )

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


# =========================================================
# GET ONE COUNTRY'S SERVICE INFORMATION
# =========================================================

def fetch_country_service(
    client,
    country_code,
):
    """
    Worker function used by the thread pool.

    Returns:
        country_code,
        service_information,
        error
    """

    try:
        duration_data = (
            client.get_duration(
                country_code
            )
        )

        service = (
            parse_service_information(
                duration_data
            )
        )

        return (
            country_code,
            service,
            None,
        )

    except Exception as e:

        return (
            country_code,
            {
                "fp_available": False,
                "fp_duration": None,
                "ems_available": False,
                "ems_duration": None,
            },
            e,
        )


# =========================================================
# MAIN
# =========================================================

def main():
    start_time = time.time()

    print(
        "Downloading Myanmar Post "
        "international pricing..."
    )

    client = MyanmarPostClient()

    # -----------------------------------------------------
    # Download pricing.
    # -----------------------------------------------------

    data = client.get_pricing_data()

    countries = find_country_list(
        data
    )

    if not countries:
        raise RuntimeError(
            "Could not find the country "
            "list in the pricing response."
        )

    print(
        f"Found {len(countries)} countries."
    )

    # -----------------------------------------------------
    # Sort countries.
    # -----------------------------------------------------

    countries_sorted = sorted(
        countries,
        key=lambda country: str(
            country.get(
                "name_en",
                "",
            )
        ).lower(),
    )

    # -----------------------------------------------------
    # Fetch all delivery durations in parallel.
    # -----------------------------------------------------

    print(
        ""
    )

    print(
        f"Fetching delivery durations "
        f"using {MAX_WORKERS} workers..."
    )

    service_results = {}

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {}

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

            if not country_code:
                continue

            future = executor.submit(
                fetch_country_service,
                client,
                country_code,
            )

            futures[future] = (
                country_code
            )

        completed = 0
        total = len(futures)

        for future in as_completed(
            futures
        ):

            country_code = futures[
                future
            ]

            (
                returned_code,
                service,
                error,
            ) = future.result()

            service_results[
                returned_code
            ] = service

            completed += 1

            if error is not None:
                print(
                    f"[{completed}/{total}] "
                    f"{country_code}: "
                    f"duration unavailable "
                    f"({error})"
                )

            else:
                print(
                    f"[{completed}/{total}] "
                    f"{country_code}: OK"
                )

    # -----------------------------------------------------
    # Build output.
    # -----------------------------------------------------

    output = []

    output.append(
        "Myanmar Post International "
        "Ordinary Letter / EMS Prices"
    )

    output.append(
        "Ordinary letter maximum "
        "weight: 20 g"
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

    fp_available_count = 0
    ems_available_count = 0

    # -----------------------------------------------------
    # Process countries.
    # -----------------------------------------------------

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
        # Service information.
        # -------------------------------------------------

        service = service_results.get(
            country_code,
            {
                "fp_available": False,
                "fp_duration": None,
                "ems_available": False,
                "ems_duration": None,
            },
        )

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
        # Prices.
        # -------------------------------------------------

        fp_price = (
            find_country_letter_price(
                country
            )
        )

        ems_price = (
            find_country_ems_price(
                country
            )
        )

        # -------------------------------------------------
        # Country.
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
    # WRITE OUTPUT FILE
    # -----------------------------------------------------

    result = "\n".join(
        output
    )

    with open(
        "myanmarpost_prices.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            result
        )

    # -----------------------------------------------------
    # DISPLAY RESULT
    # -----------------------------------------------------

    elapsed = (
        time.time()
        - start_time
    )

    print("")

    print(
        "========================================"
    )

    print(
        result
    )

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
        "Output file: "
        "myanmarpost_prices.txt"
    )

    print(
        ""
    )

    print(
        f"Total runtime: "
        f"{elapsed:.1f} seconds"
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
