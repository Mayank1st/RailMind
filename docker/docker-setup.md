# 🐳 RailMind Docker Setup Guide

Complete guide for running RailMind locally using Docker and deploying to GCP Cloud Run.

---

## 📋 Prerequisites

- **Docker** installed ([Download](https://www.docker.com/get-started))
- **Docker Compose** installed (comes with Docker Desktop)
- **Google Cloud CLI** for GCP deployment ([Install Guide](https://cloud.google.com/sdk/docs/install))
- **Gmail account** with App Password configured

---

## 🚀 Quick Start (Local Development)

### Step 1: Clone & Setup Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and fill in your values (especially EMAIL_USERNAME and EMAIL_PASSWORD)
nano .env
```

### Step 2: Build and Run

```bash
# Build and start all services (FastAPI + PostgreSQL + Redis + Celery)
docker-compose up --build

# Or run in detached mode (background)
docker-compose up -d --build
```

### Step 3: Run Migrations

```bash
# In a new terminal, run database migrations
docker-compose exec backend alembic upgrade head
```

### Step 4: Access the Application

- **API Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

---

## 🛠️ Useful Docker Commands

```bash
# View logs
docker-compose logs -f backend

# Stop all services
docker-compose down

# Stop and remove volumes (clears database)
docker-compose down -v

# Rebuild a specific service
docker-compose up --build backend

# Run a command inside backend container
docker-compose exec backend python -m pytest

# Access PostgreSQL shell
docker-compose exec postgres psql -U railmind -d railmind_db

# Access Redis CLI
docker-compose exec redis redis-cli
```

---

## 📦 What's Running?

| Service | Container Name | Port | Purpose |
|---------|---------------|------|---------|
| **backend** | railmind_backend | 8000 | FastAPI application |
| **postgres** | railmind_postgres | 5432 | PostgreSQL database |
| **redis** | railmind_redis | 6379 | Cache & session store |
| **celery_worker** | railmind_celery_worker | - | Background tasks |

---

## 🌐 Deploying to GCP Cloud Run

### Step 1: Setup GCP Project

```bash
# Login to GCP
gcloud auth login

# Create new project
gcloud projects create railmind-prod --name="RailMind Production"

# Set as active project
gcloud config set project railmind-prod

# Enable required APIs
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com
```

### Step 2: Configure Database (Railway.app - Recommended)

1. Go to [Railway.app](https://railway.app)
2. Create new project → Add PostgreSQL
3. Copy connection string
4. Update `.env` with Railway DATABASE_URL

**Alternative: Cloud SQL** (requires billing account)

```bash
gcloud sql instances create railmind-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=asia-south1
```

### Step 3: Configure Redis (Upstash - Recommended)

1. Go to [Upstash](https://upstash.com)
2. Create Redis database (free tier)
3. Copy connection string
4. Update `.env` with Upstash REDIS_URL

### Step 4: Build and Push Docker Image

```bash
# Configure Docker for GCP
gcloud auth configure-docker

# Build image
docker build -t gcr.io/railmind-prod/backend:latest .

# Push to Container Registry
docker push gcr.io/railmind-prod/backend:latest
```

### Step 5: Deploy to Cloud Run

```bash
# Deploy with environment variables
gcloud run deploy railmind-backend \
  --image gcr.io/railmind-prod/backend:latest \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL="your_railway_db_url" \
  --set-env-vars REDIS_URL="your_upstash_redis_url" \
  --set-env-vars JWT_SECRET_KEY="your_secret_key" \
  --set-env-vars EMAIL_USERNAME="your@gmail.com" \
  --set-env-vars EMAIL_PASSWORD="your_app_password" \
  --max-instances 10 \
  --min-instances 0 \
  --memory 512Mi \
  --cpu 1
```

### Step 6: Get Deployment URL

```bash
# Get service URL
gcloud run services describe railmind-backend --region asia-south1 --format 'value(status.url)'
```

Your API will be live at: `https://railmind-backend-xxx-uc.a.run.app`

---

## 🔒 Security Checklist

Before deploying to production:

- [ ] Change `JWT_SECRET_KEY` to a strong random value
- [ ] Use strong database passwords
- [ ] Enable HTTPS only (Cloud Run does this automatically)
- [ ] Set `DEBUG=False` in production
- [ ] Configure CORS with specific allowed origins
- [ ] Enable rate limiting
- [ ] Use secrets manager for sensitive values (optional)

---

## 📊 Monitoring & Logs

```bash
# View Cloud Run logs
gcloud run services logs read railmind-backend --region asia-south1

# Tail logs in real-time
gcloud run services logs tail railmind-backend --region asia-south1
```

---

## 💰 Cost Estimation (GCP Free Tier)

| Service | Free Tier | Estimated Cost |
|---------|-----------|----------------|
| Cloud Run | 2M requests/month | ₹0 (within free tier) |
| Container Registry | 5GB storage | ₹0 |
| Railway PostgreSQL | 500MB | ₹0 |
| Upstash Redis | 10K commands/day | ₹0 |
| Gmail SMTP | 500 emails/day | ₹0 |

**Total: ₹0/month** for learning/testing! 🎉

---

## 🐛 Troubleshooting

### Issue: Database connection failed

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### Issue: Redis connection timeout

```bash
# Check Redis status
docker-compose exec redis redis-cli ping

# Should return: PONG
```

### Issue: Port 8000 already in use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Issue: Docker build fails

```bash
# Clear Docker cache and rebuild
docker system prune -a
docker-compose build --no-cache
```

---

## 📚 Additional Resources

- [FastAPI Deployment Docs](https://fastapi.tiangolo.com/deployment/docker/)
- [GCP Cloud Run Docs](https://cloud.google.com/run/docs)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Railway.app Docs](https://docs.railway.app)

---

## 🎯 Next Steps

1. ✅ Local Docker setup working
2. ✅ Deploy to GCP Cloud Run
3. 📧 Configure email integration (Gmail SMTP)
4. 🔐 Set up authentication endpoints
5. 🚂 Implement train search
6. 🎫 Build booking flow

---

**Happy Coding! 🚀**