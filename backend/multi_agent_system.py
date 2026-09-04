import os
import json
from typing import Dict, Any
from openai import OpenAI

def run_multi_agent_analysis(simulation_result: Dict[str, Any]) -> Dict[str, str]:
    """
    Runs a multi-agent pipeline using Gemini to analyze simulation data from different perspectives.
    """
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if openrouter_key:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
        model_name = "meta-llama/llama-3.1-8b-instruct" # Standard default for OpenRouter
    elif groq_key:
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
        model_name = "llama3-8b-8192"
    elif openai_key:
        client = OpenAI(api_key=openai_key)
        model_name = "gpt-4o-mini"
    else:
        err = "Agents unavailable: Please set GROQ_API_KEY or OPENROUTER_API_KEY."
        return {"financial": err, "risk": err, "architect": err}
        
    sim_data_str = json.dumps(simulation_result, indent=2)
    
    def ask_agent(prompt: str) -> str:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
    
    # Agent 1: Financial Analyst
    financial_prompt = f"""
    You are the Lead Cloud Financial Analyst. 
    Analyze the following migration simulation data.
    Focus strictly on the 'cost_delta_monthly'. 
    If the data is currently using fallback values, treat them as initial estimates, but evaluate the 15% migration penalty.
    Keep your response concise (3-4 sentences).
    
    Simulation Data:
    {sim_data_str}
    """
    
    # Agent 2: Security & Risk Analyst
    risk_prompt = f"""
    You are the Senior Infrastructure Risk Assessor.
    Analyze the following migration simulation data.
    Focus strictly on the 'risk_score', 'estimated_downtime_minutes', 'affected_count', and 'critical_flags'.
    Explain the severity of the cross-environment dependencies and blast radius.
    Keep your response concise (3-4 sentences).
    
    Simulation Data:
    {sim_data_str}
    """
    
    financial_analysis = ask_agent(financial_prompt)
    risk_analysis = ask_agent(risk_prompt)
        
    # Agent 3: Lead Cloud Architect (Prescriptive Optimization Engine)
    architect_prompt = f"""
    You are the Lead Cloud Architect. You have received reports from your Financial and Risk teams regarding a proposed migration.
    
    Financial Report:
    {financial_analysis}
    
    Risk Report:
    {risk_analysis}
    
    Your goal is to provide a prescriptive plan so the user can modify their architecture to achieve 0 problems (e.g. no downtime, favorable cost).
    Look at the affected components: {simulation_result.get('affected_component_names', [])}
    
    Synthesize the findings and output a strict JSON object with EXACTLY these two keys:
    1. "explanation": A 2-sentence executive summary of the current risks.
    2. "recommended_actions": A JSON array of 3-4 specific, actionable architectural changes the user should make in their manual digital twin (e.g. "Add a Load Balancer in front of {simulation_result.get('target_component')}", "Remove strict dependency on X").
    
    You MUST output valid JSON only, with no markdown block backticks or additional text.
    """
    
    architect_recommendation = ask_agent(architect_prompt)
    
    try:
        import re
        import ast
        
        cleaned_json = architect_recommendation.strip()
        if cleaned_json.startswith("```json"):
            cleaned_json = cleaned_json[7:-3].strip()
        elif cleaned_json.startswith("```"):
            cleaned_json = cleaned_json[3:-3].strip()

        # Try to extract the JSON block if it still has garbage
        json_match = re.search(r'\{.*\}', cleaned_json, re.DOTALL)
        if json_match:
            cleaned_json = json_match.group(0)
            
        try:
            parsed = json.loads(cleaned_json)
        except Exception:
            # Fallback to ast literal eval if json fails (e.g. trailing commas, single quotes)
            # Replace true/false/null to Python equivalents before eval
            eval_str = cleaned_json.replace("true", "True").replace("false", "False").replace("null", "None")
            parsed = ast.literal_eval(eval_str)

        explanation = parsed.get("explanation", "Recommendation generated.")
        raw_actions = parsed.get("recommended_actions", [])
        
        # Ensure it's a list of strings even if LLM returned objects
        recommended_actions = []
        if isinstance(raw_actions, list):
            for action in raw_actions:
                if isinstance(action, dict):
                    # If it's a dict like {"action": "...", "description": "..."}
                    val = action.get("action", "") or action.get("description", "")
                    if val:
                        recommended_actions.append(str(val))
                else:
                    recommended_actions.append(str(action))
        elif isinstance(raw_actions, str):
            recommended_actions.append(raw_actions)
                
    except Exception as e:
        print(f"JSON Parse Error: {str(e)}", flush=True)
        print(f"Raw string was: {architect_recommendation}", flush=True)
        explanation = architect_recommendation
        recommended_actions = []
        
    return {
        "financial": financial_analysis,
        "risk": risk_analysis,
        "architect": explanation,
        "recommended_actions": recommended_actions
    }
