import google.generativeai as genai
import os
import json
from typing import Dict, Any

# Ensure GEMINI_API_KEY is in the environment
# GenAI library automatically looks for GEMINI_API_KEY env var

def generate_explanation(simulation_result: Dict[str, Any]) -> tuple[str, str]:
    """
    Takes the structured simulation result and generates a plain-English explanation 
    and recommendation using Gemini.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (
            "AI explanation unavailable: GEMINI_API_KEY environment variable is not set.",
            "Please configure your API key to enable AI insights."
        )
    
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-1.5-flash")
    
    prompt = f"""
    You are an expert IT Infrastructure Architect. I will provide you with the JSON 
    output of an infrastructure change simulation.

    Your job is to:
    1. Explain WHY the risk is what it is, focusing on the blast radius and critical flags.
    2. Provide a clear, step-by-step recommendation on the safest way to execute this change.

    RULES:
    - Base your entire explanation ONLY on the provided JSON data.
    - DO NOT invent or hallucinate any infrastructure components that are not in the JSON.
    - Write clearly, for an IT executive audience.
    - Output MUST be a valid JSON object with exactly two keys: "explanation" and "recommendation".

    Simulation Data:
    {json.dumps(simulation_result, indent=2)}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        return data.get("explanation", ""), data.get("recommendation", "")
    except Exception as e:
        return f"Error generating AI explanation: {str(e)}", "Please consult a human architect."
