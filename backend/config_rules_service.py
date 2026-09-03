import boto3
import os
import json
from botocore.exceptions import ClientError
from typing import Dict, Any, List

def get_resource_compliance(component) -> Dict[str, Any]:
    """
    Fetches AWS Config rule compliance for a specific component.
    Expects component to have metadata_col containing raw_configuration with resource_type and resource_id.
    """
    if not component.id.startswith('aws_'):
        return {"status": "NOT_APPLICABLE", "rules": []}

    try:
        # metadata_col might be a string if JSON wasn't parsed properly in some places
        metadata = component.metadata_col
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
            
        if not isinstance(metadata, dict):
            return {"status": "UNKNOWN", "rules": []}
            
        resource_type = metadata.get('resource_type')
        resource_id = metadata.get('resource_id')
        
        # S3 buckets sometimes need special handling depending on how Config records them, 
        # but the raw_configuration usually has the right ID format for Config.
        if not resource_type or not resource_id:
             # Fallback if raw config is missing it but we can guess from component type
             if component.type == 'storage' and 's3' in component.id:
                 resource_type = 'AWS::S3::Bucket'
                 # e.g. aws_s3_bucket_config-bucket-881776924433
                 resource_id = component.id.split('_bucket_')[-1]
             else:
                 return {"status": "UNKNOWN", "rules": []}

        session = boto3.Session()
        region = os.environ.get("AWS_REGION") or session.region_name or "us-east-1"
        client = session.client('config', region_name=region)
        
        response = client.get_compliance_details_by_resource(
            ResourceType=resource_type,
            ResourceId=resource_id
        )
        
        evaluations = response.get('EvaluationResults', [])
        
        if not evaluations:
            return {"status": "NO_RULES_EVALUATED", "rules": []}
            
        rules = []
        is_compliant = True
        
        for eval_result in evaluations:
            compliance = eval_result.get('ComplianceType', 'UNKNOWN')
            rule_name = eval_result.get('EvaluationResultIdentifier', {}).get('EvaluationResultQualifier', {}).get('ConfigRuleName', 'Unknown Rule')
            
            if compliance == 'NON_COMPLIANT':
                is_compliant = False
                
            rules.append({
                "rule_name": rule_name,
                "compliance": compliance
            })
            
        return {
            "status": "COMPLIANT" if is_compliant else "NON_COMPLIANT",
            "rules": rules
        }

    except ClientError as e:
        print(f"CloudWatch Compliance ClientError for {component.id}: {e}")
        return {"status": "ERROR", "rules": []}
    except Exception as e:
        print(f"Unexpected Error fetching compliance for {component.id}: {e}")
        return {"status": "ERROR", "rules": []}

if __name__ == "__main__":
    # Test script if run directly
    class MockComp:
        id = "aws_s3_bucket_config-bucket-881776924433"
        type = "storage"
        metadata_col = {
            "resource_type": "AWS::S3::Bucket",
            "resource_id": "config-bucket-881776924433"
        }
    
    comp = MockComp()
    res = get_resource_compliance(comp)
    print(json.dumps(res, indent=2))
