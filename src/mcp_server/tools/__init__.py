"""MCP tools for compliance data access."""

from .flight_log import get_flight_log
from .pilot import get_pilot
from .aircraft import get_aircraft
from .mission import get_mission
from .maintenance import get_maintenance_history
from .list_files import list_files
from .read_file import read_file
from .file_metadata import get_file_metadata
from .certifications import (
    # READ tools
    search_pilots,
    check_authorization,
    get_expiring_certifications,
    # WRITE tools
    update_faa_verification,
    record_verification_audit,
    update_training_status,
    flag_certification_warning,
)

__all__ = [
    # Compliance data tools (READ)
    "get_flight_log",
    "get_pilot",
    "get_aircraft",
    "get_mission",
    "get_maintenance_history",
    # File access tools (READ)
    "list_files",
    "read_file",
    "get_file_metadata",
    # Certification tools (READ)
    "search_pilots",
    "check_authorization",
    "get_expiring_certifications",
    # Certification tools (WRITE)
    "update_faa_verification",
    "record_verification_audit",
    "update_training_status",
    "flag_certification_warning",
]
