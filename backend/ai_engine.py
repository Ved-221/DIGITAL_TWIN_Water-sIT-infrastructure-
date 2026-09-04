import os
import json
import logging
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("infratwin.ai_engine")

SYSTEM_INSTRUCTION = """
You are an expert IT Infrastructure & SRE Architect AI assistant.
Your responsibility is ONLY to act as an EXPLANATION LAYER for an IT infrastructure Digital Twin.
You do NOT calculate numerical risk, you do NOT discover dependencies, and you do NOT train or override the ML recommendation model.
All numerical values (risk score, downtime, blast radius, cost, confidence) and dependency connections provided in the input JSON are AUTHORITATIVE ground truth.

RULES:
1. Base your explanation STRICTLY AND ENTIRELY on the provided JSON data.
2. DO NOT hallucinate or invent infrastructure components, metric values, or dependencies not present in the payload.
3. Keep all numbers (downtime minutes, risk score, dollar amounts, blast radius count) EXACTLY identical to the provided data.
4. Structure your response to answer these 6 specific questions:
   - What is happening (target component and proposed action)
   - Why the ML model recommended the action (telemetry drivers and reasoning features)
   - What infrastructure components are affected (downstream and upstream dependencies)
   - What the simulation predicts (downtime, cost change, blast radius scale)
   - Important risks (critical flags, single point of failure exposure, and severity)
   - What an engineer should consider before applying the change (actionable precautions and rollback safeguards)
5. Return a valid JSON object matching the requested schema.
"""

def generate_fallback_explanation(simulation_data: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """
    Generates a deterministic, structured architectural explanation when GEMINI_API_KEY
    is not set or the remote AI call is unavailable. Strictly adheres to backend ground truth.
    """
    target_comp = simulation_data.get("target_component", "Unknown Component")
    target_type = simulation_data.get("target_component_type", "resource")
    action = simulation_data.get("action", simulation_data.get("change_action", "NO_ACTION"))
    action_clean = action.replace("_", " ")
    
    blast_radius = simulation_data.get("blast_radius", simulation_data.get("affected_count", 0))
    affected_components = simulation_data.get("affected_components", [])
    affected_details = simulation_data.get("affected_components_details", [])
    
    risk_score = simulation_data.get("risk_score", 0)
    risk_level = simulation_data.get("risk_level", "LOW")
    downtime_min = simulation_data.get("estimated_downtime_minutes", 0)
    cost_impact = simulation_data.get("cost_impact", simulation_data.get("cost_delta_monthly", 0.0))
    warnings = simulation_data.get("critical_warnings", simulation_data.get("critical_flags", []))
    
    ml_confidence = simulation_data.get("ml_confidence")
    ml_reasoning = simulation_data.get("ml_reasoning_features", [])

    env_source = simulation_data.get("environment_source", "aws_api")
    is_manual = env_source == "manual" or simulation_data.get("is_manual", False)

    # 1. What is happening
    if is_manual:
        what_happening = (
            f"Operational action '{action_clean}' is evaluated for {target_comp} ({target_type}). "
            f"This change targets a user-defined component within the manually configured Digital Twin topology."
        )
    else:
        what_happening = (
            f"Operational action '{action_clean}' is evaluated for {target_comp} ({target_type}). "
            f"The change targets this node within the verified infrastructure topology."
        )

    # 2. Why ML recommended action
    if ml_reasoning:
        telemetry_signals = [
            f"{r.get('feature', str(r))}={r.get('value', 'N/A')} ({r.get('impact', 'neutral')} impact)"
            if isinstance(r, dict) else str(r)
            for r in ml_reasoning
        ]
        signals_str = ", ".join(telemetry_signals)
        conf_str = f" with {int(ml_confidence * 100)}% model confidence" if ml_confidence is not None else ""
        source_label = "user-configured simulation assumptions" if is_manual else "current operational telemetry signals"
        why_ml = (
            f"The Random Forest ML recommendation engine suggested '{action_clean}'{conf_str} "
            f"based on {source_label}: {signals_str}."
        )
    else:
        why_ml = (
            f"Action '{action_clean}' was manually initiated for change impact simulation "
            f"against the {'manually created' if is_manual else 'current AWS'} infrastructure topology."
        )

    # 3. What infrastructure components are affected
    if affected_details:
        sample_names = [d.get("name", d.get("id")) for d in affected_details[:4]]
        remaining = len(affected_details) - len(sample_names)
        suffix = f" and {remaining} other resource(s)" if remaining > 0 else ""
        affected_summary = (
            f"{blast_radius} component(s) exist within the topological blast radius: "
            f"{', '.join(sample_names)}{suffix}."
        )
    elif affected_components:
        sample_ids = affected_components[:4]
        remaining = len(affected_components) - len(sample_ids)
        suffix = f" and {remaining} others" if remaining > 0 else ""
        affected_summary = (
            f"{blast_radius} component(s) exist within the topological blast radius: "
            f"{', '.join(sample_ids)}{suffix}."
        )
    else:
        affected_summary = "No downstream or upstream components are affected (isolated node)."

    # 4. What the simulation predicts
    cost_str = f"+${cost_impact:.2f}/mo" if cost_impact >= 0 else f"-${abs(cost_impact):.2f}/mo (savings)"
    sim_prediction = (
        f"The simulation engine predicts an estimated downtime of {downtime_min} minute(s), "
        f"a monthly cost impact of {cost_str}, and a blast radius spanning {blast_radius} component(s)."
    )

    # 5. Important risks
    if warnings:
        warn_str = " ".join(warnings)
        key_risks = (
            f"Evaluated risk level is {risk_level} (risk score: {risk_score}/100). "
            f"Key warnings detected: {warn_str}"
        )
    else:
        key_risks = (
            f"Evaluated risk level is {risk_level} (risk score: {risk_score}/100). "
            f"No critical single-point-of-failure or cross-environment hazards were flagged."
        )

    # 6. What an engineer should consider
    considerations = [
        f"Pre-change verification: Confirm health check and snapshot status for {target_comp}.",
        f"Maintenance window: Coordinate execution during off-peak traffic hours to safeguard the {blast_radius} affected component(s).",
        f"Rollback plan: Ensure automated or documented rollback procedures are validated before applying '{action_clean}'."
    ]
    if downtime_min > 0:
        considerations.append(f"Downtime window: Prepare client notification for the anticipated {downtime_min}-minute service interruption.")
    if cost_impact > 50:
        considerations.append(f"Budget approval: Verify that the projected +${cost_impact:.2f}/month expenditure aligns with allocated capacity budget.")

    # Format into clean architectural markdown explanation
    full_explanation = f"""### Infrastructure Change Assessment: {action_clean} on {target_comp}

{what_happening}

**Recommended Action:**
{action_clean}

**Why (ML Model Rationale):**
{why_ml}

**Impact (Infrastructure Topology & Blast Radius):**
{affected_summary}

**Simulation Forecast:**
{sim_prediction}

**Risk & Critical Warnings:**
{key_risks}

**Engineer Pre-Change Checklist:**
""" + "\n".join([f"- {c}" for c in considerations])

    executive_recommendation = (
        f"Recommended Action: {action_clean}\n"
        f"Why: {why_ml}\n"
        f"Impact: {blast_radius} downstream/upstream component(s) affected.\n"
        f"Risk: {risk_level} ({risk_score}/100)\n"
        f"Warnings: {'; '.join(warnings) if warnings else 'None'}"
    )

    structured_data = {
        "what_is_happening": what_happening,
        "why_ml_recommended": why_ml,
        "affected_components_summary": affected_summary,
        "simulation_prediction": sim_prediction,
        "key_risks": key_risks,
        "engineer_considerations": considerations
    }

    return full_explanation, executive_recommendation, structured_data


def generate_explanation(simulation_result: Dict[str, Any]) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Takes the structured simulation result (combining AWS infrastructure, dependency graph,
    ML recommendation, and simulation metrics) and produces a 6-point architectural explanation.
    Uses Gemini if GEMINI_API_KEY is present; otherwise falls back to deterministic structured engine.
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.info("GEMINI_API_KEY not configured. Using deterministic architectural explanation engine.")
        return generate_fallback_explanation(simulation_result)

    # Prepare Gemini client using Google GenAI SDK
    prompt = f"""
I have provided the authoritative JSON output of an infrastructure change simulation combining
AWS topology, CloudWatch metrics, Random Forest ML recommendation, and dependency graph blast radius.

Convert this data into a clear human-readable explanation covering these 6 facets:
1. What is happening (target component and proposed action)
2. Why the ML model recommended the action (operational telemetry drivers)
3. What infrastructure components are affected (downstream and upstream dependencies)
4. What the simulation predicts (downtime minutes, monthly cost change, blast radius count)
5. Important risks (deterministic risk score/level and critical flags)
6. What an engineer should consider before applying the change (actionable pre-flight checklist)

Output MUST be a valid JSON object with the following schema:
{{
  "what_is_happening": "string",
  "why_ml_recommended": "string",
  "affected_components_summary": "string",
  "simulation_prediction": "string",
  "key_risks": "string",
  "engineer_considerations": ["string", "string", ...],
  "full_markdown_explanation": "string",
  "executive_recommendation": "string"
}}

Simulation Data:
{json.dumps(simulation_result, indent=2)}
"""

    try:
        from google import genai
        from google.genai import types

        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        data = json.loads(response.text)
        
        full_md = data.get("full_markdown_explanation")
        if not full_md:
            target = simulation_result.get("target_component", "Component")
            action = simulation_result.get("action", "Action")
            full_md = f"""### Infrastructure Change Assessment: {action} on {target}

**Recommended Action:**
{action}

**Why (ML Model Rationale):**
{data.get('why_ml_recommended', '')}

**Impact (Infrastructure Topology & Blast Radius):**
{data.get('affected_components_summary', '')}

**Simulation Forecast:**
{data.get('simulation_prediction', '')}

**Risk & Critical Warnings:**
{data.get('key_risks', '')}

**Engineer Pre-Change Checklist:**
""" + "\n".join([f"- {c}" for c in data.get("engineer_considerations", [])])

        exec_rec = data.get(
            "executive_recommendation",
            f"Recommended Action: {simulation_result.get('action')}\nRisk: {simulation_result.get('risk_level')}"
        )
        structured = {
            "what_is_happening": data.get("what_is_happening", ""),
            "why_ml_recommended": data.get("why_ml_recommended", ""),
            "affected_components_summary": data.get("affected_components_summary", ""),
            "simulation_prediction": data.get("simulation_prediction", ""),
            "key_risks": data.get("key_risks", ""),
            "engineer_considerations": data.get("engineer_considerations", [])
        }
        return full_md, exec_rec, structured

    except Exception as e:
        logger.warning("Gemini API call failed (%s). Falling back to deterministic explanation engine.", str(e))
        return generate_fallback_explanation(simulation_result)


def generate_solution_fallback_explanation(
    before_state: Dict[str, Any],
    applied_solution: Dict[str, Any],
    after_state: Dict[str, Any],
    comparison: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """
    Deterministic architectural explanation of an applied feasible solution.
    Strictly uses authoritative calculated before/after values without hallucination.
    """
    sol_title = applied_solution.get("title", "Infrastructure Solution")
    sol_desc = applied_solution.get("description", "")
    target_comp = before_state.get("target_component", "target resource")
    
    before_risk_score = before_state.get("risk_score", 0)
    before_risk_level = before_state.get("risk_level", "UNKNOWN")
    after_risk_score = after_state.get("risk_score", 0)
    after_risk_level = after_state.get("risk_level", "UNKNOWN")
    risk_diff = max(0, before_risk_score - after_risk_score)
    
    before_blast = before_state.get("blast_radius", 0)
    after_blast = after_state.get("blast_radius", 0)
    blast_diff = max(0, before_blast - after_blast)
    
    before_cost = before_state.get("monthly_cost", 0.0)
    after_cost = after_state.get("monthly_cost", 0.0)
    cost_delta = after_cost - before_cost
    curr = comparison.get("cost", {}).get("currency") or ("INR" if before_state.get("is_manual") else "USD")
    curr_sym = "₹" if curr == "INR" else "$"
    cost_str = f"+{curr_sym}{cost_delta:,.2f}/mo" if cost_delta >= 0 else f"-{curr_sym}{abs(cost_delta):,.2f}/mo"
    
    downtime_min = after_state.get("downtime_min", 0)
    resilience_val = comparison.get("resilience", {}).get("after", "Enhanced Redundancy")
    perf_val = comparison.get("performance", {}).get("after", "Capacity headroom preserved")

    # 1. What changed
    what_changed = (
        f"Applied '{sol_title}' to {target_comp}. "
        f"{sol_desc} "
        f"The Digital Twin topology model was updated with candidate resource configurations and routing dependencies."
    )

    # 2. Why it helps
    why_it_helps = (
        f"This solution addresses the identified architectural risk by providing {resilience_val.lower()}. "
        f"It establishes operational redundancy, isolating potential failures and preventing domino outages across dependent services."
    )

    # 3. Affected dependencies
    affected_dependencies = (
        f"Dependencies connected to {target_comp} now benefit from isolated failover pathways. "
        f"Blast radius decreased by {blast_diff} node(s), reducing cascading disruption if {target_comp} undergoes degradation or maintenance."
    )

    # 4. What simulation indicates
    sim_indications = (
        f"Deterministic simulation indicates risk score decreased from {before_risk_level} ({before_risk_score}/100) to "
        f"{after_risk_level} ({after_risk_score}/100) (-{risk_diff} pts). "
        f"Topological blast radius shifted from {before_blast} to {after_blast} node(s). "
        f"Projected cost impact is {cost_str} ({curr_sym}{before_cost:,.2f}/mo -> {curr_sym}{after_cost:,.2f}/mo). "
        f"Estimated execution downtime is {downtime_min} minute(s)."
    )

    # 5. Trade-offs and limitations
    tradeoffs = [
        f"Expenditure: Incurs an incremental operational expenditure of {cost_str}.",
        f"Maintenance Window: Requires an estimated {downtime_min}-minute cutover window for configuration synchronization." if downtime_min > 0 else "Execution: Zero-downtime rolling update supported.",
        f"Performance & State: {perf_val}. Dependent consumers must accommodate dual-node health check intervals."
    ]
    tradeoffs_str = " ".join(tradeoffs)

    # Markdown format
    full_md = f"""### Feasible Solution Assessment: {sol_title} on {target_comp}

**1. What Changed:**
{what_changed}

**2. Why It Helps:**
{why_it_helps}

**3. Affected Dependencies:**
{affected_dependencies}

**4. Simulation Indications:**
{sim_indications}

**5. Trade-offs & Limitations:**
""" + "\n".join([f"- {t}" for t in tradeoffs])

    structured = {
        "what_changed": what_changed,
        "why_it_helps": why_it_helps,
        "affected_dependencies": affected_dependencies,
        "simulation_indications": sim_indications,
        "trade_offs_and_limitations": tradeoffs
    }

    return full_md, structured


def generate_solution_explanation(
    before_state: Dict[str, Any],
    applied_solution: Dict[str, Any],
    after_state: Dict[str, Any],
    comparison: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    """
    Generates an architectural explanation for an applied feasible solution using Gemini,
    with automatic fallback to the deterministic explanation engine.
    Strictly avoids hallucinated numbers; enforces adherence to calculated comparison metrics.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not configured. Using deterministic solution explanation engine.")
        return generate_solution_fallback_explanation(before_state, applied_solution, after_state, comparison)

    prompt = f"""
You are an expert IT Infrastructure & SRE Architect AI assistant acting as an EXPLANATION LAYER.
An engineer has selected and applied a FEASIBLE SOLUTION to resolve an identified infrastructure problem in a Digital Twin.

Input Data:
Before State: {json.dumps(before_state, indent=2)}
Applied Solution: {json.dumps(applied_solution, indent=2)}
After State: {json.dumps(after_state, indent=2)}
Comparison Metrics: {json.dumps(comparison, indent=2)}

Produce a clear architectural explanation covering:
1. What changed (specific topology and resource modifications)
2. Why it helps (resilience improvements and failure isolation)
3. Affected dependencies (upstream/downstream routes)
4. What the simulation indicates (exact numerical risk reduction, cost delta, blast radius, downtime)
5. Trade-offs or limitations (cost increase, maintenance window, state replication)

RULES:
- Base your explanation strictly on the provided JSON data.
- NEVER invent resources, numbers, or fake statistics.
- Use EXACT numbers from the comparison metrics.
- Return a valid JSON object matching this schema:
{{
  "what_changed": "string",
  "why_it_helps": "string",
  "affected_dependencies": "string",
  "simulation_indications": "string",
  "trade_offs_and_limitations": ["string", "string", ...],
  "full_markdown_explanation": "string"
}}
"""

    try:
        from google import genai
        from google.genai import types

        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        data = json.loads(response.text)
        full_md = data.get("full_markdown_explanation")
        if not full_md:
            sol_title = applied_solution.get("title", "Infrastructure Solution")
            target = before_state.get("target_component", "Resource")
            full_md = f"""### Feasible Solution Assessment: {sol_title} on {target}

**1. What Changed:**
{data.get('what_changed', '')}

**2. Why It Helps:**
{data.get('why_it_helps', '')}

**3. Affected Dependencies:**
{data.get('affected_dependencies', '')}

**4. Simulation Indications:**
{data.get('simulation_indications', '')}

**5. Trade-offs & Limitations:**
""" + "\n".join([f"- {t}" for t in data.get("trade_offs_and_limitations", [])])

        structured = {
            "what_changed": data.get("what_changed", ""),
            "why_it_helps": data.get("why_it_helps", ""),
            "affected_dependencies": data.get("affected_dependencies", ""),
            "simulation_indications": data.get("simulation_indications", ""),
            "trade_offs_and_limitations": data.get("trade_offs_and_limitations", [])
        }
        return full_md, structured

    except Exception as e:
        logger.warning("Gemini API call for solution explanation failed (%s). Falling back to deterministic engine.", str(e))
        return generate_solution_fallback_explanation(before_state, applied_solution, after_state, comparison)


def get_ai_recommendation(component_data: Dict[str, Any], simulation_data: Dict[str, Any]) -> str:
    """Convenience helper extracting recommendation string for a component and simulation result."""
    merged = {**simulation_data, "target_component": component_data.get("name", "Target")}
    if not os.environ.get("GEMINI_API_KEY"):
        _, recommendation, _ = generate_fallback_explanation(merged)
    else:
        _, recommendation, _ = generate_explanation(merged)
    return recommendation


def analyze_simulation_with_ai(component_data: Dict[str, Any], simulation_data: Dict[str, Any]) -> str:
    """Convenience helper extracting explanation string for a component and simulation result."""
    merged = {**simulation_data, "target_component": component_data.get("name", "Target")}
    if not os.environ.get("GEMINI_API_KEY"):
        explanation, _, _ = generate_fallback_explanation(merged)
    else:
        explanation, _, _ = generate_explanation(merged)
    return explanation


def chat_with_twin(prompt: str, twin_context: Dict[str, Any]) -> str:
    """Answers conversational questions about the digital twin topology and simulation metrics."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    system_prompt = f"""
    You are an expert IT Infrastructure and Cloud Architect for the InfraTwin system.
    Answer the user query based strictly on the current digital twin environment state.
    
    Current Digital Twin Context:
    {json.dumps(twin_context, indent=2)}
    """

    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
                contents=f"{system_prompt}\n\nUser: {prompt}"
            )
            if response and response.text:
                return response.text.strip()
        except Exception:
            pass

    if openrouter_key or groq_key or openai_key:
        try:
            from openai import OpenAI
            if openrouter_key:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
                model_name = "meta-llama/llama-3.1-8b-instruct"
            elif groq_key:
                client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
                model_name = "llama3-8b-8192"
            else:
                client = OpenAI(api_key=openai_key)
                model_name = "gpt-4o-mini"

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        except Exception:
            pass

    # Deterministic rule-based fallback
    prompt_lower = prompt.lower()
    env = twin_context.get("active_environment", "active")
    nodes = twin_context.get("total_nodes", 0)
    edges = twin_context.get("total_edges", 0)
    spofs = twin_context.get("spof_nodes", [])
    cost = twin_context.get("total_monthly_cost", 0.0)
    curr = twin_context.get("currency", "INR" if twin_context.get("is_manual") else "USD")
    curr_sym = "₹" if curr == "INR" else "$"

    if any(w in prompt_lower for w in ["spof", "single point", "failure", "bottleneck", "vulnerable"]):
        if spofs:
            spof_list = ", ".join(spofs) if isinstance(spofs, list) else str(spofs)
            return f"In environment '{env}', the identified Single Points of Failure (SPOFs) are: {spof_list}. A failure in any of these components would partition the graph and disrupt downstream services."
        return f"No articulation point SPOFs were identified in the current '{env}' topology."

    if any(w in prompt_lower for w in ["cost", "spend", "expense", "budget", "price"]):
        return f"The total estimated monthly infrastructure cost for environment '{env}' is {curr_sym}{cost:,.2f} across {nodes} provisioned resource(s)."

    if any(w in prompt_lower for w in ["size", "count", "how many", "components", "resources", "nodes"]):
        return f"Environment '{env}' currently models {nodes} infrastructure component(s) interconnected by {edges} dependency relationship(s)."

    return (
        f"Environment '{env}' currently comprises {nodes} resources, {edges} dependencies, "
        f"and an estimated monthly burn of {curr_sym}{cost:,.2f}. "
        f"{len(spofs)} Single Point(s) of Failure detected."
    )

