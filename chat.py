import ollama
import requests
from bs4 import BeautifulSoup
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_article_text(url):
    """
    Fetches and extracts text from a news article.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, 'html.parser')
        # Find the main content div and extract text from all p tags within it
        main_content = soup.find('div', id='article')
        if main_content:
            article_text = ' '.join(p.get_text() for p in main_content.find_all('p'))
            return article_text
        else:
            # Fallback for pages without the specific id
            return ' '.join(p.get_text() for p in soup.find_all('p'))
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching article: {e}")
        return None

def warmup():
    """
    Performs the initial prompt to the LLM.
    """
    messages = []

    # 1. Initial prompt
    initial_prompt = "I'll give you an official statement from FOMC. Based on this statement, please tell me: (1) Whether this article describes a Federal Reserve decision about interest rates (including cuts, increases, or maintaining current rates). Your answer must be either Yes or No, and nothing else. I'll give you the statement shortly."
    messages.append({'role': 'user', 'content': initial_prompt})
    
    response = ollama.chat(model='gemma3:4b', messages=messages)
    assistant_response = response['message']['content']
    logging.debug(f"LLM Response (ignored): {assistant_response}")
    messages.append({'role': 'assistant', 'content': assistant_response})
    return messages

def extract(article_text, messages):
    """
    Performs a structured conversation with the Gemma3 4B model and returns the result.
    """
    # 2. Retrieve and send article
    if not article_text:
        return None

    messages.append({'role': 'user', 'content': article_text})
    response = ollama.chat(model='gemma3:4b', messages=messages)
    assistant_response = response['message']['content'].strip()
    logging.debug(f"LLM Response: {assistant_response}")
    messages.append({'role': 'assistant', 'content': assistant_response})

    # 3. If the LLM answers No, the conversation ends.
    if 'no' in assistant_response.lower():
        return None

    # 4. Ask for the exact sentence
    sentence_prompt = "Tell me the exact sentence that explicitly mentions the Federal Reserve's interest rate decision (whether it's a cut, increase, or maintaining current rates)."
    messages.append({'role': 'user', 'content': sentence_prompt})
    response = ollama.chat(model='gemma3:4b', messages=messages)
    assistant_response = response['message']['content']
    logging.debug(f"LLM Response (ignored): {assistant_response}")
    messages.append({'role': 'assistant', 'content': assistant_response})

    # 5. Ask for the basis points in JSON format
    basis_points_prompt = """Based on your answer above, analyze the Federal Reserve's interest rate decision and provide your answer in a JSON format with two keys:
1. "direction": The value should be either "increase", "decrease", or "maintain" (if rates are kept at current levels).
2. "basis_points": The value should be the number of basis points of the change (e.g., 50 for a 0.50% change, or 0 if rates are maintained).

Your response should only be the JSON object."""
    messages.append({'role': 'user', 'content': basis_points_prompt})
    response = ollama.chat(model='gemma3:4b', messages=messages)
    assistant_response = response['message']['content'].strip()
    logging.debug(f"LLM Response: {assistant_response}")
    messages.append({'role': 'assistant', 'content': assistant_response})
    
    try:
        # Clean the response to extract only the JSON part
        json_str = assistant_response[assistant_response.find('{'):assistant_response.rfind('}')+1]
        data = json.loads(json_str)
        direction = data.get("direction")
        basis_points = data.get("basis_points")

        if direction == "decrease":
            basis_points = -basis_points
        elif direction == "maintain":
            basis_points = 0
        
        return basis_points

    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
        logging.error(f"Error parsing LLM response: {e}")
        logging.warning("Could not determine the final answer.")
        return None

if __name__ == "__main__":
    messages = warmup()
    article_url = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm"
    article_text = get_article_text(article_url)
    final_answer = extract(article_text, messages)
    if final_answer is not None:
        print(f"Final Answer: {final_answer}")
