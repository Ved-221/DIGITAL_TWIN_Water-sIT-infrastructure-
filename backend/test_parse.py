import re
import json

architect_recommendation = """```json
{ "explanation": "The proposed migration is expected to incur a significant cost of approximately $204.00 and poses a CRITICAL risk with 180 minutes estimated downtime, affecting 10 critical components across multiple environments.", "recommended_actions": [ { "action": "Implement a cloud-based auto-scaling service to dynamically adjust resources based on changing workloads, reducing the risk of sudden spikes in usage", "description": "Utilize a service such as AWS Auto Scaling or Azure Autoscale to ensure optimal resource utilization and minimize downtime" }, { "action": "Migrate ERP and Empower databases to a cloud-native database service, such as PostgreSQL on AWS RDS or Azure Database Services", "description": "Take advantage of cloud-native database services to improve scalability, reliability, and performance, and reduce the blast radius of potential issues" }, { "action": "Deploy a cloud-based load balancer in front of the Corporate WAN to distribute traffic and mitigate the impact of sudden spikes in usage", "description": "Utilize a service such as AWS Elastic Load Balancer or Azure Load Balancer to ensure consistent and reliable user experience" }, { "action": "Establish a separate, isolated environment for Reporting/Analytics to prevent cascading failures and minimize the blast radius", "description": "Create a separate, isolated environment for Reporting/Analytics to ensure business continuity and minimize the impact of potential issues" } ] }
```"""

try:
    json_match = re.search(r'\{.*\}', architect_recommendation, re.DOTALL)
    if json_match:
        cleaned_json = json_match.group(0)
    else:
        cleaned_json = architect_recommendation
    print(f"Cleaned JSON: {cleaned_json[:50]}...")
    parsed = json.loads(cleaned_json)
    print("Parsed successfully!")
    print("Explanation:", parsed.get("explanation"))
except Exception as e:
    print("Error:", repr(e))

