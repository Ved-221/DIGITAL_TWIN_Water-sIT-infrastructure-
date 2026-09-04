from sqlalchemy import Column, Integer, String, Enum, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship, synonym
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
    load_balancer = "load_balancer"
    subnet = "subnet"
    vpc = "vpc"
    security_group = "security_group"
    gateway = "gateway"
    lambda_ = "lambda"

class EnvironmentEnum(str, enum.Enum):
    on_prem = "on_prem"
    cloud = "cloud"
    kubernetes = "kubernetes"
    hybrid = "hybrid"

Environment = EnvironmentEnum

def get_utc_now():
    return datetime.now(timezone.utc).isoformat()

class Criticality(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class Status(str, enum.Enum):
    active = "active"
    degraded = "degraded"
    offline = "offline"

from sqlalchemy.orm import reconstructor

class DependencyType(str, enum.Enum):
    depends_on = "depends_on"
    connects_to = "connects_to"
    stores_in = "stores_in"
    authenticates_via = "authenticates_via"
    hosted_on = "hosted_on"
    routes_to = "routes_to"
    # Phase 2: Normalized infrastructure relationships
    database_connection = "database_connection"
    routes_traffic_to = "routes_traffic_to"
    storage_access = "storage_access"
    enclosed_in_subnet = "enclosed_in_subnet"
    protected_by_security_group = "protected_by_security_group"
    member_of_vpc = "member_of_vpc"
    authorizes_traffic_from = "authorizes_traffic_from"

class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    type = Column(Enum(ComponentType), default=ComponentType.server)
    environment = Column(Enum(Environment), default=Environment.cloud)
    location = Column(String, default="ap-south-1")
    criticality = Column(Enum(Criticality), default=Criticality.medium)
    owner = Column(String)
    status = Column(Enum(Status), default=Status.active)
    cpu = Column(Float, nullable=True)
    memory = Column(Float, nullable=True)
    cost_per_month = Column(Float, default=0.0)
    arn = Column(String, nullable=True, index=True)
    aws_region = Column(String, nullable=True)
    discovery_source = Column(String, default="manual", index=True)
    account_id = Column(String, nullable=True)
    availability_zone = Column(String, nullable=True)
    updated_at = Column(String, nullable=True)
    metadata_col = Column(JSON, default={})
    source_environment = Column(String, default="aws")
    domain = Column(String, default="general", nullable=True)
    properties = Column(JSON, default={}, nullable=True)
    created_at = Column(String, default=get_utc_now)
    updated_at = Column(String, default=get_utc_now)

    environment_id = synonym("source_environment")

    def __init__(self, **kwargs):
        if kwargs.get("environment") is None:
            kwargs["environment"] = Environment.cloud
        if kwargs.get("criticality") is None:
            kwargs["criticality"] = Criticality.medium
        if kwargs.get("type") is None:
            kwargs["type"] = ComponentType.server
        if "environment_id" in kwargs:
            env_val = kwargs.pop("environment_id")
            if "source_environment" not in kwargs:
                kwargs["source_environment"] = env_val
        if "region" in kwargs:
            reg_val = kwargs.pop("region")
            if "location" not in kwargs:
                kwargs["location"] = reg_val
            if "aws_region" not in kwargs:
                kwargs["aws_region"] = reg_val

        provider_val = kwargs.pop("provider", None)
        currency_val = kwargs.pop("currency", None)
        pos_x = kwargs.pop("position_x", None)
        pos_y = kwargs.pop("position_y", None)
        telemetry_val = kwargs.pop("telemetry", None)

        meta = kwargs.get("metadata_col") or {}
        if not isinstance(meta, dict):
            meta = {}
        if provider_val:
            meta["provider"] = provider_val
        if currency_val:
            meta["currency"] = currency_val
        if pos_x is not None:
            meta["position_x"] = pos_x
        if pos_y is not None:
            meta["position_y"] = pos_y
        kwargs["metadata_col"] = meta

        props = kwargs.get("properties") or {}
        if not isinstance(props, dict):
            props = {}
        if telemetry_val:
            props["telemetry"] = telemetry_val
        kwargs["properties"] = props

        super().__init__(**kwargs)

    @property
    def provider(self):
        return self.metadata_col.get("provider", "aws") if isinstance(self.metadata_col, dict) else "aws"

    @provider.setter
    def provider(self, val):
        meta = dict(self.metadata_col or {})
        meta["provider"] = val
        self.metadata_col = meta

    @property
    def region(self):
        return self.aws_region or self.location or "us-east-1"

    @region.setter
    def region(self, val):
        self.aws_region = val
        self.location = val

    @property
    def currency(self):
        return self.metadata_col.get("currency", "USD") if isinstance(self.metadata_col, dict) else "USD"

    @currency.setter
    def currency(self, val):
        meta = dict(self.metadata_col or {})
        meta["currency"] = val
        self.metadata_col = meta

    @property
    def position_x(self):
        return self.metadata_col.get("position_x", 100) if isinstance(self.metadata_col, dict) else 100

    @position_x.setter
    def position_x(self, val):
        meta = dict(self.metadata_col or {})
        meta["position_x"] = val
        self.metadata_col = meta

    @property
    def position_y(self):
        return self.metadata_col.get("position_y", 100) if isinstance(self.metadata_col, dict) else 100

    @position_y.setter
    def position_y(self, val):
        meta = dict(self.metadata_col or {})
        meta["position_y"] = val
        self.metadata_col = meta

    @property
    def telemetry(self):
        return self.properties.get("telemetry", {}) if isinstance(self.properties, dict) else {}

    @telemetry.setter
    def telemetry(self, val):
        props = dict(self.properties or {})
        props["telemetry"] = val
        self.properties = props

    @property
    def source(self):
        return self.discovery_source or "manual"

    @property
    def source_id(self):
        return self.arn or self.id

    @property
    def last_updated(self):
        return self.updated_at

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
    source_component_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    target_component_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    source_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    target_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    relationship_type = Column(String, index=True)
    criticality = Column(Enum(Criticality), default=Criticality.medium)
    source = Column(String, default="aws_api")
    discovery_source = Column(String, default="aws_api")
    source_environment = synonym("source")
    environment_id = synonym("source")
    metadata_col = Column("metadata", JSON, default={})

    def __init__(self, **kwargs):
        src = kwargs.get("source_component_id") or kwargs.get("source_id")
        kwargs["source_component_id"] = src
        kwargs["source_id"] = src
        
        tgt = kwargs.get("target_component_id") or kwargs.get("target_id")
        kwargs["target_component_id"] = tgt
        kwargs["target_id"] = tgt

        if "environment_id" in kwargs:
            env_val = kwargs.pop("environment_id")
            if "source_environment" not in kwargs:
                kwargs["source_environment"] = env_val
        s = kwargs.get("source_environment") or kwargs.get("source") or kwargs.get("discovery_source") or "manual"
        kwargs["source"] = s
        kwargs["discovery_source"] = s

        meta = kwargs.get("metadata_col") if "metadata_col" in kwargs else kwargs.get("metadata", {})
        kwargs["metadata_col"] = meta

        rel = kwargs.get("relationship_type")
        if hasattr(rel, "value"):
            kwargs["relationship_type"] = rel.value
        elif rel is not None:
            kwargs["relationship_type"] = str(rel)

        super().__init__(**kwargs)

    @reconstructor
    def init_on_load(self):
        if not self.source_component_id and self.source_id:
            self.source_component_id = self.source_id
        elif not self.source_id and self.source_component_id:
            self.source_id = self.source_component_id

        if not self.target_component_id and self.target_id:
            self.target_component_id = self.target_id
        elif not self.target_id and self.target_component_id:
            self.target_id = self.target_component_id

        if not self.source and self.discovery_source:
            self.source = self.discovery_source
        elif not self.discovery_source and self.source:
            self.discovery_source = self.source


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    resource_id = Column(String, ForeignKey("components.id"), index=True, nullable=False)
    timestamp = Column(String, index=True, nullable=False)
    resource_type = Column(String, index=True)
    cpu = Column(Float, nullable=True)
    memory = Column(Float, nullable=True)
    disk = Column(JSON, nullable=True)
    network = Column(JSON, nullable=True)
    latency = Column(Float, nullable=True)
    error_rate = Column(Float, nullable=True)
    request_rate = Column(Float, nullable=True)
    connections = Column(Float, nullable=True)
    status = Column(String, default="active")
    age_days = Column(Float, nullable=True)
    raw_metrics = Column(JSON, default={})


class TwinState(Base):
    __tablename__ = "twin_state"

    id = Column(Integer, primary_key=True, default=1)
    mode = Column(String, default="unconnected") # "unconnected", "live", "demo"
    account_id = Column(String, nullable=True)
    arn = Column(String, nullable=True)
    region = Column(String, nullable=True)
    discovery_status = Column(String, default="idle") # "idle", "discovering", "completed", "empty", "failed"
    discovery_summary = Column(JSON, default={})
    last_sync = Column(String, nullable=True)
    error = Column(String, nullable=True)

class Environment(Base):
    __tablename__ = "environments"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    provider = Column(String, default="aws")
    source_type = Column(String, default="aws")
    is_active = Column(Boolean, default=True)
    status = Column(String, default="connected")
    created_at = Column(String, default=get_utc_now)

    type = synonym("source_type")

    # Enum compatibility
    on_prem = EnvironmentEnum.on_prem
    cloud = EnvironmentEnum.cloud
    kubernetes = EnvironmentEnum.kubernetes
    hybrid = EnvironmentEnum.hybrid

    def __init__(self, **kwargs):
        if "type" in kwargs and "source_type" not in kwargs:
            kwargs["source_type"] = kwargs.pop("type")
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


