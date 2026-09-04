from sqlalchemy import Column, Integer, String, Enum, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
import enum
import uuid
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

class Environment(str, enum.Enum):
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

class Component(Base):
    __tablename__ = "components"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    type = Column(Enum(ComponentType))
    environment = Column(Enum(Environment))
    location = Column(String)
    criticality = Column(Enum(Criticality))
    owner = Column(String)
    status = Column(Enum(Status), default=Status.active)
    cpu = Column(Float, nullable=True)
    memory = Column(Float, nullable=True)
    cost_per_month = Column(Float, default=0.0)
    metadata_col = Column(JSON, default={})
    source_environment = Column(String, default="aws")

class ManualProject(Base):
    __tablename__ = "manual_projects"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    created_at = Column(String, default="2023-01-01T00:00:00Z") # simple string for simplicity or datetime

class Dependency(Base):
    __tablename__ = "dependencies"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey("components.id"))
    target_id = Column(String, ForeignKey("components.id"))
    relationship_type = Column(Enum(DependencyType))
    criticality = Column(Enum(Criticality))
    source_environment = Column(String, default="aws")
