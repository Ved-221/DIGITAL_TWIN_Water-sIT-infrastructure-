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
    load_balancer = "load_balancer"
    subnet = "subnet"
    vpc = "vpc"
    security_group = "security_group"

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
    type = Column(Enum(ComponentType))
    environment = Column(Enum(Environment))
    location = Column(String, default="ap-south-1")
    criticality = Column(Enum(Criticality))
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
    source_component_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    target_component_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    source_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    target_id = Column(String, ForeignKey("components.id"), nullable=True, index=True)
    relationship_type = Column(String, index=True)
    criticality = Column(Enum(Criticality), default=Criticality.medium)
    source = Column(String, default="aws_api")
    discovery_source = Column(String, default="aws_api")
    metadata_col = Column("metadata", JSON, default={})

    def __init__(self, **kwargs):
        src = kwargs.get("source_component_id") or kwargs.get("source_id")
        kwargs["source_component_id"] = src
        kwargs["source_id"] = src
        
        tgt = kwargs.get("target_component_id") or kwargs.get("target_id")
        kwargs["target_component_id"] = tgt
        kwargs["target_id"] = tgt

        s = kwargs.get("source") or kwargs.get("discovery_source") or "manual"
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

