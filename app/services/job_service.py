"""
Job Service
Business logic for work order operations using SQLAlchemy ORM
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from decimal import Decimal, InvalidOperation
import logging
from flask import g
from app.extensions import db
from app.models.job import Job
from app.models.service import Service
from app.models.part import Part


class JobService:
    """Job service class"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _current_tenant_id():
        """Get current tenant ID from Flask g context"""
        return getattr(g, 'current_tenant_id', None)

    def get_current_jobs(
        self,
        page: int = 1,
        per_page: int = 10,
        tab: str = 'current',
    ) -> Tuple[List[Job], int, int]:
        """Get jobs filtered by list-page tab with pagination."""
        try:
            jobs, total = Job.get_current_jobs(page, per_page, tab=tab)
            total_pages = (total + per_page - 1) // per_page
            return jobs, total, total_pages

        except Exception as e:
            self.logger.error(f"Failed to get current jobs: {e}")
            raise

    def get_tab_counts(self) -> Dict[str, int]:
        """Counts per jobs-list tab for badges."""
        try:
            return Job.get_tab_counts()
        except Exception as e:
            self.logger.error(f"Failed to get tab counts: {e}")
            return {'current': 0, 'estimates': 0, 'completed': 0}

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Get job by ID"""
        try:
            return Job.find_by_id(job_id)
        except Exception as e:
            self.logger.error(f"Failed to get job (ID: {job_id}): {e}")
            raise

    def get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Get detailed job information"""
        try:
            from sqlalchemy.orm import joinedload
            job = db.session.execute(
                db.select(Job)
                .options(
                    joinedload(Job.customer_rel),
                    joinedload(Job.vehicle_rel),
                    joinedload(Job.complaints),
                )
                .where(Job.job_id == job_id)
            ).unique().scalar_one_or_none()

            if not job:
                return {}

            all_services = Service.get_all_sorted()
            all_parts = Part.get_all_sorted()

            return {
                'job_info': job.to_dict(),
                'services': job.get_services(),
                'parts': job.get_parts(),
                'complaints': job.get_complaints(),
                'all_services': [s.to_dict() for s in all_services],
                'all_parts': [p.to_dict() for p in all_parts],
                'job_completed': job.completed
            }

        except Exception as e:
            self.logger.error(f"Failed to get job details (ID: {job_id}): {e}")
            return {}

    def add_service_to_job(self, job_id: int, service_id: int, quantity: int) -> Tuple[bool, List[str]]:
        """
        Add service to job

        Args:
            job_id: Job ID
            service_id: Service ID
            quantity: Quantity

        Returns:
            (success, error_messages)
        """
        try:
            if quantity <= 0:
                return False, ["Quantity must be greater than 0"]

            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]

            if job.completed:
                return False, ["Cannot modify a completed job"]

            service = Service.find_by_id(service_id)
            if not service:
                return False, ["Service does not exist"]

            job.add_service(service_id, quantity)
            self.logger.info(f"Added service {service.service_name} to job {job_id}")
            return True, []

        except ValueError as e:
            return False, [str(e)]
        except Exception as e:
            self.logger.error(f"Failed to add service: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]

    def add_part_to_job(self, job_id: int, part_id: int, quantity: int) -> Tuple[bool, List[str]]:
        """
        Add part to job

        Args:
            job_id: Job ID
            part_id: Part ID
            quantity: Quantity

        Returns:
            (success, error_messages)
        """
        try:
            if quantity <= 0:
                return False, ["Quantity must be greater than 0"]

            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]

            if job.completed:
                return False, ["Cannot modify a completed job"]

            part = Part.find_by_id(part_id)
            if not part:
                return False, ["Part does not exist"]

            job.add_part(part_id, quantity)
            self.logger.info(f"Added part {part.part_name} to job {job_id}")
            return True, []

        except ValueError as e:
            return False, [str(e)]
        except Exception as e:
            self.logger.error(f"Failed to add part: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]

    def mark_job_as_completed(self, job_id: int) -> Tuple[bool, List[str]]:
        """
        Mark job as completed

        Args:
            job_id: Job ID

        Returns:
            (success, error_messages)
        """
        try:
            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]

            if job.completed:
                return False, ["Job is already completed"]

            job.mark_as_completed()
            self.logger.info(f"Job {job_id} marked as completed")
            return True, []

        except Exception as e:
            self.logger.error(f"Failed to mark job as completed: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]

    def mark_job_as_paid(self, job_id: int) -> Tuple[bool, List[str]]:
        """
        Mark job as paid

        Args:
            job_id: Job ID

        Returns:
            (success, error_messages)
        """
        try:
            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]

            if job.paid:
                return False, ["Job is already paid"]

            job.mark_as_paid()
            self.logger.info(f"Job {job_id} marked as paid")
            return True, []

        except Exception as e:
            self.logger.error(f"Failed to mark job as paid: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]

    def get_all_jobs_with_customer_info(self) -> List[Job]:
        """Get all jobs with customer information"""
        try:
            return Job.get_all_with_customer_info()
        except Exception as e:
            self.logger.error(f"Failed to get all jobs: {e}")
            return []

    def get_job_statistics(self) -> Dict[str, Any]:
        """Get job statistics (tenant-scoped via model)"""
        try:
            # Job.count() and Job.get_overdue_jobs() are tenant-scoped via TenantScopedMixin
            total_jobs = Job.count()
            completed_jobs = Job.count(completed=True)
            unpaid_jobs = Job.count(paid=False)
            overdue_jobs = Job.get_overdue_jobs()

            return {
                'total_jobs': total_jobs,
                'completed_jobs': completed_jobs,
                'pending_jobs': total_jobs - completed_jobs,
                'unpaid_jobs': unpaid_jobs,
                'overdue_jobs': len(overdue_jobs),
                'completion_rate': (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0,
                'payment_rate': ((total_jobs - unpaid_jobs) / total_jobs * 100) if total_jobs > 0 else 0
            }

        except Exception as e:
            self.logger.error(f"Failed to get job statistics: {e}")
            return {
                'total_jobs': 0,
                'completed_jobs': 0,
                'pending_jobs': 0,
                'unpaid_jobs': 0,
                'overdue_jobs': 0,
                'completion_rate': 0,
                'payment_rate': 0
            }

    def create_job(
        self,
        customer_id: int,
        job_date: date,
        tenant_id: int = None,
        vehicle_id: int = None,
        odometer_in: int = None,
        complaints: List[str] = None,
        is_estimate: bool = False,
        estimate_approved: bool = False,
        contingency_amount: Optional[Decimal] = None,
        contingency_note: Optional[str] = None,
    ) -> Tuple[bool, List[str], Optional[Job]]:
        """Create a new job with optional vehicle, odometer, complaints, estimate flags."""
        try:
            if job_date < date.today():
                return False, ["Job date cannot be earlier than today"], None

            job = Job(
                job_date=job_date,
                customer=customer_id,
                tenant_id=tenant_id or self._current_tenant_id(),
                vehicle_id=vehicle_id,
                odometer_in=odometer_in,
                total_cost=0.0,
                completed=False,
                paid=False,
                is_estimate=is_estimate,
                estimate_approved=estimate_approved if is_estimate else False,
                contingency_amount=contingency_amount or Decimal('0'),
                contingency_note=contingency_note,
            )
            db.session.add(job)
            db.session.flush()  # get job_id before adding complaints

            for i, desc in enumerate(complaints or []):
                if desc and desc.strip():
                    from app.models.job import JobComplaint
                    db.session.add(JobComplaint(
                        job_id=job.job_id,
                        description=desc.strip(),
                        sort_order=i,
                    ))

            db.session.commit()
            self.logger.info(f"Created job {job.job_id} for customer {customer_id}")
            return True, [], job

        except Exception as e:
            self.logger.error(f"Failed to create job: {e}")
            db.session.rollback()
            return False, ["System error, please try again"], None

    def approve_estimate(self, job_id: int) -> Tuple[bool, List[str]]:
        """Mark an estimate as approved by the customer."""
        try:
            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]
            if not job.is_estimate:
                return False, ["This job is not an estimate"]
            if job.estimate_approved:
                return False, ["Estimate is already approved"]

            job.estimate_approved = True
            db.session.commit()
            self.logger.info(f"Approved estimate for job {job_id}")
            return True, []
        except Exception as e:
            self.logger.error(f"Failed to approve estimate {job_id}: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]

    def delete_job(self, job_id: int) -> Tuple[bool, List[str]]:
        """
        Delete job

        Args:
            job_id: Job ID

        Returns:
            (success, error_messages)
        """
        try:
            job = self.get_job_by_id(job_id)
            if not job:
                return False, ["Job does not exist"]

            if job.completed:
                return False, ["Cannot delete a completed job"]

            if job.job_services or job.job_parts:
                return False, ["Cannot delete job with services or parts"]

            job.delete()
            self.logger.info(f"Deleted job {job_id}")
            return True, []

        except Exception as e:
            self.logger.error(f"Failed to delete job: {e}")
            db.session.rollback()
            return False, ["System error, please try again"]
