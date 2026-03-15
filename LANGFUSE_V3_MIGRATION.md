# Langfuse v2 to v3 Migration - COMPLETED

## Status: ✅ Complete

## Migration Date: 2026-03-15

## New Configuration

- **Running Version**: Langfuse v3.99.0
- **Previous Version**: Langfuse v2.95.11
- **Database**: PostgreSQL + ClickHouse + Redis + MinIO

---

## Migration Completed Successfully

Langfuse v3 is now running with the following services:

| Service | Port | Image |
|---------|------|-------|
| langfuse-web | 3000 | langfuse/langfuse:3 |
| langfuse-worker | 3030 | langfuse/langfuse-worker:3 |
| postgres | 5432 | postgres:17 |
| clickhouse | 8123 | clickhouse/clickhouse-server |
| redis | 6379 | valkey/valkey:8 |
| minio | 9000/9090 | minio/minio |

## New Secrets (updated)

All secrets have been updated from defaults. See `docker-compose.v3.yml` in the langfuse repository for current values.

---

## Resources

- Migration Guide: https://langfuse.com/self-hosting/upgrade-guides/upgrade-v2-to-v3
- Langfuse Docs: https://langfuse.com/docs
- ClickHouse: https://clickhouse.com/

---

## Notes

- Fresh start was chosen (no data migration from v2)
- docker-compose.v3.yml created with updated secrets
- agent-monitor setup-langfuse.sh updated to use v3
