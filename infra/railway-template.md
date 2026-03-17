# Railway Multi-Tenant Deployment Guide

Each tester deploys their **own isolated Railway environment** — dedicated URL,
dedicated PostgreSQL database, and no shared state between instances.

## One-Click Deploy Architecture

```
[Tester clicks "Deploy to Railway"]
        ↓
Railway clones the repo into a fresh project
        ↓
Spins up 3 services:
  1. apollo-postgres   — PostgreSQL 16 (private, no public port)
  2. apollo-backend    — FastAPI on PORT=$PORT (Railway-assigned)
  3. apollo-frontend   — Next.js  on PORT=$PORT (Railway-assigned)
        ↓
Each service gets unique subdomain:
  frontend: https://apollo-<uuid>.up.railway.app
  backend:  https://apollo-api-<uuid>.up.railway.app
```

## Required Environment Variables (set per-service in Railway)

### backend service
| Variable          | Value                              | Notes                              |
|-------------------|------------------------------------|------------------------------------|
| `DATABASE_URL`    | Auto-filled by Railway Postgres    | Set via "Add a Variable Reference" |
| `LOG_LEVEL`       | `INFO`                             |                                    |

### frontend service
| Variable               | Value                                      | Notes              |
|------------------------|--------------------------------------------|--------------------|
| `NEXT_PUBLIC_API_URL`  | `https://<your-backend-railway-url>`       | Set after backend deploys |
| `NEXT_PUBLIC_WS_URL`   | `wss://<your-backend-railway-url>`         |                    |

### IMPORTANT: No API keys in Railway variables
Kalshi keys, BALLDONTLIE keys, and Perplexity keys are entered in the UI
at `/onboarding`. They are held **in-memory only** for the session lifetime.

## Step-by-step Deploy

1. Fork or push the `apollo-agent` repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select your fork
4. Railway auto-detects the `railway.json` and both Dockerfiles
5. Add a **PostgreSQL** plugin from the Railway dashboard
6. Set `DATABASE_URL` in the backend service to reference the PostgreSQL plugin
7. Deploy → copy the backend URL → paste into frontend `NEXT_PUBLIC_API_URL`
8. Redeploy frontend → done

## Per-Tester Isolation

To give each tester their own instance:
1. Each tester forks the repo (or you create separate Railway projects)
2. Each Railway project has its own Postgres volume — **no shared data**
3. Each tester's session keys never leave their Railway instance

## Monitoring

Railway provides:
- Automatic HTTPS termination
- Log streaming (all `logging.info` calls visible in Railway console)
- Restart on failure (`ON_FAILURE` policy in railway.json)
- Health checks on `/api/health` every 30s

## Scaling (optional)

For higher throughput, increase FastAPI workers in the backend Dockerfile:
```
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```
