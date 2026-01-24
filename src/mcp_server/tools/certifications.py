"""Certification tools for MCP server.

Provides both READ and WRITE operations for CONCORD integration:
- READ: Search pilots, check authorization, get expiring certs
- WRITE: Update FAA verification, record audits, update training, flag warnings
"""

import json
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database.models import (
    Pilot,
    FAAVerification,
    VerificationAudit,
    TrainingRecord,
    CertificationWarning,
)


# =============================================================================
# READ Tools
# =============================================================================

def search_pilots(
    db: Session,
    name: str | None = None,
    certificate_number: str | None = None,
    certificate_type: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Search pilots by various criteria.

    Args:
        db: Database session
        name: Partial name match (case-insensitive)
        certificate_number: Exact or partial certificate number
        certificate_type: Filter by certificate type (Part 107, Part 61, etc.)
        limit: Maximum results to return

    Returns:
        List of matching pilots
    """
    query = db.query(Pilot)

    if name:
        query = query.filter(Pilot.name.ilike(f"%{name}%"))
    if certificate_number:
        query = query.filter(Pilot.certificate_number.ilike(f"%{certificate_number}%"))
    if certificate_type:
        query = query.filter(Pilot.certificate_type == certificate_type)

    pilots = query.limit(limit).all()

    return {
        "pilots": [
            {
                "pilot_id": p.id,
                "name": p.name,
                "certificate_type": p.certificate_type,
                "certificate_number": p.certificate_number,
                "certificate_expiry": p.certificate_expiry.isoformat(),
                "certificate_valid": p.certificate_valid,
            }
            for p in pilots
        ],
        "count": len(pilots),
    }


def check_authorization(
    db: Session,
    pilot_id: str,
    operation_type: str = "Part 107",
    aircraft_id: str | None = None,
) -> dict:
    """
    Check if a pilot is authorized for a specific operation.

    Args:
        db: Database session
        pilot_id: Pilot identifier
        operation_type: Type of operation (Part 107, Part 61 BVLOS, etc.)
        aircraft_id: Optional aircraft ID for aircraft-specific checks

    Returns:
        Authorization status and details
    """
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        return {"error": f"Pilot not found: {pilot_id}", "authorized": False}

    # Check certificate validity
    today = date.today()
    cert_expired = pilot.certificate_expiry < today
    cert_valid = pilot.certificate_valid and not cert_expired

    # Check for recent FAA verification
    recent_verification = (
        db.query(FAAVerification)
        .filter(FAAVerification.pilot_id == pilot_id)
        .order_by(FAAVerification.verified_at.desc())
        .first()
    )

    # Check for active warnings
    active_warnings = (
        db.query(CertificationWarning)
        .filter(
            CertificationWarning.entity_type == "pilot",
            CertificationWarning.entity_id == pilot_id,
            CertificationWarning.resolved == False,
            CertificationWarning.severity.in_(["critical", "high"]),
        )
        .all()
    )

    # Determine authorization
    authorized = cert_valid and len(active_warnings) == 0

    # Check waivers for operation type
    waivers = json.loads(pilot.waivers) if pilot.waivers else []
    has_required_waiver = operation_type in waivers if operation_type != "Part 107" else True

    return {
        "pilot_id": pilot_id,
        "pilot_name": pilot.name,
        "operation_type": operation_type,
        "authorized": authorized and has_required_waiver,
        "certificate_valid": cert_valid,
        "certificate_expired": cert_expired,
        "certificate_expiry": pilot.certificate_expiry.isoformat(),
        "has_required_waiver": has_required_waiver,
        "waivers": waivers,
        "active_warnings": len(active_warnings),
        "last_faa_verification": (
            recent_verification.verified_at.isoformat()
            if recent_verification else None
        ),
        "reasons": _build_authorization_reasons(
            cert_valid, cert_expired, has_required_waiver, active_warnings
        ),
    }


def _build_authorization_reasons(
    cert_valid: bool,
    cert_expired: bool,
    has_waiver: bool,
    warnings: list,
) -> list[str]:
    """Build list of reasons for authorization status."""
    reasons = []
    if not cert_valid:
        reasons.append("Certificate marked as invalid")
    if cert_expired:
        reasons.append("Certificate has expired")
    if not has_waiver:
        reasons.append("Missing required waiver for operation type")
    if warnings:
        reasons.append(f"{len(warnings)} active high-severity warning(s)")
    if not reasons:
        reasons.append("All checks passed")
    return reasons


def get_expiring_certifications(
    db: Session,
    days_ahead: int = 90,
    pilot_id: str | None = None,
) -> dict:
    """
    Get certifications expiring within a timeframe.

    Args:
        db: Database session
        days_ahead: Number of days to look ahead
        pilot_id: Optional - filter to specific pilot

    Returns:
        List of expiring certifications
    """
    cutoff_date = date.today() + timedelta(days=days_ahead)
    today = date.today()

    query = db.query(Pilot).filter(Pilot.certificate_expiry <= cutoff_date)

    if pilot_id:
        query = query.filter(Pilot.id == pilot_id)

    pilots = query.all()

    expiring = []
    for p in pilots:
        days_until = (p.certificate_expiry - today).days
        status = "expired" if days_until < 0 else "expiring"

        expiring.append({
            "pilot_id": p.id,
            "pilot_name": p.name,
            "certificate_type": p.certificate_type,
            "certificate_number": p.certificate_number,
            "expiry_date": p.certificate_expiry.isoformat(),
            "days_until_expiry": days_until,
            "status": status,
        })

    # Sort by expiry (most urgent first)
    expiring.sort(key=lambda x: x["days_until_expiry"])

    return {
        "expiring_certifications": expiring,
        "count": len(expiring),
        "days_ahead": days_ahead,
    }


# =============================================================================
# WRITE Tools
# =============================================================================

def update_faa_verification(
    db: Session,
    pilot_id: str,
    verification_status: str,
    is_authorized: bool,
    certificate_verified: bool = True,
    verification_source: str = "faa_airmen_inquiry",
    verification_details: dict | None = None,
    verified_by: str = "CONCORD",
    expires_at: datetime | None = None,
) -> dict:
    """
    Update FAA verification status for a pilot.

    Called by CONCORD after verifying pilot credentials with FAA.

    Args:
        db: Database session
        pilot_id: Pilot identifier
        verification_status: valid, invalid, expired, not_found
        is_authorized: Whether pilot is authorized to fly
        certificate_verified: Whether certificate was successfully verified
        verification_source: Source of verification (faa_airmen_inquiry, manual, etc.)
        verification_details: Additional verification data
        verified_by: Agent performing verification (default: CONCORD)
        expires_at: When this verification expires

    Returns:
        Created verification record
    """
    # Verify pilot exists
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        return {"error": f"Pilot not found: {pilot_id}"}

    # Create verification record
    verification = FAAVerification(
        pilot_id=pilot_id,
        verification_status=verification_status,
        is_authorized=is_authorized,
        certificate_verified=certificate_verified,
        verification_source=verification_source,
        verification_details=json.dumps(verification_details or {}),
        verified_by=verified_by,
        verified_at=datetime.utcnow(),
        expires_at=expires_at,
    )

    db.add(verification)

    # Update pilot's certificate_valid based on verification
    if verification_status == "valid":
        pilot.certificate_valid = True
    elif verification_status in ["invalid", "expired", "not_found"]:
        pilot.certificate_valid = False

    db.commit()

    return {
        "verification_id": verification.id,
        "pilot_id": pilot_id,
        "verification_status": verification_status,
        "is_authorized": is_authorized,
        "verified_at": verification.verified_at.isoformat(),
        "verified_by": verified_by,
        "message": f"FAA verification recorded for pilot {pilot_id}",
    }


def record_verification_audit(
    db: Session,
    event_type: str,
    entity_type: str,
    entity_id: str,
    action: str,
    result: str,
    performed_by: str,
    details: dict | None = None,
    job_id: str | None = None,
) -> dict:
    """
    Record an audit trail entry for a verification event.

    Args:
        db: Database session
        event_type: Type of event (faa_check, training_update, warning_flag, etc.)
        entity_type: Type of entity (pilot, aircraft, flight)
        entity_id: Entity identifier
        action: Action performed
        result: Result (success, failure, warning)
        performed_by: Agent name (CONCORD, TUCKER, etc.)
        details: Additional event details
        job_id: Optional workflow job reference

    Returns:
        Created audit record
    """
    audit = VerificationAudit(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        result=result,
        details=json.dumps(details or {}),
        performed_by=performed_by,
        job_id=job_id,
    )

    db.add(audit)
    db.commit()

    return {
        "audit_id": audit.id,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "result": result,
        "performed_by": performed_by,
        "created_at": audit.created_at.isoformat(),
        "message": f"Audit record created for {entity_type} {entity_id}",
    }


def update_training_status(
    db: Session,
    pilot_id: str,
    training_type: str,
    course_name: str,
    completion_date: str,
    expiry_date: str | None = None,
    provider: str | None = None,
    certificate_number: str | None = None,
    notes: str | None = None,
    updated_by: str = "CONCORD",
) -> dict:
    """
    Update or create a training record for a pilot.

    Args:
        db: Database session
        pilot_id: Pilot identifier
        training_type: Type (initial, recurrent, specialized)
        course_name: Name of training course
        completion_date: Date training was completed (ISO format)
        expiry_date: Optional expiry date (ISO format)
        provider: Training provider name
        certificate_number: Training certificate number
        notes: Additional notes
        updated_by: Agent updating the record

    Returns:
        Created/updated training record
    """
    # Verify pilot exists
    pilot = db.query(Pilot).filter(Pilot.id == pilot_id).first()
    if not pilot:
        return {"error": f"Pilot not found: {pilot_id}"}

    # Parse dates
    try:
        comp_date = date.fromisoformat(completion_date)
    except ValueError:
        return {"error": f"Invalid completion_date format: {completion_date}"}

    exp_date = None
    if expiry_date:
        try:
            exp_date = date.fromisoformat(expiry_date)
        except ValueError:
            return {"error": f"Invalid expiry_date format: {expiry_date}"}

    # Determine status
    today = date.today()
    if exp_date:
        if exp_date < today:
            status = "expired"
        elif exp_date < today + timedelta(days=90):
            status = "expiring"
        else:
            status = "current"
    else:
        status = "current"

    # Create training record
    training = TrainingRecord(
        pilot_id=pilot_id,
        training_type=training_type,
        course_name=course_name,
        provider=provider,
        completion_date=comp_date,
        expiry_date=exp_date,
        certificate_number=certificate_number,
        status=status,
        notes=notes,
        updated_by=updated_by,
    )

    db.add(training)
    db.commit()

    return {
        "training_id": training.id,
        "pilot_id": pilot_id,
        "training_type": training_type,
        "course_name": course_name,
        "completion_date": comp_date.isoformat(),
        "expiry_date": exp_date.isoformat() if exp_date else None,
        "status": status,
        "message": f"Training record created for pilot {pilot_id}",
    }


def flag_certification_warning(
    db: Session,
    entity_type: str,
    entity_id: str,
    warning_type: str,
    severity: str,
    title: str,
    description: str,
    due_date: str | None = None,
    flagged_by: str = "CONCORD",
    job_id: str | None = None,
) -> dict:
    """
    Create a certification warning/alert.

    Args:
        db: Database session
        entity_type: Type of entity (pilot, aircraft)
        entity_id: Entity identifier
        warning_type: Type (expiring, expired, invalid, missing_training)
        severity: Severity level (critical, high, medium, low)
        title: Short warning title
        description: Detailed description
        due_date: Optional due date for resolution (ISO format)
        flagged_by: Agent creating the warning
        job_id: Optional workflow job reference

    Returns:
        Created warning record
    """
    # Parse due date if provided
    due = None
    if due_date:
        try:
            due = date.fromisoformat(due_date)
        except ValueError:
            return {"error": f"Invalid due_date format: {due_date}"}

    # Check for existing unresolved warning of same type
    existing = (
        db.query(CertificationWarning)
        .filter(
            CertificationWarning.entity_type == entity_type,
            CertificationWarning.entity_id == entity_id,
            CertificationWarning.warning_type == warning_type,
            CertificationWarning.resolved == False,
        )
        .first()
    )

    if existing:
        return {
            "warning_id": existing.id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "warning_type": warning_type,
            "already_exists": True,
            "message": f"Warning already exists (ID: {existing.id})",
        }

    # Create warning
    warning = CertificationWarning(
        entity_type=entity_type,
        entity_id=entity_id,
        warning_type=warning_type,
        severity=severity,
        title=title,
        description=description,
        due_date=due,
        flagged_by=flagged_by,
        job_id=job_id,
    )

    db.add(warning)
    db.commit()

    return {
        "warning_id": warning.id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "warning_type": warning_type,
        "severity": severity,
        "title": title,
        "created_at": warning.created_at.isoformat(),
        "message": f"Warning flagged for {entity_type} {entity_id}",
    }
