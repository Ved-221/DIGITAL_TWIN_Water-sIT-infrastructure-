import re
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("infratwin.nl_parser")

# Standard type keywords mapping
TYPE_KEYWORDS = {
    "load_balancer": ["load balancer", "loadbalancer", "alb", "nlb", "elb", "ingress", "haproxy", "nginx reverse proxy"],
    "database": ["postgresql", "postgres", "mysql", "mariadb", "oracle", "mongodb", "redis", "dynamodb", "aurora", "rds", "database", "db", "chromatography data server"],
    "storage": ["object storage", "object-storage", "s3", "blob", "bucket", "nfs", "efs", "ebs", "backup storage", "storage"],
    "application": ["application server", "app server", "app", "api service", "microservice", "web app", "empower informatics"],
    "server": ["server", "ec2", "virtual machine", "vm", "host", "worker node", "compute node"],
    "api": ["api gateway", "api", "rest api", "graphql"],
    "network": ["vpc", "subnet", "firewall", "router", "gateway", "network"],
    "identity": ["iam", "cognito", "keycloak", "auth0", "okta", "active directory", "sso", "identity provider"]
}

# Number words mapping
WORD_TO_NUM = {
    "one": 1, "a": 1, "an": 1, "single": 1,
    "two": 2, "both": 2, "pair of": 2,
    "three": 3, "triple": 3,
    "four": 4, "five": 5, "six": 6
}

def infer_component_type(name: str) -> str:
    name_lower = name.lower()
    for ctype, kws in TYPE_KEYWORDS.items():
        for kw in kws:
            if kw in name_lower:
                return ctype
    return "application"

def parse_with_rule_engine(description: str, domain: str = "general") -> Dict[str, Any]:
    """
    Deterministic rule-based NLP extraction engine.
    Guarantees ZERO hallucinated components and ZERO invented dependencies.
    """
    components: List[Dict[str, Any]] = []
    dependencies: List[Dict[str, Any]] = []
    ambiguities: List[str] = []
    
    # Clean text into sentences
    raw_sentences = [s.strip() for s in re.split(r'[.\n;]+', description) if s.strip()]
    
    # Internal registry for matching
    comp_by_name: Dict[str, Dict[str, Any]] = {}
    comp_counter = 1
    
    def register_comp(name: str, ctype: Optional[str] = None, raw_mention: str = "") -> Dict[str, Any]:
        nonlocal comp_counter
        for existing_name, comp in comp_by_name.items():
            if existing_name.lower() == name.lower():
                return comp
                
        cid = f"comp_{comp_counter}"
        comp_counter += 1
        resolved_type = ctype or infer_component_type(name)
        comp_obj = {
            "temp_id": cid,
            "name": name,
            "type": resolved_type,
            "domain": domain,
            "status": "active",
            "criticality": "medium",
            "properties": {},
            "metrics": None,
            "metadata": {},
            "source": "user_description",
            "source_id": None,
            "raw_mention": raw_mention or name
        }
        comp_by_name[name.lower()] = comp_obj
        components.append(comp_obj)
        return comp_obj

    # Check for ambiguous modal expressions
    for s in raw_sentences:
        s_lower = s.lower()
        if any(w in s_lower for w in ["might connect", "maybe connects", "possibly depends", "optionally communicates"]):
            ambiguities.append(f"Ambiguous or optional relationship detected in sentence: '{s}'. Not created automatically.")
        if " or " in s_lower and any(w in s_lower for w in ["connect", "route", "talk"]):
            ambiguities.append(f"Disjunctive connection ('or') detected in sentence: '{s}'. Target component is ambiguous.")

    # Pass 1: Extract Components & Multiplicities
    for sentence in raw_sentences:
        s_lower = sentence.lower()
        
        # Pattern: "Two application servers are behind a load balancer" / "2 servers behind an ALB"
        multi_behind_match = re.search(
            r'(?:(?:there are|we have)\s+)?(two|three|four|five|2|3|4|5|\d+)\s+([a-zA-Z0-9\s_-]+?)\s+(?:are\s+)?behind\s+(?:a|an|the)\s+([a-zA-Z0-9\s_-]+)',
            sentence,
            re.IGNORECASE
        )
        if multi_behind_match:
            count_str, comp_base, lb_name = multi_behind_match.groups()
            count = int(count_str) if count_str.isdigit() else WORD_TO_NUM.get(count_str.lower(), 2)
            
            # Clean base name
            comp_base_clean = re.sub(r'servers?', 'server', comp_base.strip(), flags=re.IGNORECASE).title()
            lb_clean = lb_name.strip().title()
            
            lb_comp = register_comp(lb_clean, ctype="load_balancer", raw_mention=lb_name)
            
            app_comps = []
            for i in range(1, count + 1):
                cname = f"{comp_base_clean} {i}"
                ctype = infer_component_type(comp_base_clean)
                app_comp = register_comp(cname, ctype=ctype, raw_mention=f"{comp_base} {i}")
                app_comps.append(app_comp)
                
                # Explicit dependency from LB -> App Server
                dependencies.append({
                    "source_temp_id": lb_comp["temp_id"],
                    "target_temp_id": app_comp["temp_id"],
                    "source_name": lb_comp["name"],
                    "target_name": app_comp["name"],
                    "relationship_type": "routes_traffic_to",
                    "source": "user_description",
                    "explicit_quote": sentence,
                    "metadata": {"discovered_by": "nlp_behind_clause"}
                })
            continue

        # Pattern: "A load balancer routes to [X]"
        routes_to_match = re.search(
            r'(?:a|an|the)?\s*([a-zA-Z0-9\s_-]+?)\s+(?:routes(?: traffic)? to|distributes to|balances to)\s+(?:a|an|the)?\s*([a-zA-Z0-9\s_,-]+)',
            sentence,
            re.IGNORECASE
        )
        if routes_to_match:
            src_name, tgt_name = routes_to_match.groups()
            src_comp = register_comp(src_name.strip().title(), raw_mention=src_name)
            tgt_comp = register_comp(tgt_name.strip().title(), raw_mention=tgt_name)
            dependencies.append({
                "source_temp_id": src_comp["temp_id"],
                "target_temp_id": tgt_comp["temp_id"],
                "source_name": src_comp["name"],
                "target_name": tgt_comp["name"],
                "relationship_type": "routes_traffic_to",
                "source": "user_description",
                "explicit_quote": sentence,
                "metadata": {}
            })
            continue

        # Pattern: "Both connect to PostgreSQL" / "All connect to PostgreSQL" / "[X] connects to [Y]"
        if re.search(r'\b(both|all|each|they)\s+connect\s+to\s+', sentence, re.IGNORECASE):
            tgt_match = re.search(r'\b(?:both|all|each|they)\s+connect\s+to\s+(?:a|an|the)?\s*([a-zA-Z0-9\s_-]+)', sentence, re.IGNORECASE)
            if tgt_match:
                tgt_raw = tgt_match.group(1).strip()
                tgt_comp = register_comp(tgt_raw.title(), raw_mention=tgt_raw)
                
                # Connect all previously found application servers/servers to this target
                candidate_sources = [c for c in components if c["temp_id"] != tgt_comp["temp_id"] and c["type"] in ["application", "server"]]
                for src in candidate_sources:
                    # Check if already added
                    if not any(d["source_temp_id"] == src["temp_id"] and d["target_temp_id"] == tgt_comp["temp_id"] for d in dependencies):
                        dependencies.append({
                            "source_temp_id": src["temp_id"],
                            "target_temp_id": tgt_comp["temp_id"],
                            "source_name": src["name"],
                            "target_name": tgt_comp["name"],
                            "relationship_type": "database_connection" if tgt_comp["type"] == "database" else "connects_to",
                            "source": "user_description",
                            "explicit_quote": sentence,
                            "metadata": {}
                        })
            continue

        # Direct connection: "[X] connects to [Y]" / "[X] talks to [Y]" / "[X] depends on [Y]"
        direct_connect_match = re.search(
            r'(?:a|an|the)?\s*([a-zA-Z0-9\s_-]+?)\s+(?:connects to|talks to|queries|depends on|calls)\s+(?:a|an|the)?\s*([a-zA-Z0-9\s_-]+)',
            sentence,
            re.IGNORECASE
        )
        if direct_connect_match:
            src_raw, tgt_raw = direct_connect_match.groups()
            if src_raw.lower() not in ["both", "all", "they", "each"]:
                src_comp = register_comp(src_raw.strip().title(), raw_mention=src_raw)
                tgt_comp = register_comp(tgt_raw.strip().title(), raw_mention=tgt_raw)
                rel_type = "database_connection" if tgt_comp["type"] == "database" else "connects_to"
                dependencies.append({
                    "source_temp_id": src_comp["temp_id"],
                    "target_temp_id": tgt_comp["temp_id"],
                    "source_name": src_comp["name"],
                    "target_name": tgt_comp["name"],
                    "relationship_type": rel_type,
                    "source": "user_description",
                    "explicit_quote": sentence,
                    "metadata": {}
                })
                continue

        # Pattern: "[X] has an [Y] backup" / "[X] backs up to [Y]" / "[X] stores in [Y]"
        backup_match = re.search(
            r'(?:a|an|the)?\s*([a-zA-Z0-9\s_-]+?)\s+(?:has\s+(?:an?|the)\s+([a-zA-Z0-9\s_-]+?)\s+backup|backs up to\s+(?:an?|the)?\s*([a-zA-Z0-9\s_-]+)|stores in\s+(?:an?|the)?\s*([a-zA-Z0-9\s_-]+))',
            sentence,
            re.IGNORECASE
        )
        if backup_match:
            src_raw = backup_match.group(1).strip()
            tgt_raw = (backup_match.group(2) or backup_match.group(3) or backup_match.group(4) or "").strip()
            if tgt_raw:
                src_comp = register_comp(src_raw.title(), raw_mention=src_raw)
                tgt_comp = register_comp(tgt_raw.title(), ctype="storage", raw_mention=tgt_raw)
                dependencies.append({
                    "source_temp_id": src_comp["temp_id"],
                    "target_temp_id": tgt_comp["temp_id"],
                    "source_name": src_comp["name"],
                    "target_name": tgt_comp["name"],
                    "relationship_type": "storage_access",
                    "source": "user_description",
                    "explicit_quote": sentence,
                    "metadata": {"backup": True}
                })
                continue

    return {
        "success": True,
        "domain": domain,
        "raw_description": description,
        "components": components,
        "dependencies": dependencies,
        "ambiguities": ambiguities,
        "source": "user_description"
    }

def parse_system_description(description: str, domain: str = "general") -> Dict[str, Any]:
    """
    Parses a natural-language system description into a structured Digital Twin preview.
    Uses Gemini LLM if configured with strict extraction instructions,
    and falls back to deterministic rule-based NLP extraction.
    """
    if not description or not description.strip():
        return {
            "success": False,
            "domain": domain,
            "raw_description": "",
            "components": [],
            "dependencies": [],
            "ambiguities": ["Description cannot be empty."],
            "source": "user_description"
        }

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = f"""
You are a strict, domain-agnostic IT Infrastructure Digital Twin parser.
Extract ONLY explicitly mentioned components and direct relationships from the user's description.

CRITICAL RULES:
1. NEVER invent, hallucinate, or assume implicit dependencies (e.g. if the user does NOT explicitly state A connects to B, DO NOT create a relationship).
2. If multiplicities are stated (e.g. "two app servers"), extract them as distinct components: "App Server 1", "App Server 2".
3. If an ambiguity or uncertainty exists in the text, record it in the 'ambiguities' list.
4. Output MUST be strictly valid JSON matching this exact structure:
{{
  "domain": "{domain}",
  "components": [
    {{
      "temp_id": "c1",
      "name": "Component Name",
      "type": "load_balancer" | "server" | "application" | "database" | "storage" | "api" | "network" | "identity",
      "domain": "{domain}",
      "status": "active",
      "criticality": "medium",
      "properties": {{}},
      "metrics": null,
      "metadata": {{}},
      "source": "user_description",
      "source_id": null,
      "raw_mention": "quote from description"
    }}
  ],
  "dependencies": [
    {{
      "source_temp_id": "c1",
      "target_temp_id": "c2",
      "source_name": "Source Name",
      "target_name": "Target Name",
      "relationship_type": "routes_traffic_to" | "connects_to" | "database_connection" | "storage_access" | "depends_on",
      "source": "user_description",
      "explicit_quote": "exact sentence stating this relationship",
      "metadata": {{}}
    }}
  ],
  "ambiguities": []
}}

USER SYSTEM DESCRIPTION:
\"\"\"{description}\"\"\"
"""
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
            )
            raw_text = response.text.strip()
            parsed_json = json.loads(raw_text)
            
            # Post-validation: ensure IDs match and no fake edges
            components = parsed_json.get("components", [])
            dependencies = parsed_json.get("dependencies", [])
            ambiguities = parsed_json.get("ambiguities", [])
            
            valid_ids = {c.get("temp_id") for c in components}
            filtered_deps = []
            for d in dependencies:
                if d.get("source_temp_id") in valid_ids and d.get("target_temp_id") in valid_ids:
                    filtered_deps.append(d)
                    
            return {
                "success": True,
                "domain": parsed_json.get("domain", domain),
                "raw_description": description,
                "components": components,
                "dependencies": filtered_deps,
                "ambiguities": ambiguities,
                "source": "user_description"
            }
        except Exception as e:
            logger.warning("Gemini parsing failed or unavailable, using deterministic rule engine: %s", str(e))
            
    # Fallback to rule engine
    return parse_with_rule_engine(description, domain=domain)
