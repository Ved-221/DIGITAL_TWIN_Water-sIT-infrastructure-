import json
import re

def fuzzy_parse_json(text):
    try:
        # Try raw json loads
        return json.loads(text)
    except Exception:
        pass
        
    try:
        # Try to find a JSON object using regex
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
            # Remove trailing commas before closing braces/brackets
            cleaned = re.sub(r',\s*\}', '}', cleaned)
            cleaned = re.sub(r',\s*\]', ']', cleaned)
            return json.loads(cleaned)
    except Exception:
        pass
        
    return None

