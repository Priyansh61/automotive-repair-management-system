"""
Vehicle Service
Business logic for vehicle management
"""
from typing import List, Optional, Tuple
import logging
from app.extensions import db
from app.models.vehicle import Vehicle, FUEL_TYPES
from app.utils.validators import sanitize_input


class VehicleService:

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_vehicles_for_customer(self, customer_id: int) -> List[dict]:
        """Return all vehicles for a customer as dicts"""
        try:
            vehicles = Vehicle.get_for_customer(customer_id)
            return [v.to_dict() for v in vehicles]
        except Exception as e:
            self.logger.error(f"Failed to get vehicles for customer {customer_id}: {e}")
            return []

    def create_vehicle(
        self,
        customer_id: int,
        make: str,
        model: str,
        license_plate: str,
        year: Optional[int] = None,
        vin: Optional[str] = None,
        color: Optional[str] = None,
        fuel_type: Optional[str] = None,
        tenant_id: Optional[int] = None,
    ) -> Tuple[bool, List[str], Optional[Vehicle]]:
        """Create a new vehicle, returns (success, errors, vehicle)"""
        try:
            plate = license_plate.upper().strip()

            existing = Vehicle.find_by_plate(plate)
            if existing:
                return False, [f"License plate {plate} is already registered"], None

            vehicle = Vehicle(
                customer_id=customer_id,
                make=sanitize_input(make),
                model=sanitize_input(model),
                license_plate=plate,
                year=year,
                vin=sanitize_input(vin) if vin else None,
                color=sanitize_input(color) if color else None,
                fuel_type=fuel_type if fuel_type in FUEL_TYPES else None,
                tenant_id=tenant_id,
            )

            errors = vehicle.validate()
            if errors:
                return False, errors, None

            vehicle.save()
            self.logger.info(f"Created vehicle {plate} for customer {customer_id}")
            return True, [], vehicle

        except Exception as e:
            self.logger.error(f"Failed to create vehicle: {e}")
            db.session.rollback()
            return False, ["System error, please try again"], None
