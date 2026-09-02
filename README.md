# FastAPI using PostgreSQL (Login-Register and CRUD Application)

FastAPI is a modern, high-performance web framework for building APIs in Python based on standard type hints. This project is a backend application using FastAPI as the framework and PostgreSQL as the database.

The project uses:

- FastAPI
- PostgreSQL
- SQLModel ORM
- JWT Authentication
- CRUD Operations

Features included:

- User Registration
- User Login
- Forgot Password
- JWT Authentication & Authorization
- CRUD APIs

---

# Project Setup

## 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <project-folder>
```

---

# PostgreSQL Database Setup

Open a second terminal and run:

```bash
psql -U postgres
```

Inside PostgreSQL shell:

```sql
CREATE DATABASE dbname;
\c dbname;
```

---

# Backend Setup

## 1. Create Virtual Environment

```bash
python -m venv venv
```

## 2. Activate Virtual Environment

### Windows

```bash
venv\Scripts\activate
```

### Linux / macOS

```bash
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Database Migrations

Alembic is the only supported schema creation path. Application startup
automatically applies pending Alembic migrations before serving requests.

---

## 5. Razorpay Test Payments

Add these values to the backend environment. Never expose
`RAZORPAY_KEY_SECRET` or `RAZORPAY_WEBHOOK_SECRET` to the frontend.

```env
RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=xxxxx
RAZORPAY_WEBHOOK_SECRET=use-a-strong-random-secret-you-create-in-dashboard
PAYMENT_RECONCILIATION_ENABLED=true
PAYMENT_RECONCILIATION_INTERVAL_MINUTES=15
PAYMENT_RECONCILIATION_PENDING_MINUTES=5
PAYMENT_RECONCILIATION_STALE_HOURS=24
```

Create the webhook in Razorpay Test Mode with:

```text
https://your-backend-domain.com/payments/razorpay/webhook
```

Subscribe to `payment.captured`, `payment.failed`, and `order.paid`.

---

## 6. Run FastAPI Server

```bash
uvicorn app.main:app --reload
```

Server will start at:

```bash
http://127.0.0.1:8000
```

---

# API Documentation

After starting the server, open:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

# Structured Logging

The API emits structured JSON logs to stdout. Each non-excluded HTTP request
receives an `X-Request-ID` response header; callers may provide `X-Request-ID`
or `X-Correlation-ID` to correlate logs across services.

Logging is configured with environment variables:

```bash
SERVICE_NAME=nmk-jobportal-userservice
LOG_ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_EXCLUDED_PATHS=/health,/docs,/redoc,/openapi.json
```

Sensitive fields such as authorization headers, passwords, OTPs, tokens, API
keys, cookies, secrets, and database URLs are redacted before logs are emitted.
Request and response bodies are not logged.

To also send logs to AWS CloudWatch Logs, install the dependencies and enable
the CloudWatch handler:

```bash
CLOUDWATCH_LOGGING_ENABLED=true
CLOUDWATCH_LOG_GROUP=/nmk/jobportal/userservice
CLOUDWATCH_LOG_STREAM=
CLOUDWATCH_LOG_RETENTION_DAYS=30
AWS_REGION=us-east-1
```

If `CLOUDWATCH_LOG_STREAM` is blank, the app uses an environment/service/host/process
stream name. CloudWatch delivery is best-effort and will not fail API requests if
CloudWatch is temporarily unavailable.

The runtime IAM role or AWS credentials must allow:

```text
logs:CreateLogGroup
logs:CreateLogStream
logs:PutLogEvents
logs:DescribeLogStreams
logs:DescribeLogGroups
logs:PutRetentionPolicy
```

---

# Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLModel
- Alembic
- JWT Authentication
