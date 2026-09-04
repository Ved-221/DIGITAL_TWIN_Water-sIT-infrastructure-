from sqlalchemy import Column, Integer, String, Enum, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
import enum
import uuid
from datetime import datetime, timezone
from database import Base

class ComponentType(str, enum.Enum):
    application = "application"
    server = "server"
    database = "database"
    network = "network"
    cloud_resource = "cloud_resource"
    storage = "storage"
    api = "api"
    identity = "identity"
    k8s_node = "k8s_node"
    k8s_pod = "k8s_pod"
    lambda_fn = "lambda"

class EnvironmentEnum(str, enum.Enum):
    on_prem = "on_prem"
    cloud = "cloud"
    kubernetes = "kubernetes"
    hybrid = "hybrid"

class Criticality(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class Status(str, enum.Enum):
    active = "active"
    degraded = "degraded"
    offline = "offline"

class DependencyType(str, enum.Enum):
    depends_on = "depends_on"
    connects_to = "connects_to"
    stores_in = "stores_in"
    authenticates_via = "authenticates_via"
    hosted_on = "hosted_on"
    calls = "calls"
    queries = "queries"
    replicates = "replicates"
    routes_to = "routes_to"

def get_utc_now():
    return datetime.now(timezone.utc).isoformat()

class Environment(Base):
    __tablename__ = "environments"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    type = Column(String, default="manual")
    region = Column(String, nullable=True, default="us-east-1")
    created_at = Column(String, default=get_utc_now)
    updated_at = Column(String, default=get_utc_now)

class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    type = Column(String, default="server")
    environment = Column(String, default="cloud")
    environment_id = Column(String, nullable=True)
    provider = Column(String, default="manual")
    region = Column(String, nullable=True)
    location = Column(String, default="us-east-1")
    criticality = Column(String, default="medium")
    owner = Column(String, default="Ops")
    status = Column(String, default="active")
    cpu = Column(Float, nullable=True)
    memory = Column(Float, nullable=True)
    cost_per_month = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    position_x = Column(Float, nullable=True, default=0.0)
    position_y = Column(Float, nullable=True, default=0.0)
    telemetry = Column(JSON, default={})
    metadata_col = Column(JSON, default={})
    source_environment = Column(String, default="aws")
    created_at = Column(String, default=get_utc_now)
    updated_at = Column(String, default=get_utc_now)

    def __init__(self, **kwargs):
        if "environment_id" in kwargs and "source_environment" not in kwargs:
            kwargs["source_environment"] = kwargs["environment_id"]
        elif "source_environment" in kwargs and "environment_id" not in kwargs:
            kwargs["environment_id"] = kwargs["source_environment"]
        if "location" in kwargs and "region" not in kwargs:
            kwargs["region"] = kwargs["location"]
        elif "region" in kwargs and "location" not in kwargs:
            kwargs["location"] = kwargs["region"]
        super().__init__(**kwargs)

    @property
    def metadata_info(self):
        if isinstance(self.metadata_col, dict):
            return self.metadata_col
        import json
        try:
            return json.loads(self.metadata_col) if self.metadata_col else {}
        except Exception:
            return {}

class ManualProject(Base):
    __tablename__ = "manual_projects"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    created_at = Column(String, default=get_utc_now)

class Dependency(Base):
    __tablename__ = "dependencies"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey("components.id"))
    target_id = Column(String, ForeignKey("components.id"))
    relationship_type = Column(String, default="depends_on")
    criticality = Column(String, default="medium")
    environment_id = Column(String, nullable=True)
    source_environment = Column(String, default="aws")
    metadata_col = Column(JSON, default={})
    created_at = Column(String, default=get_utc_now)

    def __init__(self, **kwargs):
        if "environment_id" in kwargs and "source_environment" not in kwargs:
            kwargs["source_environment"] = kwargs["environment_id"]
        elif "source_environment" in kwargs and "environment_id" not in kwargs:
            kwargs["environment_id"] = kwargs["source_environment"]
        super().__init__(**kwargs)

class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    environment_id = Column(String, nullable=True)
    source_environment = Column(String, default="aws")
    target_component_id = Column(String, nullable=True)
    action = Column(String, default="migrate")
    destination_env = Column(String, nullable=True)
    affected_components = Column(JSON, default=[])
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String, default="LOW")
    estimated_downtime_minutes = Column(Integer, default=0)
    cost_delta_monthly = Column(Float, default=0.0)
    status = Column(String, default="completed")
    result_status = Column(String, default="completed")
    created_at = Column(String, default=get_utc_now)

    def __init__(self, **kwargs):
        if "environment_id" in kwargs and "source_environment" not in kwargs:
            kwargs["source_environment"] = kwargs["environment_id"]
        elif "source_environment" in kwargs and "environment_id" not in kwargs:
            kwargs["environment_id"] = kwargs["source_environment"]
        if "component_id" in kwargs and "target_component_id" not in kwargs:
            kwargs["target_component_id"] = kwargs["component_id"]
        if "target_environment" in kwargs and "destination_env" not in kwargs:
            kwargs["destination_env"] = kwargs["target_environment"]
        if "result_status" in kwargs and "status" not in kwargs:
            kwargs["status"] = kwargs["result_status"]
        super().__init__(**kwargs)

    @property
    def component_id(self):
        return self.target_component_id

    @component_id.setter
    def component_id(self, val):
        self.target_component_id = val

    @property
    def target_environment(self):
        return self.destination_env

    @target_environment.setter
    def target_environment(self, val):
        self.destination_env = val

class SandboxSnapshot(Base):
    __tablename__ = "sandbox_snapshots"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    environment_id = Column(String, index=True)
    solution_id = Column(String, nullable=True)
    solution_name = Column(String, nullable=True)
    strategy_type = Column(String, nullable=True)
    state_json = Column(JSON, default=dict)
    status = Column(String, default="pending")
    created_at = Column(String, default=get_utc_now)

