
import requests
import re
import sys

def find_rate_reduction(url):
    """
    Finds the interest rate reduction from a given URL.

    Args:
        url: The URL of the article to parse.

    Returns:
        The rate reduction as a string, or None if not found.
    """
    response = requests.get(url)

    if response.status_code == 200:
        # The regex looks for a number (integer or float) followed by
        # "percentage point", "basis points", or "%", or a fraction.
        # It also handles fractions like "1/2" or "1/4".
        regex = r"(\d+/\d+|\d*\.?\d+)\s*(percentage point|basis points|%)"
        
        # Search for the pattern in the text of the response
        match = re.search(regex, response.text, re.IGNORECASE)

        if match:
            reduction_str = match.group(1)
            unit = match.group(2).lower()

            if "/" in reduction_str:
                parts = reduction_str.split('/')
                reduction = float(parts[0]) / float(parts[1])
            else:
                reduction = float(reduction_str)

            if "basis points" in unit:
                return reduction / 100
            else:
                return reduction
        else:
            return None
    else:
        print(f"Failed to retrieve URL. Status code: {response.status_code}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        rate_reduction = find_rate_reduction(url)
        if rate_reduction is not None:
            print(f"Interest rate reduction found: {rate_reduction}%")
        else:
            print("No interest rate reduction found in the article.")
