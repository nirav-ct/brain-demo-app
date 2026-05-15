# Brain Demo App

A realistic microservice application for payment processing, user authentication,
and notification delivery. Built with FastAPI and PostgreSQL.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│  Auth API   │────▶│ Payment API  │────▶│ Notification Svc   │
│  /api/auth  │     │ /api/payments│     │ /svc/notifications │
└─────────────┘     └──────────────┘     └────────────────────┘
       │                    │                       │
       └────────────────────┴───────────────────────┘
                            │
                     ┌──────▼──────┐
                     │  PostgreSQL  │
                     └─────────────┘
```

## Quick Start

```bash
pip install -r requirements.txt
uvicorn src.api.auth:app --reload --port 8000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://localhost/demodb` |
| `JWT_SECRET` | Secret key for JWT signing | (required) |
| `SMTP_HOST` | SMTP server for notifications | `localhost` |
| `RATE_LIMIT_RPM` | Requests per minute limit | `60` |

## Running Tests

```bash
pytest tests/ -v --cov=src
```

## Docker

```bash
docker build -t brain-demo-app .
docker run -p 8000:8000 brain-demo-app
```
