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
        
    # Agent 3: Lead Cloud Architect (Synthesizer)
    architect_prompt = f"""
    You are the Lead Cloud Architect. You have received reports from your Financial and Risk teams regarding a proposed migration.
    
    Financial Report:
    {financial_analysis}
    
    Risk Report:
    {risk_analysis}
    
    Synthesize these findings into a final, executive recommendation on whether to proceed with migrating {simulation_result.get('target_component')} to the {simulation_result.get('destination')}. 
    Provide actionable mitigation steps for the risks identified.
    Keep your response concise (4-5 sentences).
    """
    
    architect_recommendation = ask_agent(architect_prompt)
        
    return {
        "financial": financial_analysis,
        "risk": risk_analysis,
        "architect": architect_recommendation
    }
