"""
MinIO client wrapper for MCP server.

Provides presigned URL generation and file operations for AI agents.
"""

import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, List


# MinIO configuration from environment
MINIO_ENDPOINT_URL = os.environ.get('MINIO_ENDPOINT_URL', 'https://minio.ayna.com')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', '')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', '')
MINIO_BUCKET_PREFIX = os.environ.get('MINIO_BUCKET_PREFIX', '')

# Lazy-loaded client
_client = None


def get_client():
    """Get MinIO S3 client (lazy-loaded)."""
    global _client
    if _client is None:
        _client = boto3.client(
            's3',
            endpoint_url=MINIO_ENDPOINT_URL,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1',
        )
    return _client


def get_bucket_name(org_id: str) -> str:
    """Get bucket name for organization."""
    return f"{MINIO_BUCKET_PREFIX}org-{org_id}"


def list_bucket_files(
    org_id: str,
    prefix: str = '',
    limit: int = 100,
    continuation_token: str = None
) -> Dict[str, Any]:
    """
    List files in organization's bucket.

    Args:
        org_id: Organization UUID
        prefix: Path prefix to filter
        limit: Max files to return
        continuation_token: For pagination

    Returns:
        Dict with files list and pagination info
    """
    client = get_client()
    bucket_name = get_bucket_name(org_id)

    params = {
        'Bucket': bucket_name,
        'Prefix': prefix,
        'MaxKeys': min(limit, 1000),
    }

    if continuation_token:
        params['ContinuationToken'] = continuation_token

    try:
        response = client.list_objects_v2(**params)

        files = []
        for obj in response.get('Contents', []):
            files.append({
                'key': obj['Key'],
                'size': obj['Size'],
                'last_modified': obj['LastModified'].isoformat(),
                'etag': obj['ETag'].strip('"'),
            })

        return {
            'success': True,
            'bucket': bucket_name,
            'prefix': prefix,
            'files': files,
            'file_count': len(files),
            'is_truncated': response.get('IsTruncated', False),
            'continuation_token': response.get('NextContinuationToken'),
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == '404' or error_code == 'NoSuchBucket':
            return {
                'success': True,
                'bucket': bucket_name,
                'prefix': prefix,
                'files': [],
                'file_count': 0,
                'message': 'Bucket does not exist or is empty',
            }
        return {
            'success': False,
            'error': str(e),
        }


def get_presigned_url(
    org_id: str,
    object_key: str,
    expiration: int = 900,
    method: str = 'get_object'
) -> Dict[str, Any]:
    """
    Generate presigned URL for file access.

    Args:
        org_id: Organization UUID
        object_key: Object key (path) in bucket
        expiration: URL validity in seconds (default 15 min)
        method: 'get_object' or 'put_object'

    Returns:
        Dict with URL and metadata
    """
    client = get_client()
    bucket_name = get_bucket_name(org_id)

    try:
        url = client.generate_presigned_url(
            method,
            Params={
                'Bucket': bucket_name,
                'Key': object_key,
            },
            ExpiresIn=expiration,
        )

        return {
            'success': True,
            'url': url,
            'bucket': bucket_name,
            'key': object_key,
            'expires_in': expiration,
        }

    except ClientError as e:
        return {
            'success': False,
            'error': str(e),
        }


def get_file_info(org_id: str, object_key: str) -> Dict[str, Any]:
    """
    Get file metadata from MinIO.

    Args:
        org_id: Organization UUID
        object_key: Object key (path) in bucket

    Returns:
        Dict with file metadata
    """
    client = get_client()
    bucket_name = get_bucket_name(org_id)

    try:
        response = client.head_object(Bucket=bucket_name, Key=object_key)

        return {
            'success': True,
            'key': object_key,
            'bucket': bucket_name,
            'size': response['ContentLength'],
            'content_type': response.get('ContentType', 'application/octet-stream'),
            'last_modified': response['LastModified'].isoformat(),
            'etag': response['ETag'].strip('"'),
            'metadata': response.get('Metadata', {}),
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == '404':
            return {
                'success': False,
                'error': 'File not found',
                'key': object_key,
            }
        return {
            'success': False,
            'error': str(e),
        }


def copy_file(
    org_id: str,
    source_key: str,
    dest_key: str
) -> Dict[str, Any]:
    """
    Copy file within organization's bucket.

    Args:
        org_id: Organization UUID
        source_key: Source object key
        dest_key: Destination object key

    Returns:
        Dict with copy result
    """
    client = get_client()
    bucket_name = get_bucket_name(org_id)

    try:
        client.copy_object(
            CopySource={'Bucket': bucket_name, 'Key': source_key},
            Bucket=bucket_name,
            Key=dest_key,
        )

        return {
            'success': True,
            'source_key': source_key,
            'dest_key': dest_key,
            'bucket': bucket_name,
        }

    except ClientError as e:
        return {
            'success': False,
            'error': str(e),
        }


def get_bucket_usage(org_id: str) -> Dict[str, Any]:
    """
    Get storage usage for organization's bucket.

    Note: This is expensive for large buckets. Prefer using
    the StorageQuota table for cached usage stats.

    Args:
        org_id: Organization UUID

    Returns:
        Dict with usage stats
    """
    client = get_client()
    bucket_name = get_bucket_name(org_id)

    total_size = 0
    file_count = 0
    continuation_token = None

    try:
        while True:
            params = {
                'Bucket': bucket_name,
                'MaxKeys': 1000,
            }
            if continuation_token:
                params['ContinuationToken'] = continuation_token

            response = client.list_objects_v2(**params)

            for obj in response.get('Contents', []):
                total_size += obj['Size']
                file_count += 1

            if not response.get('IsTruncated'):
                break
            continuation_token = response.get('NextContinuationToken')

        return {
            'success': True,
            'bucket': bucket_name,
            'total_size_bytes': total_size,
            'file_count': file_count,
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == '404' or error_code == 'NoSuchBucket':
            return {
                'success': True,
                'bucket': bucket_name,
                'total_size_bytes': 0,
                'file_count': 0,
                'message': 'Bucket does not exist',
            }
        return {
            'success': False,
            'error': str(e),
        }
