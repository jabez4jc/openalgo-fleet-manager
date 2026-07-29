from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class FleetUser(Base):
    __tablename__ = "fleet_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(512), nullable=False)
    must_change_password = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Server(Base):
    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    base_url = Column(String(512), nullable=False)
    ssh_host = Column(String(256), nullable=True)
    ssh_port = Column(Integer, default=22, server_default="22")
    ssh_user = Column(String(128), nullable=True)
    ssh_key_encrypted = Column(Text, nullable=True)
    ssh_host_key = Column(Text, nullable=True)
    admin_username = Column(String(128), nullable=True)
    admin_password_encrypted = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    instances = relationship("Instance", back_populates="server", cascade="all, delete-orphan", lazy="selectin")
    provisioning_jobs = relationship("ProvisioningJob", back_populates="server", cascade="all, delete-orphan", lazy="selectin")


class Instance(Base):
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    instance_name = Column(String(256), nullable=False)
    domain = Column(String(512), nullable=True)
    broker = Column(String(128), nullable=True)
    flask_port = Column(String(16), nullable=True)
    status = Column(String(64), nullable=True)
    health_status = Column(String(64), nullable=True)
    env_version = Column(String(64), nullable=True)
    last_polled_at = Column(DateTime(timezone=True), nullable=True)
    raw_json = Column(Text, nullable=True)

    server = relationship("Server", back_populates="instances")


class ProvisioningJob(Base):
    __tablename__ = "provisioning_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="SET NULL"), nullable=True)
    job_type = Column(String(64), nullable=False)
    params_json = Column(Text, nullable=True)
    status = Column(String(32), default="queued", server_default="queued")
    log_text = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    triggered_by = Column(String(128), nullable=True)

    server = relationship("Server", back_populates="provisioning_jobs")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(128), nullable=True)
    action = Column(String(256), nullable=False)
    server_id = Column(Integer, nullable=True)
    instance_name = Column(String(256), nullable=True)
    detail_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
