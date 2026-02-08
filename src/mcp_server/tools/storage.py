"""
Storage tools for MCP server.

Provides AI agents access to organization file storage in MinIO.
All operations are scoped to a specific organization for tenant isolation.
"""

from typing import Dict, Any, List, Optional
from ..database import get_db
from ..minio_client import (
    list_bucket_files,
    get_presigned_url,
    get_file_info,
    copy_file,
    get_bucket_name,
)


def storage_list(
    org_id: str,
    prefix: str = '',
    category: str = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List files in organization's storage.

    Args:
        org_id: Organization UUID
        prefix: Path prefix to filter (e.g., 'flight-logs/')
        category: Filter by category (flight_log, raw_video, document, etc.)
        limit: Maximum files to return

    Returns:
        Dict with files list and metadata
    """
    db = get_db()
    try:
        # Query StorageFile table for metadata
        from sqlalchemy import text

        query = """
            SELECT
                sf.id,
                sf.bucket_name,
                sf.object_key,
                sf.original_filename,
                sf.content_type,
                sf.file_size_bytes,
                sf.category,
                sf.tier,
                sf.description,
                sf.tags,
                sf.ai_category,
                sf.ai_tags,
                sf.ai_summary,
                sf.created_at,
                sf.updated_at
            FROM storage_file sf
            JOIN organization o ON sf.organization_id = o.id
            WHERE o.id = :org_id
              AND sf.deleted_at IS NULL
        """

        params = {'org_id': org_id}

        if category:
            query += " AND sf.category = :category"
            params['category'] = category

        if prefix:
            query += " AND sf.object_key LIKE :prefix"
            params['prefix'] = f"{prefix}%"

        query += " ORDER BY sf.created_at DESC LIMIT :limit"
        params['limit'] = limit

        result = db.execute(text(query), params)
        rows = result.fetchall()

        files = []
        for row in rows:
            files.append({
                'id': str(row.id),
                'bucket': row.bucket_name,
                'key': row.object_key,
                'filename': row.original_filename,
                'content_type': row.content_type,
                'size_bytes': row.file_size_bytes,
                'size_display': _format_size(row.file_size_bytes),
                'category': row.category,
                'tier': row.tier,
                'description': row.description or '',
                'tags': row.tags or [],
                'ai_category': row.ai_category or '',
                'ai_tags': row.ai_tags or [],
                'ai_summary': row.ai_summary or '',
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
            })

        return {
            'success': True,
            'org_id': org_id,
            'prefix': prefix,
            'category_filter': category,
            'files': files,
            'file_count': len(files),
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_get(
    org_id: str,
    file_id: str = None,
    object_key: str = None,
    include_url: bool = True,
) -> Dict[str, Any]:
    """
    Get file details with optional download URL.

    Args:
        org_id: Organization UUID
        file_id: StorageFile UUID (preferred)
        object_key: Object key in bucket (alternative)
        include_url: Whether to include presigned URL

    Returns:
        Dict with file metadata and optional URL
    """
    db = get_db()
    try:
        from sqlalchemy import text

        if file_id:
            query = """
                SELECT
                    sf.*,
                    o.name as org_name
                FROM storage_file sf
                JOIN organization o ON sf.organization_id = o.id
                WHERE sf.id = :file_id
                  AND o.id = :org_id
                  AND sf.deleted_at IS NULL
            """
            params = {'file_id': file_id, 'org_id': org_id}
        elif object_key:
            query = """
                SELECT
                    sf.*,
                    o.name as org_name
                FROM storage_file sf
                JOIN organization o ON sf.organization_id = o.id
                WHERE sf.object_key = :object_key
                  AND o.id = :org_id
                  AND sf.deleted_at IS NULL
            """
            params = {'object_key': object_key, 'org_id': org_id}
        else:
            return {
                'success': False,
                'error': 'Either file_id or object_key is required',
            }

        result = db.execute(text(query), params)
        row = result.fetchone()

        if not row:
            return {
                'success': False,
                'error': 'File not found',
            }

        file_data = {
            'id': str(row.id),
            'bucket': row.bucket_name,
            'key': row.object_key,
            'filename': row.original_filename,
            'content_type': row.content_type,
            'size_bytes': row.file_size_bytes,
            'size_display': _format_size(row.file_size_bytes),
            'category': row.category,
            'tier': row.tier,
            'description': row.description or '',
            'tags': row.tags or [],
            'ai_category': row.ai_category or '',
            'ai_tags': row.ai_tags or [],
            'ai_summary': row.ai_summary or '',
            'flight_id': str(row.flight_id) if row.flight_id else None,
            'mission_id': str(row.mission_id) if row.mission_id else None,
            'drone_id': str(row.drone_id) if row.drone_id else None,
            'pilot_id': str(row.pilot_id) if row.pilot_id else None,
            'access_count': row.access_count,
            'last_accessed': row.last_accessed.isoformat() if row.last_accessed else None,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        }

        if include_url:
            url_result = get_presigned_url(org_id, row.object_key, expiration=900)
            if url_result['success']:
                file_data['download_url'] = url_result['url']
                file_data['url_expires_in'] = 900

        return {
            'success': True,
            'file': file_data,
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_classify(
    org_id: str,
    file_id: str,
    ai_category: str = None,
    ai_tags: List[str] = None,
    ai_summary: str = None,
) -> Dict[str, Any]:
    """
    Set AI classification metadata on a file.

    Args:
        org_id: Organization UUID
        file_id: StorageFile UUID
        ai_category: AI-detected category
        ai_tags: AI-detected tags
        ai_summary: AI-generated summary

    Returns:
        Dict with updated file info
    """
    db = get_db()
    try:
        from sqlalchemy import text
        import json

        # Verify file belongs to org
        verify_query = """
            SELECT sf.id FROM storage_file sf
            JOIN organization o ON sf.organization_id = o.id
            WHERE sf.id = :file_id AND o.id = :org_id AND sf.deleted_at IS NULL
        """
        result = db.execute(text(verify_query), {'file_id': file_id, 'org_id': org_id})
        if not result.fetchone():
            return {
                'success': False,
                'error': 'File not found or access denied',
            }

        # Build update
        updates = []
        params = {'file_id': file_id}

        if ai_category is not None:
            updates.append("ai_category = :ai_category")
            params['ai_category'] = ai_category

        if ai_tags is not None:
            updates.append("ai_tags = :ai_tags")
            params['ai_tags'] = json.dumps(ai_tags)

        if ai_summary is not None:
            updates.append("ai_summary = :ai_summary")
            params['ai_summary'] = ai_summary

        if not updates:
            return {
                'success': False,
                'error': 'No classification fields provided',
            }

        updates.append("updated_at = NOW()")
        update_query = f"UPDATE storage_file SET {', '.join(updates)} WHERE id = :file_id"

        db.execute(text(update_query), params)
        db.commit()

        return {
            'success': True,
            'file_id': file_id,
            'updated': {
                'ai_category': ai_category,
                'ai_tags': ai_tags,
                'ai_summary': ai_summary,
            },
        }

    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_notes(
    org_id: str,
    file_id: str,
    description: str = None,
    tags: List[str] = None,
    append_description: bool = False,
) -> Dict[str, Any]:
    """
    Add or update notes on a file.

    Args:
        org_id: Organization UUID
        file_id: StorageFile UUID
        description: New description text
        tags: New tags list
        append_description: If True, append to existing description

    Returns:
        Dict with updated file info
    """
    db = get_db()
    try:
        from sqlalchemy import text
        import json

        # Get current file
        query = """
            SELECT sf.id, sf.description, sf.tags FROM storage_file sf
            JOIN organization o ON sf.organization_id = o.id
            WHERE sf.id = :file_id AND o.id = :org_id AND sf.deleted_at IS NULL
        """
        result = db.execute(text(query), {'file_id': file_id, 'org_id': org_id})
        row = result.fetchone()

        if not row:
            return {
                'success': False,
                'error': 'File not found or access denied',
            }

        # Build update
        updates = []
        params = {'file_id': file_id}

        if description is not None:
            if append_description and row.description:
                new_desc = f"{row.description}\n\n{description}"
            else:
                new_desc = description
            updates.append("description = :description")
            params['description'] = new_desc

        if tags is not None:
            # Merge with existing tags
            existing_tags = row.tags or []
            merged_tags = list(set(existing_tags + tags))
            updates.append("tags = :tags")
            params['tags'] = json.dumps(merged_tags)

        if not updates:
            return {
                'success': False,
                'error': 'No fields to update',
            }

        updates.append("updated_at = NOW()")
        update_query = f"UPDATE storage_file SET {', '.join(updates)} WHERE id = :file_id"

        db.execute(text(update_query), params)
        db.commit()

        return {
            'success': True,
            'file_id': file_id,
            'updated': {
                'description': params.get('description'),
                'tags': tags,
            },
        }

    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_move(
    org_id: str,
    file_id: str,
    new_category: str,
) -> Dict[str, Any]:
    """
    Move file to a different category/folder.

    Args:
        org_id: Organization UUID
        file_id: StorageFile UUID
        new_category: Target category

    Returns:
        Dict with move result
    """
    db = get_db()
    try:
        from sqlalchemy import text
        import uuid

        valid_categories = [
            'flight_log', 'raw_video', 'processed_media', 'document',
            'deliverable', 'asset', 'maintenance', 'certification', 'other'
        ]

        if new_category not in valid_categories:
            return {
                'success': False,
                'error': f'Invalid category: {new_category}. Valid: {valid_categories}',
            }

        # Get current file
        query = """
            SELECT sf.id, sf.object_key, sf.original_filename, sf.category
            FROM storage_file sf
            JOIN organization o ON sf.organization_id = o.id
            WHERE sf.id = :file_id AND o.id = :org_id AND sf.deleted_at IS NULL
        """
        result = db.execute(text(query), {'file_id': file_id, 'org_id': org_id})
        row = result.fetchone()

        if not row:
            return {
                'success': False,
                'error': 'File not found or access denied',
            }

        if row.category == new_category:
            return {
                'success': True,
                'message': 'File already in this category',
                'file_id': file_id,
                'category': new_category,
            }

        # Generate new object key
        prefix_map = {
            'flight_log': 'flight-logs/',
            'raw_video': 'raw-video/',
            'processed_media': 'processed/',
            'document': 'documents/',
            'deliverable': 'deliverables/',
            'asset': 'assets/',
            'maintenance': 'maintenance/',
            'certification': 'certifications/',
            'other': 'other/',
        }
        new_prefix = prefix_map[new_category]
        file_uuid = str(uuid.uuid4())
        ext = row.original_filename.rsplit('.', 1)[-1] if '.' in row.original_filename else ''
        new_key = f"{new_prefix}{file_uuid[:2]}/{file_uuid}.{ext}" if ext else f"{new_prefix}{file_uuid[:2]}/{file_uuid}"

        # Copy file in MinIO
        copy_result = copy_file(org_id, row.object_key, new_key)
        if not copy_result['success']:
            return copy_result

        # Update database record
        update_query = """
            UPDATE storage_file
            SET object_key = :new_key, category = :category, updated_at = NOW()
            WHERE id = :file_id
        """
        db.execute(text(update_query), {
            'file_id': file_id,
            'new_key': new_key,
            'category': new_category,
        })
        db.commit()

        return {
            'success': True,
            'file_id': file_id,
            'old_category': row.category,
            'new_category': new_category,
            'old_key': row.object_key,
            'new_key': new_key,
        }

    except Exception as e:
        db.rollback()
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_quota(org_id: str) -> Dict[str, Any]:
    """
    Get storage quota and usage for organization.

    Args:
        org_id: Organization UUID

    Returns:
        Dict with quota and usage stats
    """
    db = get_db()
    try:
        from sqlalchemy import text

        query = """
            SELECT
                sq.hot_storage_limit_bytes,
                sq.hot_storage_used_bytes,
                sq.cold_storage_limit_bytes,
                sq.cold_storage_used_bytes,
                sq.file_count,
                sq.alert_threshold_percent,
                sq.last_calculated,
                o.name as org_name,
                o.subscription_tier
            FROM storage_quota sq
            JOIN organization o ON sq.organization_id = o.id
            WHERE o.id = :org_id
        """
        result = db.execute(text(query), {'org_id': org_id})
        row = result.fetchone()

        if not row:
            return {
                'success': True,
                'message': 'No quota record found - using defaults',
                'org_id': org_id,
                'hot_storage': {'used': 0, 'limit': 5 * 1024**3},
                'cold_storage': {'used': 0, 'limit': 10 * 1024**3},
                'file_count': 0,
            }

        hot_used = row.hot_storage_used_bytes
        hot_limit = row.hot_storage_limit_bytes
        cold_used = row.cold_storage_used_bytes
        cold_limit = row.cold_storage_limit_bytes

        return {
            'success': True,
            'org_id': org_id,
            'org_name': row.org_name,
            'subscription_tier': row.subscription_tier,
            'hot_storage': {
                'used_bytes': hot_used,
                'used_display': _format_size(hot_used),
                'limit_bytes': hot_limit,
                'limit_display': _format_size(hot_limit),
                'usage_percent': round((hot_used / hot_limit * 100) if hot_limit else 0, 1),
                'remaining_bytes': max(0, hot_limit - hot_used),
            },
            'cold_storage': {
                'used_bytes': cold_used,
                'used_display': _format_size(cold_used),
                'limit_bytes': cold_limit,
                'limit_display': _format_size(cold_limit),
                'usage_percent': round((cold_used / cold_limit * 100) if cold_limit else 0, 1),
                'remaining_bytes': max(0, cold_limit - cold_used),
            },
            'total': {
                'used_bytes': hot_used + cold_used,
                'used_display': _format_size(hot_used + cold_used),
                'limit_bytes': hot_limit + cold_limit,
                'limit_display': _format_size(hot_limit + cold_limit),
            },
            'file_count': row.file_count,
            'alert_threshold': row.alert_threshold_percent,
            'last_calculated': row.last_calculated.isoformat() if row.last_calculated else None,
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def storage_search(
    org_id: str,
    query: str,
    category: str = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search files by filename, description, or AI summary.

    Args:
        org_id: Organization UUID
        query: Search query string
        category: Optional category filter
        limit: Max results

    Returns:
        Dict with matching files
    """
    db = get_db()
    try:
        from sqlalchemy import text

        sql = """
            SELECT
                sf.id,
                sf.bucket_name,
                sf.object_key,
                sf.original_filename,
                sf.content_type,
                sf.file_size_bytes,
                sf.category,
                sf.description,
                sf.ai_summary,
                sf.created_at
            FROM storage_file sf
            JOIN organization o ON sf.organization_id = o.id
            WHERE o.id = :org_id
              AND sf.deleted_at IS NULL
              AND (
                  sf.original_filename ILIKE :search
                  OR sf.description ILIKE :search
                  OR sf.ai_summary ILIKE :search
              )
        """

        params = {
            'org_id': org_id,
            'search': f'%{query}%',
        }

        if category:
            sql += " AND sf.category = :category"
            params['category'] = category

        sql += " ORDER BY sf.created_at DESC LIMIT :limit"
        params['limit'] = limit

        result = db.execute(text(sql), params)
        rows = result.fetchall()

        files = []
        for row in rows:
            files.append({
                'id': str(row.id),
                'bucket': row.bucket_name,
                'key': row.object_key,
                'filename': row.original_filename,
                'content_type': row.content_type,
                'size_display': _format_size(row.file_size_bytes),
                'category': row.category,
                'description': row.description or '',
                'ai_summary': row.ai_summary or '',
                'created_at': row.created_at.isoformat() if row.created_at else None,
            })

        return {
            'success': True,
            'query': query,
            'category_filter': category,
            'results': files,
            'result_count': len(files),
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        db.close()


def _format_size(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"
