"""
Database backup — admin-only export of every table as CSV inside one zip.

Railway keeps volume backups behind the Pro plan, so this deployment has no
backups at all. Rather than depend on that, the data is exported directly:
the schema is reproducible from the Alembic migrations in the repository, so
the data itself is the part that cannot be recreated.

Deliberately CSV rather than pg_dump: the runtime image ships no
postgresql-client, and a backup that depends on a binary which may or may not
be in the image is not a backup you can rely on when you need it.
"""
import csv
import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

# Written verbatim into the archive so whoever restores it does not have to
# reconstruct the procedure from memory under pressure.
_RESTORE_NOTES = """RESTORING THIS BACKUP
=====================

This archive holds one CSV per table plus manifest.json. The schema is NOT in
here — it is recreated from the Alembic migrations in the repository, which
are versioned alongside the code that expects them.

1. Create an empty database and point DATABASE_URL at it.
2. Recreate the schema:      cd backend && alembic upgrade head
   manifest.json records the alembic revision this backup was taken at.
   Check out that revision first if it is not the current one.
3. Load each CSV, parents before children (users and assets first, then
   portfolios, recommendations, watchlist, notifications, ...):

     \\copy <table> FROM '<table>.csv' WITH (FORMAT csv, HEADER true)

4. Reset the id sequences, or every insert afterwards collides:

     SELECT setval(pg_get_serial_sequence('<table>','id'),
                   COALESCE((SELECT MAX(id) FROM <table>), 1));

Verify row counts against manifest.json before trusting the restore.
"""


@router.get("/export")
async def export_backup(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Download every table as CSV in one zip. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = await db.connection()
    table_names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    # Alembic's own bookkeeping table is data too — it records which schema
    # version these CSVs belong to.
    table_names = sorted(table_names)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp_dir = tempfile.mkdtemp(prefix="ai_backup_")
    zip_path = os.path.join(tmp_dir, f"investment-ai-backup-{stamp}.zip")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "alembic_revision": None,
        "note": "Schema comes from alembic migrations; this archive is data only.",
    }

    total_rows = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in table_names:
            try:
                result = await db.execute(text(f'SELECT * FROM "{table}"'))
                rows = result.fetchall()
                columns = list(result.keys())

                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow([
                        "" if v is None
                        else json.dumps(v, ensure_ascii=False, default=str)
                        if isinstance(v, (dict, list))
                        else v
                        for v in row
                    ])
                zf.writestr(f"{table}.csv", buf.getvalue())

                manifest["tables"][table] = len(rows)
                total_rows += len(rows)
                if table == "alembic_version" and rows:
                    manifest["alembic_revision"] = rows[0][0]
            except Exception as exc:
                logger.warning(f"[backup] table {table} failed: {exc}")
                manifest["tables"][table] = f"FAILED: {exc}"

        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("RESTORE.txt", _RESTORE_NOTES)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info(
        f"[backup] exported {len(table_names)} tables, {total_rows} rows, {size_mb:.1f} MB"
    )

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=os.path.basename(zip_path),
    )


@router.get("/status")
async def backup_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Row counts per table — a cheap way to sanity-check a backup afterwards
    and to see at a glance how much data is at risk."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = await db.connection()
    table_names = await conn.run_sync(lambda c: inspect(c).get_table_names())

    counts = {}
    for table in sorted(table_names):
        try:
            r = await db.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
            counts[table] = r.scalar()
        except Exception:
            counts[table] = None

    return {
        "tables": counts,
        "total_rows": sum(v for v in counts.values() if isinstance(v, int)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
