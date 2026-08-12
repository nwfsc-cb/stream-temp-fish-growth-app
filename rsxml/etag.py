import hashlib
import os

from rsxml.constants import MULTIPART_CHUNK_SIZE, MULTIPART_THRESHOLD


def calculate_etag(
    filePath: str,
    chunk_size_bytes: int = MULTIPART_CHUNK_SIZE,
    chunk_thresh_bytes: int = MULTIPART_THRESHOLD,
    force_single_part: bool = False,
) -> str:
    """Calculate the Etag of a file. This is useful for figuring out if
    it needs to be uploaded to the warehouse or not.

    Args:
        filePath (str): path to the file we want an etag for
        chunk_size_bytes (int): The size of a multipart upload
        chunk_thresh_bytes (int): The threshold before we start using multipart uploads
        force_single_part (bool): If True, force a single part etag (standard MD5) even for large files.

    Returns:
        str: The Etag of the file

    """
    filesize_bytes = os.stat(filePath).st_size

    etag = ""
    # For files smaller than the threshold size we just MD5 the whole file
    if filesize_bytes < chunk_thresh_bytes or force_single_part:
        hash_obj = hashlib.md5()
        with open(filePath, "rb") as f:
            # Read in chunks to avoid memory issues with large files
            for chunk in iter(lambda: f.read(4096 * 1024), b""):
                hash_obj.update(chunk)
        etag = hash_obj.hexdigest()
    # For large files we need to use the MD5 hashing schem prescribed by S3 for multipart uploads
    else:
        parts = filesize_bytes // chunk_size_bytes
        if filesize_bytes % chunk_size_bytes > 0:
            parts += 1

        md5_digests = []
        with open(filePath, "rb") as file:
            for part in range(parts):
                skip_bytes = chunk_size_bytes * part
                total_bytes_left = filesize_bytes - skip_bytes
                bytes_to_read = min(total_bytes_left, chunk_size_bytes)
                file.seek(skip_bytes)
                buffer = file.read(bytes_to_read)
                md5_digests.append(hashlib.md5(buffer).digest())

        combined_hash = hashlib.md5(b"".join(md5_digests)).hexdigest()
        etag = f"{combined_hash}-{parts}"

    return f'"{etag}"'
