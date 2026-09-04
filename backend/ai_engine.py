import os
import json
import logging
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("infratwin.ai_engine")

SYSTEM_INSTRUCTION = """
You are an expert IT Infrastructure & SRE Architect AI assistant.
Your responsibility is ONLY to act as an EXPLANATION LAYER for an IT infrastructure Digital Twin.
You do NOT calculate numerical risk, you do NOT discover dependencies, and you do NOT train or override the model.
All numerical values (risk score, downtime, blast radius, cost) and dependency connections provided in the input JSON are AUTHORITATIVE ground truth.

RULES:
1. Base your explanation STRICTLY AND ENTIRELY on the provided JSON data.
2. DO NOT hallucinate or invent infrastructure components, metric values, or dependencies not present in the payload.
3. Keep all numbers (downtime minutes, risk score, dollar amounts, blast radius count) EXACTLY identical to the provided data.
"""

def generate_fallback_explanation(simulation_data: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    target_comp = simulation_data.get("target_component", "Unknown Component")
    target_type = simulation_data.get("target_component_type", "resource")
    action = simulation_data.get("action", simulation_data.get("change_action", "NO_ACTION"))
    action_clean = action.replace("_", " ")
    
    blast_radius = simulation_data.get("blast_radius", simulation_data.get("affected_count", simulation_data.get("total_nodes_affected", 0)))
    
    risk_score = simulation_data.get("risk_score", 0)
    risk_level = simulation_data.get("risk_level", "LOW")
    downtime_min = simulation_data.get("estimated_downtime_minutes")
    cost_impact = simulation_data.get("cost_impact", simulation_data.get("cost_delta_monthly"))
    warnings = simulation_data.get("critical_warnings", simulation_data.get("critical_flags", []))
    downtime_basis = simulation_data.get("downtime_explanation", "")
    cost_basis = simulation_data.get("cost_explanation", "")

    what_happening = f"Operational action '{action_clean}' evaluated for {target_comp} ({target_type}) within the infrastructure topology."
    why_analysis = f"Action '{action_clean}' impacts {blast_radius} component(s) with an evaluated risk level of {risk_level} ({risk_score}/100)."
    
    if cost_impact is not None:
        cost_str = f"+${cost_impact:,.2f}/mo" if cost_impact >= 0 else f"-${abs(cost_impact):,.2f}/mo"
    else:
        cost_str = "Unavailable (requires target SKU pricing)"
        
    dt_str = f"{downtime_min}m" if downtime_min is not None else "Unavailable (data transfer/storage metrics required)"
    
    sim_prediction = f"Estimated downtime: {dt_str}; monthly cost impact: {cost_str}; blast radius: {blast_radius} component(s)."
    
    key_risks = f"Risk severity: {risk_level} ({risk_score}/100). Warnings: {'; '.join(warnings) if warnings else 'None detected'}."
    
    considerations = [
        f"Pre-change verification: Confirm health check and snapshot status for {target_comp}.",
        f"Maintenance window: Coordinate execution during off-peak hours for {blast_radius} affected component(s).",
        f"Rollback plan: Ensure automated rollback safeguards are verified before applying '{action_clean}'."
    ]

    full_explanation = f"### Infrastructure Change Assessment: {action_clean} on {target_comp}\n\n{what_happening}\n\n**Prediction:** {sim_prediction}\n\n**Risk:** {key_risks}"
    executive_recommendation = f"Recommended Action: {action_clean}\nWhy: {why_analysis}\nRisk: {risk_level} ({risk_score}/100)\nDowntime: {dt_str}"

    structured_data = {
        "what_is_happening": what_happening,
        "why_analysis": why_analysis,
        "sim_prediction": sim_prediction,
        "key_risks": key_risks,
        "engineer_considerations": considerations
    }
    return full_explanation, executive_recommendation, structured_data

def generate_explanation(simulation_result: Dict[str, Any]) -> Tuple[str, str]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        exp, rec, _ = generate_fallback_explanation(simulation_result)
        return exp, rec

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"{SYSTEM_INSTRUCTION}\n\nSimulation Data:\n{json.dumps(simulation_result, indent=2)}\n\nOutput JSON with keys 'explanation' and 'recommendation'."
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        return data.get("explanation", ""), data.get("recommendation", "")
    except Exception as e:
        exp, rec, _ = generate_fallback_explanation(simulation_result)
        return exp, rec

def get_ai_recommendation(component_data: Dict[str, Any], simulation_data: Dict[str, Any]) -> str:
    merged = {**simulation_data, "target_component": component_data.get("name", "Target")}
    _, recommendation, _ = generate_fallback_explanation(merged)
    return recommendation

def analyze_simulation_with_ai(component_data: Dict[str, Any], simulation_data: Dict[str, Any]) -> str:
    merged = {**simulation_data, "target_component": component_data.get("name", "Target")}
    explanation, _, _ = generate_fallback_explanation(merged)
    return explanation

def chat_with_twin(prompt: str, twin_context: Dict[str, Any]) -> str:
    prompt_lower = prompt.lower()
    env = twin_context.get("active_environment", "active")
    nodes = twin_context.get("total_nodes", 0)
    edges = twin_context.get("total_edges", 0)
    spofs = twin_context.get("spof_nodes", [])
    cost = twin_context.get("total_monthly_cost", 0.0)
    curr = twin_context.get("currency", "USD")
    curr_sym = "₹" if curr == "INR" else "$"

    if any(w in prompt_lower for w in ["spof", "single point", "failure", "bottleneck"]):
        if spofs:
            spof_list = ", ".join(spofs) if isinstance(spofs, list) else str(spofs)
            return f"In environment '{env}', the identified Single Points of Failure (SPOFs) are: {spof_list}. A failure in these components would partition the topology."
        return f"No articulation point SPOFs were identified in the current '{env}' topology."

    if any(w in prompt_lower for w in ["cost", "spend", "expense", "budget"]):
        return f"The total estimated monthly infrastructure cost for environment '{env}' is {curr_sym}{cost:,.2f} across {nodes} provisioned resource(s)."

    return f"Environment '{env}' currently comprises {nodes} resources, {edges} dependencies, and an estimated monthly burn of {curr_sym}{cost:,.2f}."

