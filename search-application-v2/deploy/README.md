# FastAPI Deployment Guide

## Prerequisites

- `flyctl` installed locally
- Fly account, logged in (`fly auth login`)
- The prod DuckDB file: `indo_swiss_research.duckdb` (~1.3–2 GB) available locally on Windows desktop

## First-Time Setup

### 1. Initialize the Fly app

```bash
cd search-application-v2
fly launch --no-deploy
```

When prompted:
- App name: accept default or override to `indoswisscollab`
- Region: select `cdg` (Paris)
- Do NOT create a Postgres database
- Do NOT generate a Dockerfile (we provide one)

### 2. Create the data volume

```bash
fly volumes create isrd_data --region cdg --size 3
```

The 3GB size accommodates the ~1.5–2 GB DuckDB file plus write overhead.

### 3. Deploy the app (without DB)

```bash
fly deploy
```

The app will start but searches will fail until the DuckDB file is present.

### 4. Upload the DuckDB file

**Option A: Interactive SFTP**

```bash
fly ssh console
mkdir -p /data
exit

fly ssh sftp shell
put D:\Projects\indo-swiss-collab\ingestion\output\indo_swiss_research.duckdb /data/indo_swiss_research.duckdb
quit
```

(Adjust the local path to match where your DuckDB file lives.)

**Option B: Non-interactive SFTP**

```bash
fly ssh sftp put D:\Projects\indo-swiss-collab\ingestion\output\indo_swiss_research.duckdb /data/indo_swiss_research.duckdb
```

### 5. Restart the app

```bash
fly apps restart indoswisscollab
```

### 6. Verify

```bash
fly open
```

Search for a known institution, e.g. "ETH Zurich". You should see ~3,448 publications.

## Subsequent Deploys

For code changes, redeploy in one command:

```bash
fly deploy
```

The data volume persists.

## Updating the DuckDB File

Use the same SFTP procedure as step 4 above, then optionally restart:

```bash
fly apps restart indoswisscollab
```

(Restart not strictly needed unless the app is holding an old file handle, but it is fast.)

## DNS Cutover (indoswisscollab.org)

1. **Add the domain to Fly:**
   ```bash
   fly certs add indoswisscollab.org
   fly certs add www.indoswisscollab.org
   ```

2. **Get Fly's IP addresses:**
   ```bash
   fly ips list
   ```

3. **Update DNS at your registrar:**
   - Set A record (IPv4) to the Fly IPv4 address, or
   - Set CNAME on `www` → `indoswisscollab.fly.dev` and ALIAS/ANAME on apex → same

4. **Verify the certificate:**
   ```bash
   fly certs check indoswisscollab.org
   ```
   Wait until you see "Verified" and "Issued".

5. **Test:**
   ```
   https://indoswisscollab.org
   ```

## Troubleshooting

**App crashes on startup:**
- Check logs: `fly logs`
- Likely cause: `ISRD_DB_PATH` points to missing file. Verify the DuckDB file is on the volume via `fly ssh console` and `ls -lh /data/`.

**Out of memory (OOM):**
- Update `fly.toml`: change `memory_mb = 1024` to `memory_mb = 2048`
- Redeploy: `fly deploy`

**Slow after cold start:**
- The app sleeps when idle. First request after sleep takes ~10–15 seconds. This is normal.
- To keep the app always-on, set `min_machines_running = 1` in `fly.toml` and redeploy.

**Rollback to a previous version:**
```bash
fly releases
fly releases revert <version>
```

## Volume Management

To inspect the volume:

```bash
fly ssh console
ls -lh /data/
```

To delete and recreate it (data loss):

```bash
fly volumes delete isrd_data
fly volumes create isrd_data --region cdg --size 3
```

Do this only if corruption is suspected.
