import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import NoCredentialsError

import aws_mapper
from aws_collector import check_aws_status, get_aws_region
from cloudwatch_service import get_resource_health
from config_rules_service import get_resource_compliance

def test_aws_resource_normalization():
    """Verify raw AWS Config resource definitions are normalized into standard digital twin schemas."""
    # 1. EC2 Instance
    ec2_raw = {
        "resource_id": "i-0123456789abcdef0",
        "resource_type": "AWS::EC2::Instance",
        "name": "prod-api-worker-1",
        "region": "ap-south-1",
        "status": "running",
        "raw_configuration": {
            "InstanceType": "t3.large",
            "SubnetId": "subnet-0a1b2c3d",
            "VpcId": "vpc-0987654321"
        }
    }
    comp_ec2 = aws_mapper.resource_to_component(ec2_raw)
    assert comp_ec2["id"] == "aws_ec2_instance_i-0123456789abcdef0"
    assert comp_ec2["name"] == "prod-api-worker-1"
    assert comp_ec2["type"] == "server"
    assert comp_ec2["environment"] == "cloud"
    assert comp_ec2["location"] == "ap-south-1"
    assert comp_ec2["status"] == "active"
    
    # 2. RDS Database
    rds_raw = {
        "resource_id": "prod-postgres-cluster",
        "resource_type": "AWS::RDS::DBInstance",
        "name": "prod-postgres-cluster",
        "region": "ap-south-1",
        "status": "available",
        "raw_configuration": {
            "DBInstanceClass": "db.r6g.xlarge",
            "DBSubnetGroup": {"VpcId": "vpc-0987654321"}
        }
    }
    comp_rds = aws_mapper.resource_to_component(rds_raw)
    assert comp_rds["id"] == "aws_rds_dbinstance_prod-postgres-cluster"
    assert comp_rds["type"] == "database"
    assert comp_rds["status"] == "active"
    
    # 3. VPC
    vpc_raw = {
        "resource_id": "vpc-0987654321",
        "resource_type": "AWS::EC2::VPC",
        "name": "prod-mumbai-vpc",
        "region": "ap-south-1",
        "status": "available",
        "raw_configuration": {"CidrBlock": "10.0.0.0/16"}
    }
    comp_vpc = aws_mapper.resource_to_component(vpc_raw)
    assert comp_vpc["type"] == "network"
    assert comp_vpc["environment"] == "cloud"

def test_aws_topology_dependency_extraction():
    """Verify network and infrastructure relationships are extracted correctly."""
    resources = [
        {
            "resource_id": "vpc-100",
            "resource_type": "AWS::EC2::VPC",
            "name": "Main-VPC",
            "raw_configuration": {}
        },
        {
            "resource_id": "subnet-200",
            "resource_type": "AWS::EC2::Subnet",
            "name": "Private-Subnet-1A",
            "raw_configuration": {
                "VpcId": "vpc-100"
            }
        },
        {
            "resource_id": "i-300",
            "resource_type": "AWS::EC2::Instance",
            "name": "App-Server",
            "raw_configuration": {
                "VpcId": "vpc-100",
                "SubnetId": "subnet-200"
            }
        }
    ]
    
    deps = aws_mapper.extract_dependencies(resources)
    assert len(deps) >= 2
    
    # Check Subnet -> VPC dependency
    subnet_id = "aws_ec2_subnet_subnet-200"
    vpc_id = "aws_ec2_vpc_vpc-100"
    ec2_id = "aws_ec2_instance_i-300"
    
    subnet_vpc_dep = next((d for d in deps if d["source_id"] == subnet_id and d["target_id"] == vpc_id), None)
    assert subnet_vpc_dep is not None
    assert subnet_vpc_dep["relationship_type"] in ["contained_in", "depends_on"]
    
    # Check EC2 -> Subnet dependency
    ec2_subnet_dep = next((d for d in deps if d["source_id"] == ec2_id and d["target_id"] == subnet_id), None)
    assert ec2_subnet_dep is not None
    assert ec2_subnet_dep["relationship_type"] in ["hosted_in", "connects_to"]

def test_aws_status_graceful_handling_without_credentials():
    """Verify check_aws_status returns clean no_credentials or error status rather than throwing uncaught exceptions."""
    with patch("boto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_client.describe_configuration_recorder_status.side_effect = NoCredentialsError()
        mock_session.client.return_value = mock_client
        mock_session_cls.return_value = mock_session
        
        status = check_aws_status(region="ap-south-1")
        assert status["status"] in ["no_credentials", "error"]
        assert status["config_recording"] is False

def test_cloudwatch_and_config_rules_services():
    """Verify CloudWatch and Config Rules collectors return fallback or structured outputs gracefully."""
    mock_comp = MagicMock()
    mock_comp.id = "aws_ec2_instance_i-0123456789"
    mock_comp.type = "server"
    mock_comp.location = "us-east-1"
    mock_comp.metadata_col = {"instanceId": "i-0123456789", "resource_type": "AWS::EC2::Instance", "resource_id": "i-0123456789"}
    
    # Test CloudWatch service without active AWS credentials
    cw_metrics = get_resource_health(mock_comp)
    assert "metrics" in cw_metrics
    assert "alarms" in cw_metrics
    
    # Test Config Rules service without active AWS credentials
    compliance = get_resource_compliance(mock_comp)
    assert "status" in compliance
    assert "rules" in compliance
