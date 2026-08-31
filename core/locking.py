import logging
from typing import List, Set, Optional, Dict, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, When, Value, IntegerField, Q

from core.models import Professor

logger = logging.getLogger(__name__)


# Set of status values that mark a professor/group as "active"
ACTIVE_STATUS_CODES: Set[str] = {
    "researching",
    "needs_review",
    "approved",
    "applied",
}

# Display names mapped to canonical internal status codes
STATUS_NAME_TO_CODE: Dict[str, str] = {
    "researching": "researching",
    "needs review": "needs_review",
    "needs_review": "needs_review",
    "approved": "approved",
    "applied": "applied",
    "pending": "pending",
}


class ContactGroupLockedException(ValidationError):
    """Raised when an action violates the rule of max ONE active professor per Contact Group."""
    pass


class ContactGroupLockManager:
    """
    Locking manager for Contact Groups enforcing the rule:
    Maximum ONE active professor per 'Contact Group'.

    A Contact Group is considered 'locked' (active) if ANY professor belonging to that
    group currently has one of the active statuses:
      - 'Researching'
      - 'Needs Review'
      - 'Approved'
      - 'Applied'
    """

    ACTIVE_STATUSES = ACTIVE_STATUS_CODES

    @classmethod
    def normalize_group_name(cls, group_name: Optional[str]) -> str:
        """Trim and return normalized contact group name."""
        return (group_name or "").strip()

    @classmethod
    def get_locked_contact_groups(cls) -> Set[str]:
        """
        Returns the set of all Contact Group names that are currently locked (active).
        A group is locked if it has at least one professor in Researching, Needs Review,
        Approved, or Applied status.
        """
        active_groups = (
            Professor.objects.filter(pipeline_status__in=cls.ACTIVE_STATUSES)
            .exclude(contact_group__isnull=True)
            .exclude(contact_group__exact="")
            .values_list("contact_group", flat=True)
            .distinct()
        )
        return {cls.normalize_group_name(g) for g in active_groups if cls.normalize_group_name(g)}

    @classmethod
    def is_group_locked(cls, contact_group: str, exclude_professor_id: Optional[int] = None) -> bool:
        """
        Checks if a specific Contact Group is currently locked.

        :param contact_group: Name of the contact group.
        :param exclude_professor_id: Optional professor ID to exclude (useful when updating an existing record).
        :return: True if group is locked by another active professor, False otherwise.
        """
        group_clean = cls.normalize_group_name(contact_group)
        if not group_clean:
            return False

        query = Professor.objects.filter(
            contact_group__iexact=group_clean,
            pipeline_status__in=cls.ACTIVE_STATUSES,
        )
        if exclude_professor_id:
            query = query.exclude(id=exclude_professor_id)

        return query.exists()

    @classmethod
    def get_active_professor_in_group(cls, contact_group: str) -> Optional[Professor]:
        """
        Returns the active Professor currently locking the Contact Group, if any.
        """
        group_clean = cls.normalize_group_name(contact_group)
        if not group_clean:
            return None

        return (
            Professor.objects.filter(
                contact_group__iexact=group_clean,
                pipeline_status__in=cls.ACTIVE_STATUSES,
            )
            .order_by("-updated_at")
            .first()
        )

    @classmethod
    def validate_professor_transition(
        cls, professor: Professor, new_status: str, new_contact_group: Optional[str] = None
    ) -> None:
        """
        Validates whether transitioning a professor to `new_status` or changing their
        `contact_group` violates the rule of maximum ONE active professor per Contact Group.

        Raises `ContactGroupLockedException` if the target group is already locked.
        """
        norm_status = STATUS_NAME_TO_CODE.get(new_status.lower().strip(), new_status.lower().strip())
        target_group = cls.normalize_group_name(new_contact_group if new_contact_group is not None else professor.contact_group)

        if not target_group:
            return

        if norm_status in cls.ACTIVE_STATUSES:
            active_prof = (
                Professor.objects.filter(
                    contact_group__iexact=target_group,
                    pipeline_status__in=cls.ACTIVE_STATUSES,
                )
                .exclude(id=professor.id if professor.id else None)
                .first()
            )

            if active_prof:
                raise ContactGroupLockedException(
                    f"Contact Group '{target_group}' is locked. It already has an active professor: "
                    f"'{active_prof.name}' with status '{active_prof.get_pipeline_status_display()}'. "
                    f"Maximum ONE active professor allowed per Contact Group."
                )

    @classmethod
    def activate_professor(cls, professor: Professor, target_status: str = "researching") -> Professor:
        """
        Safely transitions a professor to an active status inside a database transaction
        with atomic lock validation.
        """
        norm_status = STATUS_NAME_TO_CODE.get(target_status.lower().strip(), target_status.lower().strip())
        if norm_status not in cls.ACTIVE_STATUSES:
            raise ValueError(f"Target status '{target_status}' is not an active status.")

        with transaction.atomic():
            # Lock the group checking with SELECT FOR UPDATE if possible
            cls.validate_professor_transition(professor, norm_status)
            professor.pipeline_status = norm_status
            professor.save(update_fields=["pipeline_status", "updated_at"])

        return professor


def get_next_eligible_professors(limit: Optional[int] = None) -> List[Professor]:
    """
    Returns a list of highest-priority 'Pending' professors whose Contact Groups
    are currently unlocked (i.e. having NO active professor in 'Researching',
    'Needs Review', 'Approved', or 'Applied').

    Priority ordering:
      1. Priority ranking: High (1) -> Medium (2) -> Low (3)
      2. Created date: oldest pending records first

    Furthermore, ensures that the returned list contains at most ONE professor
    per eligible Contact Group so picking them concurrently will not cause conflicts.

    :param limit: Optional max number of eligible professors to return.
    :return: List of eligible Professor instances.
    """
    # 1. Identify all currently locked Contact Groups
    locked_groups = ContactGroupLockManager.get_locked_contact_groups()

    # 2. Query all 'Pending' professors
    pending_query = Professor.objects.filter(
        Q(pipeline_status__iexact="pending") | Q(pipeline_status="pending")
    )

    # Exclude professors whose contact group is in the locked set
    if locked_groups:
        pending_query = pending_query.exclude(contact_group__in=locked_groups)

    # 3. Order by Priority (High -> Medium -> Low), then creation timestamp
    ordered_pending = pending_query.annotate(
        priority_rank=Case(
            When(priority__iexact="high", then=Value(1)),
            When(priority__iexact="medium", then=Value(2)),
            When(priority__iexact="low", then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by("priority_rank", "created_at", "id")

    # 4. Filter to ensure at most one professor per Contact Group in the returned batch
    seen_groups: Set[str] = set()
    eligible: List[Professor] = []

    for prof in ordered_pending:
        group_key = (prof.contact_group or "").strip().lower()

        # If a contact group is specified, ensure we only include one per group in the batch
        if group_key:
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)

        eligible.append(prof)
        if limit is not None and len(eligible) >= limit:
            break

    return eligible
