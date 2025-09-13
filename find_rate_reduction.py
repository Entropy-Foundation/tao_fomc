
import requests
import re
import sys

def extract_rate_change_from_text(text):
    """
    Extracts interest rate change from text and returns it in basis points.

    Args:
        text: The text to parse for rate changes.

    Returns:
        The rate change in basis points as an integer (negative for reductions, 
        positive for increases), or None if not found.
    """
    # Enhanced regex to capture context words that indicate direction
    rate_pattern = r"(cut|reduce|lower|decrease|raise|increase|hike|boost).*?(\d+/\d+|\d*\.?\d+)\s*(percentage point|basis points?|%)"
    
    # Search for the pattern in the text
    match = re.search(rate_pattern, text, re.IGNORECASE)

    if match:
        direction_word = match.group(1).lower()
        rate_str = match.group(2)
        unit = match.group(3).lower()

        # Parse the rate value
        if "/" in rate_str:
            parts = rate_str.split('/')
            rate_value = float(parts[0]) / float(parts[1])
        else:
            rate_value = float(rate_str)

        # Convert to basis points
        if "basis point" in unit:
            basis_points = int(rate_value)
        else:  # percentage points or %
            basis_points = int(rate_value * 100)

        # Determine sign based on direction word
        if direction_word in ['cut', 'reduce', 'lower', 'decrease']:
            return -basis_points
        elif direction_word in ['raise', 'increase', 'hike', 'boost']:
            return basis_points
        else:
            # Default to negative for historical compatibility
            return -basis_points
    
    return None


def find_rate_reduction(url):
    """
    Finds the interest rate change from a given URL.

    Args:
        url: The URL of the article to parse.

    Returns:
        The rate change in basis points as an integer (negative for reductions,
        positive for increases), or None if not found.
    """
    response = requests.get(url)

    if response.status_code == 200:
        return extract_rate_change_from_text(response.text)
    else:
        print(f"Failed to retrieve URL. Status code: {response.status_code}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        rate_change = find_rate_reduction(url)
        if rate_change is not None:
            if rate_change < 0:
                print(f"Interest rate reduction found: {abs(rate_change)} basis points")
            elif rate_change > 0:
                print(f"Interest rate increase found: {rate_change} basis points")
            else:
                print("No interest rate change found (0 basis points)")
        else:
            print("No interest rate change found in the article.")
