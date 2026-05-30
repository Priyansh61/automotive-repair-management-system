"""
Vehicle Model - SQLAlchemy ORM
Customer vehicles, multi-tenant scoped
"""
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.models.base import BaseModelMixin, TenantScopedMixin

FUEL_TYPES = ['Petrol', 'Diesel', 'CNG', 'Electric', 'Hybrid']


class Vehicle(db.Model, BaseModelMixin, TenantScopedMixin):
    """Vehicle model — one customer can own many vehicles"""

    __tablename__ = 'vehicle'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'license_plate', name='uq_vehicle_tenant_plate'),
    )

    vehicle_id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey('tenant.tenant_id'), nullable=True, index=True
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('customer.customer_id'), nullable=False
    )
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False)
    vin: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    fuel_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="vehicles")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="vehicle_rel")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", backref="vehicles")

    @property
    def display_name(self) -> str:
        parts = []
        if self.year:
            parts.append(str(self.year))
        parts.append(self.make)
        parts.append(self.model)
        return f"{' '.join(parts)} — {self.license_plate}"

    @classmethod
    def get_for_customer(cls, customer_id: int) -> List['Vehicle']:
        """Get all vehicles for a customer, scoped to tenant"""
        query = db.select(cls).where(cls.customer_id == customer_id)
        tenant_id = cls._get_current_tenant_id()
        if tenant_id:
            query = query.where(cls.tenant_id == tenant_id)
        query = query.order_by(cls.make, cls.model)
        return list(db.session.execute(query).scalars())

    @classmethod
    def find_by_plate(cls, license_plate: str) -> Optional['Vehicle']:
        """Find vehicle by license plate, scoped to tenant"""
        query = db.select(cls).where(cls.license_plate == license_plate.upper().strip())
        tenant_id = cls._get_current_tenant_id()
        if tenant_id:
            query = query.where(cls.tenant_id == tenant_id)
        return db.session.execute(query).scalar_one_or_none()

    def validate(self) -> List[str]:
        errors = []
        if not self.make or not self.make.strip():
            errors.append("Vehicle make is required")
        if not self.model or not self.model.strip():
            errors.append("Vehicle model is required")
        if not self.license_plate or not self.license_plate.strip():
            errors.append("License plate is required")
        if self.year and (self.year < 1900 or self.year > 2100):
            errors.append("Invalid year")
        if self.fuel_type and self.fuel_type not in FUEL_TYPES:
            errors.append(f"Fuel type must be one of: {', '.join(FUEL_TYPES)}")
        return errors

    def to_dict(self) -> dict:
        data = super().to_dict()
        data['display_name'] = self.display_name
        return data

    def __str__(self) -> str:
        return self.display_name


from app.models.customer import Customer
from app.models.job import Job
