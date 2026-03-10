# Langfuse v2 to v3 Migration - TODO

## Status: Deferred

## Current State

- **Running Version**: Langfuse v2.95.11
- **Database**: PostgreSQL
- **Upgrade Attempted**: Failed - requires ClickHouse migration

---

## Why This is Blocked

Langfuse v3 requires:
1. **ClickHouse** - New database for analytics/metrics (mandatory)
2. **Database Migration** - v2 data needs special migration to v3 schema
3. **New Environment Variables** - `CLICKHOUSE_URL` is required

---

## Migration Steps (For When Ready)

### Prerequisites
- [ ] Read migration guide: https://langfuse.com/self-hosting/upgrade-guides/upgrade-v2-to-v3
- [ ] Backup current PostgreSQL database
- [ ] Allocate time (~1-2 hours)

### Step 1: Set Up ClickHouse
- [ ] Add ClickHouse service to docker-compose.yml
- [ ] Or use managed ClickHouse service

### Step 2: Update Configuration
- [ ] Update `docker-compose.yml` for v3
- [ ] Add required environment variables:
  - `CLICKHOUSE_URL`
  - Other v3-specific variables
- [ ] Keep v2 backup: copy current `docker-compose.yml` to `docker-compose.v2.yml`

### Step 3: Run Migration
- [ ] Stop current containers
- [ ] Run database migration
- [ ] Start v3 containers

### Step 4: Verify
- [ ] Test Langfuse access at http://localhost:3000
- [ ] Verify data integrity
- [ ] Check all features work

### Step 5: Rollback Plan (If Needed)
- [ ] Keep `docker-compose.v2.yml` as backup
- [ ] Know how to restore PostgreSQL data

---

## Resources

- Migration Guide: https://langfuse.com/self-hosting/upgrade-guides/upgrade-v2-to-v3
- Langfuse Docs: https://langfuse.com/docs
- ClickHouse: https://clickhouse.com/

---

## Notes

- Last attempt: 2026-03-10
- v3 is at version v3.157.0 (much newer than v2.95.11)
- v3 has significant new features and improvements
