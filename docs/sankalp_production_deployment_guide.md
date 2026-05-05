# 🛡️ SANKALP — Production Deployment Guide
## Azure · AWS · GCP | Full Infrastructure, Dataset Connectors & Reporting

> **Author:** Dhiraj Patra | [LinkedIn](https://linkedin.com/in/dhirajpatra)  
> **Version:** 2.1 Production-Ready  
> **Platform:** Multi-Cloud (Azure / AWS / GCP) + On-Prem Hybrid Option

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Mapping: POC → Production](#2-component-mapping-poc--production)
3. [Azure Deployment (Recommended for Defence / Government)](#3-azure-deployment)
4. [AWS Deployment](#4-aws-deployment)
5. [GCP Deployment](#5-gcp-deployment)
6. [Database Layer: Neo4j + SQLite → Cloud Databases](#6-database-layer)
7. [Dataset Connectors & Ingestion Pipeline](#7-dataset-connectors--ingestion-pipeline)
8. [Report Building & BI Tools Integration](#8-report-building--bi-tools-integration)
9. [Security & Compliance](#9-security--compliance)
10. [CI/CD Pipeline](#10-cicd-pipeline)
11. [Monitoring & Observability](#11-monitoring--observability)
12. [Cost Estimates](#12-cost-estimates)
13. [Migration Checklist: POC → Production](#13-migration-checklist)

---

## 1. Architecture Overview

### Current POC Stack

```
Local Docker
├── Neo4j 5 (Community)          → Graph store
├── SQLite (3 Gold DBs)          → Relational store
├── Streamlit (single process)   → Dashboard
├── Groq/LLM (external)          → AI inference
└── APScheduler (in-process)     → Automation scheduler
```

### Production Target Architecture

```
                         ┌─────────────────────────────────┐
                         │        CDN / WAF / DDoS          │
                         │   (CloudFront / Azure Front Door  │
                         │         / Cloud Armor)            │
                         └──────────────┬──────────────────┘
                                        │
                    ┌───────────────────▼────────────────────┐
                    │         API Gateway / Load Balancer      │
                    │     (HTTPS, Auth, Rate Limiting)         │
                    └────────┬────────────────┬──────────────┘
                             │                │
              ┌──────────────▼──┐     ┌───────▼──────────────┐
              │  Streamlit App  │     │   FastAPI / MCP API   │
              │  (Container)    │     │   (Container)          │
              │  2–N replicas   │     │   2–N replicas         │
              └──────┬──────────┘     └───────┬───────────────┘
                     │                         │
         ┌───────────▼─────────────────────────▼─────────────┐
         │                  Internal VPC / VNet                │
         │  ┌──────────────────────────────────────────────┐  │
         │  │         Agent Worker Pool (K8s / ECS)         │  │
         │  │  Ganana · Shodhan · Bandhan · Bhavishyavani  │  │
         │  │  Yojana · Threat Engine · Automation Engine  │  │
         │  └───────────────────┬──────────────────────────┘  │
         │                      │                              │
         │  ┌───────────────────▼──────────────────────────┐  │
         │  │              Data Layer                        │  │
         │  │  Neo4j Enterprise (AuraDB or self-managed)   │  │
         │  │  PostgreSQL / Aurora (replaces SQLite)        │  │
         │  │  Redis (session cache / pub-sub)              │  │
         │  │  Object Storage (CSV, models, exports)        │  │
         │  └──────────────────────────────────────────────┘  │
         │                                                     │
         │  ┌──────────────────────────────────────────────┐  │
         │  │            Message Bus / Scheduler            │  │
         │  │   (SQS+Lambda / Azure Service Bus / Pub/Sub) │  │
         │  └──────────────────────────────────────────────┘  │
         └─────────────────────────────────────────────────────┘
                         │                    │
          ┌──────────────▼────┐   ┌───────────▼─────────────┐
          │  BI / Reporting   │   │   External Datasets /    │
          │  Power BI/Looker/ │   │   Airbyte / Kafka /      │
          │  Superset/Grafana │   │   REST APIs / ERP        │
          └───────────────────┘   └─────────────────────────┘
```

---

## 2. Component Mapping: POC → Production

| POC Component | Production Replacement | Why |
|---|---|---|
| SQLite (3 Gold DBs) | **PostgreSQL** (managed) | ACID, concurrent writes, JSONB, extensions |
| Neo4j Community (Docker) | **Neo4j AuraDB Enterprise** or **Self-managed cluster** | HA, backups, APOC, GDS |
| Streamlit (single process) | **Containerised Streamlit** behind ALB/AGW | Horizontal scaling, session persistence |
| APScheduler (in-process) | **Cloud Scheduler** + **Celery Workers** | Decoupled, retryable, observable |
| Docker Compose | **Kubernetes (EKS/AKS/GKE)** or **ECS Fargate** | Orchestration, auto-healing, autoscaling |
| Groq (direct) | **LLM Gateway** (AWS Bedrock / Azure OpenAI / VertexAI) | Enterprise SLA, VPC routing |
| Local `.env` secrets | **Secrets Manager** (AWS SM / Azure KV / GCP SM) | Rotation, audit logs |
| FAISS (local) | **Pinecone** / **Azure AI Search** / **Vertex Matching Engine** | Managed vector search |
| Local file storage | **S3 / Azure Blob / GCS** | Durable, versioned, lifecycle policies |
| Console logging | **CloudWatch / Azure Monitor / Cloud Logging** + **OpenTelemetry** | Centralised, alertable |

---

## 3. Azure Deployment

### Recommended for Indian Defence / Government workloads (DPDP, MeitY compliance)

### 3.1 Resource Group Layout

```
Resource Group: rg-sankalp-prod
├── Networking
│   ├── vnet-sankalp-prod (10.0.0.0/16)
│   │   ├── snet-app       (10.0.1.0/24)  ← App containers
│   │   ├── snet-data      (10.0.2.0/24)  ← Databases
│   │   ├── snet-agents    (10.0.3.0/24)  ← Worker agents
│   │   └── snet-mgmt      (10.0.4.0/24)  ← Bastion / CI
│   ├── Azure Application Gateway (WAF v2)
│   └── Azure Front Door (global CDN + DDoS)
│
├── Compute
│   ├── AKS Cluster: aks-sankalp-prod
│   │   ├── System pool:  Standard_D4s_v5 × 3
│   │   ├── App pool:     Standard_D8s_v5 × 2-10 (autoscale)
│   │   └── Agent pool:   Standard_D4s_v5 × 2-6 (autoscale)
│   └── Azure Container Registry: acrSankalpProd
│
├── Data
│   ├── Azure Database for PostgreSQL Flexible Server
│   │   └── Standard_D4ds_v5, 128 GB, HA enabled
│   ├── Neo4j AuraDB Enterprise (Azure marketplace)
│   │   └── Or: Neo4j on AKS (StatefulSet + Premium SSD P30)
│   ├── Azure Cache for Redis (Standard C2)
│   └── Azure Blob Storage (GRS, soft delete 30d)
│
├── AI / LLM
│   ├── Azure OpenAI Service (gpt-4o-mini / gpt-4o)
│   │   └── Or keep Groq via Private Link
│   └── Azure AI Search (for RAG / FAISS replacement)
│
├── Integration
│   ├── Azure Service Bus (Standard tier, 2 queues)
│   ├── Azure Event Grid (readiness events)
│   └── Azure API Management (APIM)
│
├── Security
│   ├── Azure Key Vault (secrets, certs)
│   ├── Azure Active Directory B2C (user auth)
│   ├── Microsoft Defender for Containers
│   └── Azure Policy (governance)
│
└── Observability
    ├── Azure Monitor + Log Analytics Workspace
    ├── Application Insights (APM)
    └── Azure Managed Grafana
```

### 3.2 AKS Deployment — Kubernetes Manifests

**Namespace setup:**
```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sankalp
  labels:
    app.kubernetes.io/managed-by: helm
```

**Streamlit Deployment:**
```yaml
# streamlit-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sankalp-dashboard
  namespace: sankalp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sankalp-dashboard
  template:
    metadata:
      labels:
        app: sankalp-dashboard
    spec:
      containers:
      - name: dashboard
        image: acrSankalpProd.azurecr.io/sankalp-dashboard:latest
        ports:
        - containerPort: 8501
        env:
        - name: NEO4J_URI
          valueFrom:
            secretKeyRef:
              name: sankalp-secrets
              key: neo4j-uri
        - name: NEO4J_PASSWORD
          valueFrom:
            secretKeyRef:
              name: sankalp-secrets
              key: neo4j-password
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: sankalp-secrets
              key: postgres-url
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /_stcore/health
            port: 8501
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /_stcore/health
            port: 8501
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: sankalp-dashboard-svc
  namespace: sankalp
spec:
  selector:
    app: sankalp-dashboard
  ports:
  - port: 80
    targetPort: 8501
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sankalp-dashboard-hpa
  namespace: sankalp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sankalp-dashboard
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
```

**Agent CronJobs (replace APScheduler):**
```yaml
# agents-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sankalp-pipeline-iaf
  namespace: sankalp
spec:
  schedule: "0 */6 * * *"   # every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: pipeline-runner
            image: acrSankalpProd.azurecr.io/sankalp-agents:latest
            command: ["python", "sankalp_orchestrator.py", "--branch", "iaf"]
            envFrom:
            - secretRef:
                name: sankalp-secrets
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: sankalp-readiness-monitor
  namespace: sankalp
spec:
  schedule: "* * * * *"   # every minute
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: monitor
            image: acrSankalpProd.azurecr.io/sankalp-agents:latest
            command: ["python", "-m", "agents.readiness_monitor", "--once"]
```

### 3.3 PostgreSQL Migration (SQLite → Azure PostgreSQL)

Replace the SQLite connection in all agents with:

```python
# db_connection.py  (new shared module)
import os
import psycopg2
from sqlalchemy import create_engine
from config_loader import cfg

def get_engine(branch: str = "iaf"):
    db_map = {
        "iaf":   os.getenv("IAF_DATABASE_URL",   cfg("db.iaf_url")),
        "army":  os.getenv("ARMY_DATABASE_URL",  cfg("db.army_url")),
        "navy":  os.getenv("NAVY_DATABASE_URL",  cfg("db.navy_url")),
        "auto":  os.getenv("AUTO_DATABASE_URL",  cfg("db.auto_url")),
        "alert": os.getenv("ALERT_DATABASE_URL", cfg("db.alert_url")),
    }
    return create_engine(db_map[branch], pool_pre_ping=True, pool_size=5, max_overflow=10)
```

**Schema migration with Alembic:**
```bash
pip install alembic
alembic init alembic
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

### 3.4 Terraform for Azure (IaC)

```hcl
# main.tf
terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
  }
  backend "azurerm" {
    resource_group_name  = "rg-sankalp-tfstate"
    storage_account_name = "stsankalptfstate"
    container_name       = "tfstate"
    key                  = "prod.terraform.tfstate"
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-sankalp-prod"
  location = "Central India"    # or "South India" for DR
  tags     = { environment = "production", project = "sankalp" }
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-sankalp-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "sankalp"

  default_node_pool {
    name                = "system"
    node_count          = 3
    vm_size             = "Standard_D4s_v5"
    os_disk_size_gb     = 128
    enable_auto_scaling = true
    min_count           = 3
    max_count           = 5
  }

  identity { type = "SystemAssigned" }
  network_profile { network_plugin = "azure" }
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "psql-sankalp-prod"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "16"
  administrator_login    = "sankalp_admin"
  administrator_password = var.postgres_password
  zone                   = "1"

  storage_mb = 131072   # 128 GB
  sku_name   = "GP_Standard_D4ds_v5"

  high_availability { mode = "ZoneRedundant", standby_availability_zone = "2" }
  backup { backup_retention_days = 30, geo_redundant_backup_enabled = true }
}

resource "azurerm_redis_cache" "main" {
  name                = "redis-sankalp-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 2
  family              = "C"
  sku_name            = "Standard"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
}
```

---

## 4. AWS Deployment

### 4.1 Service Selection Per Component

| Component | AWS Service | Tier/Size |
|---|---|---|
| Container Orchestration | **ECS Fargate** or **EKS** | Fargate for simplicity; EKS for complex workloads |
| Streamlit App | ECS Fargate Task | 1 vCPU / 2 GB RAM, 2–10 replicas |
| Agent Workers | ECS Fargate (scheduled tasks) | 2 vCPU / 4 GB RAM |
| PostgreSQL | **Amazon Aurora PostgreSQL Serverless v2** | 0.5–16 ACU autoscaling |
| Neo4j | **Neo4j AuraDB on AWS** (marketplace) or EC2 | r6i.2xlarge for self-managed |
| Redis | **Amazon ElastiCache for Redis** | cache.r7g.large (cluster mode) |
| Object Storage | **S3** | Standard + Intelligent-Tiering |
| Secrets | **AWS Secrets Manager** | Auto-rotation |
| LLM Inference | **Amazon Bedrock** (Claude Haiku/Sonnet) | On-demand |
| Vector Search | **Amazon OpenSearch Serverless** | Replace FAISS |
| Scheduler | **Amazon EventBridge + ECS Tasks** | Replace APScheduler |
| Message Queue | **Amazon SQS + SNS** | Standard queue |
| CDN + WAF | **CloudFront + AWS WAF** | — |
| Load Balancer | **Application Load Balancer (ALB)** | — |
| Monitoring | **CloudWatch + X-Ray + Managed Grafana** | — |
| CI/CD | **CodePipeline + CodeBuild + ECR** | — |

### 4.2 ECS Task Definition (Streamlit)

```json
{
  "family": "sankalp-dashboard",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/sankalpTaskRole",
  "containerDefinitions": [{
    "name": "dashboard",
    "image": "ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/sankalp-dashboard:latest",
    "portMappings": [{ "containerPort": 8501, "protocol": "tcp" }],
    "environment": [
      { "name": "STREAMLIT_SERVER_PORT", "value": "8501" },
      { "name": "STREAMLIT_SERVER_ADDRESS", "value": "0.0.0.0" }
    ],
    "secrets": [
      { "name": "NEO4J_URI",      "valueFrom": "arn:aws:secretsmanager:...:sankalp/neo4j:uri::" },
      { "name": "NEO4J_PASSWORD", "valueFrom": "arn:aws:secretsmanager:...:sankalp/neo4j:password::" },
      { "name": "DATABASE_URL",   "valueFrom": "arn:aws:secretsmanager:...:sankalp/postgres:url::" },
      { "name": "GROQ_API_KEY",   "valueFrom": "arn:aws:secretsmanager:...:sankalp/groq:api_key::" }
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/sankalp-dashboard",
        "awslogs-region": "ap-south-1",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
      "interval": 30,
      "timeout": 5,
      "retries": 3
    }
  }]
}
```

### 4.3 EventBridge Scheduler (Replace APScheduler)

```python
# deploy_scheduler.py  —  run once during setup
import boto3

scheduler = boto3.client("scheduler")

# IAF pipeline — every 6 hours
scheduler.create_schedule(
    Name="sankalp-iaf-pipeline",
    ScheduleExpression="rate(6 hours)",
    FlexibleTimeWindow={"Mode": "OFF"},
    Target={
        "Arn": "arn:aws:ecs:ap-south-1:ACCOUNT:cluster/sankalp-prod",
        "RoleArn": "arn:aws:iam::ACCOUNT:role/SchedulerECSRole",
        "EcsParameters": {
            "TaskDefinitionArn": "arn:aws:ecs:...:task-definition/sankalp-agents:LATEST",
            "LaunchType": "FARGATE",
            "TaskCount": 1,
            "NetworkConfiguration": {
                "awsvpcConfiguration": {
                    "Subnets": ["subnet-AGENT"],
                    "SecurityGroups": ["sg-agents"],
                    "AssignPublicIp": "DISABLED"
                }
            }
        },
        "Input": json.dumps({"command": ["python", "sankalp_orchestrator.py", "--branch", "iaf"]})
    }
)
```

### 4.4 Terraform for AWS

```hcl
# aws_main.tf
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~>5.0"
  name    = "sankalp-prod"
  cidr    = "10.0.0.0/16"
  azs             = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
  enable_nat_gateway     = true
  single_nat_gateway     = false   # HA
  enable_vpn_gateway     = false
}

module "aurora_postgresql" {
  source  = "terraform-aws-modules/rds-aurora/aws"
  version = "~>9.0"
  name    = "sankalp-aurora-prod"
  engine  = "aurora-postgresql"
  engine_version = "16.2"
  instance_class = "db.serverless"
  instances      = { 1 = {}, 2 = {} }
  vpc_id         = module.vpc.vpc_id
  db_subnet_group_name = module.vpc.database_subnet_group_name
  
  serverlessv2_scaling_configuration = {
    min_capacity = 0.5
    max_capacity = 16
  }

  storage_encrypted = true
  deletion_protection = true
  backup_retention_period = 30
}

module "elasticache_redis" {
  source  = "terraform-aws-modules/elasticache/aws"
  version = "~>1.0"
  cluster_id           = "sankalp-redis"
  engine               = "redis"
  node_type            = "cache.r7g.large"
  num_cache_nodes      = 2
  automatic_failover_enabled = true
  vpc_id               = module.vpc.vpc_id
  subnet_ids           = module.vpc.private_subnets
}
```

---

## 5. GCP Deployment

### 5.1 Service Selection Per Component

| Component | GCP Service | Tier/Size |
|---|---|---|
| Container Orchestration | **GKE Autopilot** | Fully managed |
| Streamlit App | GKE workload / **Cloud Run** | Cloud Run for simplicity |
| Agent Workers | **Cloud Run Jobs** + **Cloud Scheduler** | — |
| PostgreSQL | **Cloud SQL for PostgreSQL** (HA) | db-perf-optimized-N-4 |
| Neo4j | **Neo4j AuraDB** (GCP marketplace) | Business Critical tier |
| Redis | **Memorystore for Redis** | Standard tier 5 GB |
| Object Storage | **Cloud Storage** | Standard + Autoclass |
| Secrets | **Secret Manager** | — |
| LLM | **Vertex AI** (Gemini 1.5 Flash) or keep Groq | — |
| Vector Search | **Vertex AI Matching Engine** | Replace FAISS |
| Scheduler | **Cloud Scheduler** + **Pub/Sub** | — |
| CDN + WAF | **Cloud Armor + Cloud CDN** | — |
| Load Balancer | **Global External HTTPS LB** | — |
| Monitoring | **Cloud Monitoring + Cloud Logging** | — |
| CI/CD | **Cloud Build + Artifact Registry** | — |

### 5.2 Cloud Run Deployment (Simplest GCP Option)

```yaml
# cloud-run-streamlit.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: sankalp-dashboard
  annotations:
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "2"
        autoscaling.knative.dev/maxScale: "20"
        run.googleapis.com/vpc-access-connector: projects/PROJECT/locations/REGION/connectors/sankalp-connector
        run.googleapis.com/vpc-access-egress: private-ranges-only
    spec:
      containerConcurrency: 10
      timeoutSeconds: 3600
      containers:
      - image: REGION-docker.pkg.dev/PROJECT/sankalp/dashboard:latest
        ports:
        - containerPort: 8501
        resources:
          limits:
            cpu: "2"
            memory: "4Gi"
        env:
        - name: NEO4J_URI
          valueFrom:
            secretKeyRef:
              name: neo4j-uri
              key: latest
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-url
              key: latest
```

**Deploy command:**
```bash
gcloud run deploy sankalp-dashboard \
  --image=REGION-docker.pkg.dev/PROJECT/sankalp/dashboard:latest \
  --region=asia-south1 \
  --platform=managed \
  --memory=4Gi \
  --cpu=2 \
  --min-instances=2 \
  --max-instances=20 \
  --vpc-connector=sankalp-connector \
  --no-allow-unauthenticated \
  --service-account=sankalp-sa@PROJECT.iam.gserviceaccount.com
```

### 5.3 Cloud Run Jobs for Agents

```bash
# Create agent job
gcloud run jobs create sankalp-iaf-pipeline \
  --image=REGION-docker.pkg.dev/PROJECT/sankalp/agents:latest \
  --region=asia-south1 \
  --memory=4Gi \
  --cpu=2 \
  --max-retries=3 \
  --task-timeout=3600s \
  --command="python" \
  --args="sankalp_orchestrator.py,--branch,all"

# Schedule it
gcloud scheduler jobs create http sankalp-pipeline-schedule \
  --location=asia-south1 \
  --schedule="0 */6 * * *" \
  --uri="https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT/jobs/sankalp-iaf-pipeline:run" \
  --oauth-service-account-email=sankalp-sa@PROJECT.iam.gserviceaccount.com
```

---

## 6. Database Layer

### 6.1 SQLite → PostgreSQL Migration

**Code changes required in `shodhan.py`, `bhavishyavani.py`, `automation_engine.py`, `readiness_monitor.py`:**

```python
# Before (POC)
import sqlite3
conn = sqlite3.connect("data/processed/sankalp_gold.db")
df = pd.read_sql("SELECT * FROM aircraft_gold", conn)

# After (Production)
from db_connection import get_engine   # new module above
engine = get_engine("iaf")
with engine.connect() as conn:
    df = pd.read_sql("SELECT * FROM aircraft_gold", conn)
```

**Schema initialisation (run once):**
```sql
-- PostgreSQL production schema
CREATE SCHEMA IF NOT EXISTS iaf;
CREATE SCHEMA IF NOT EXISTS army;
CREATE SCHEMA IF NOT EXISTS navy;
CREATE SCHEMA IF NOT EXISTS automation;
CREATE SCHEMA IF NOT EXISTS alerts;

-- IAF tables (example)
CREATE TABLE iaf.aircraft_gold (
    aircraft_id         TEXT PRIMARY KEY,
    aircraft_type       TEXT,
    squadron            TEXT,
    last_maintenance_date DATE,
    flight_hours        NUMERIC(10,2),
    readiness_base_score NUMERIC(5,2),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_aircraft_squadron ON iaf.aircraft_gold(squadron);
CREATE INDEX idx_aircraft_readiness ON iaf.aircraft_gold(readiness_base_score);
```

### 6.2 Neo4j: AuraDB vs Self-Managed

**Option A — Neo4j AuraDB Enterprise (Recommended)**

- Available on all three cloud marketplaces
- Fully managed backups, upgrades, HA, monitoring
- VPC peering supported (private connectivity)
- Cost: ~$1,500–5,000/month depending on size
- Connection string format: `neo4j+s://xxxxx.databases.neo4j.io`

**Option B — Self-Managed on Kubernetes**

```yaml
# neo4j-statefulset.yaml (simplified)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j
  namespace: sankalp
spec:
  serviceName: neo4j
  replicas: 3   # cluster of 3
  template:
    spec:
      containers:
      - name: neo4j
        image: neo4j:5-enterprise
        env:
        - name: NEO4J_AUTH
          valueFrom:
            secretKeyRef:
              name: sankalp-secrets
              key: neo4j-auth
        - name: NEO4J_ACCEPT_LICENSE_AGREEMENT
          value: "yes"
        - name: NEO4J_dbms_mode
          value: CORE
        - name: NEO4J_causalClustering_minimumCoreClusterSizeAtFormation
          value: "3"
        volumeMounts:
        - name: data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      storageClassName: premium-ssd   # Azure / managed-premium / pd-ssd
      accessModes: [ReadWriteOnce]
      resources:
        requests:
          storage: 500Gi
```

---

## 7. Dataset Connectors & Ingestion Pipeline

Replace the CSV-only ingestion with a proper enterprise connector layer.

### 7.1 Airbyte (Open-Source EL Platform)

Airbyte can ingest from 300+ sources into PostgreSQL/Neo4j.

**Deploy Airbyte on K8s:**
```bash
helm repo add airbyte https://airbytehq.github.io/helm-charts
helm install airbyte airbyte/airbyte \
  --namespace sankalp-airbyte \
  --set global.database.type=external \
  --set global.database.host=YOUR_PG_HOST
```

**Supported connectors relevant to SANKALP:**

| Data Source | Airbyte Connector | Use Case |
|---|---|---|
| CSV files (S3/Blob/GCS) | S3 / Azure Blob / GCS Source | Current CSV workflow |
| REST APIs | HTTP / Generic REST | External defence data APIs |
| Oracle / SQL Server | Oracle Source / MSSQL Source | Legacy ERP systems |
| MySQL / PostgreSQL | Native connectors | Operational databases |
| SAP | SAP HANA Source | Supply chain / logistics |
| Excel / SharePoint | Microsoft SharePoint | Manual data uploads |
| Kafka | Kafka Source | Real-time telemetry streams |
| Salesforce | Salesforce Source | Asset management |

**Example Airbyte connection (S3 CSV → PostgreSQL):**
```python
# airbyte_sync.py  — trigger via API
import requests

AIRBYTE_URL = "http://airbyte-server:8001/api/v1"

def trigger_sync(connection_id: str):
    resp = requests.post(
        f"{AIRBYTE_URL}/connections/sync",
        json={"connectionId": connection_id},
        headers={"Authorization": f"Bearer {AIRBYTE_TOKEN}"}
    )
    return resp.json()
```

### 7.2 Apache Kafka (Real-Time Streaming)

For real-time telemetry (aircraft sensors, vessel AIS, etc.):

```python
# agents/kafka_consumer.py  — new production agent
from confluent_kafka import Consumer
import json

class SankalpKafkaConsumer:
    def __init__(self, topics: list[str]):
        self.consumer = Consumer({
            "bootstrap.servers": os.getenv("KAFKA_BROKERS"),
            "group.id": "sankalp-ingestion",
            "security.protocol": "SASL_SSL",
            "sasl.mechanism": "PLAIN",
            "sasl.username": os.getenv("KAFKA_USERNAME"),
            "sasl.password": os.getenv("KAFKA_PASSWORD"),
            "auto.offset.reset": "latest",
        })
        self.consumer.subscribe(topics)

    def consume_and_ingest(self):
        while True:
            msg = self.consumer.poll(1.0)
            if msg and not msg.error():
                data = json.loads(msg.value())
                # Route to appropriate Ganana agent
                if msg.topic() == "iaf.aircraft.telemetry":
                    self._ingest_iaf(data)
                elif msg.topic() == "army.asset.telemetry":
                    self._ingest_army(data)
```

### 7.3 Adding New Dataset Types

To add a new dataset (e.g., maintenance logs from an ERP), create a new Ganana agent:

```python
# agents/ganana_erp.py
"""
Ganana-ERP – Ingests maintenance records from Oracle ERP via REST API
"""
import requests
import pandas as pd
from db_connection import get_engine

ERP_BASE_URL = os.getenv("ERP_BASE_URL")
ERP_TOKEN    = os.getenv("ERP_TOKEN")

def ingest_maintenance_logs(branch: str = "iaf") -> dict:
    resp = requests.get(
        f"{ERP_BASE_URL}/api/maintenance/records",
        headers={"Authorization": f"Bearer {ERP_TOKEN}"},
        params={"branch": branch, "from_date": "2024-01-01"}
    )
    df = pd.DataFrame(resp.json()["records"])
    
    engine = get_engine(branch)
    df.to_sql("maintenance_logs_raw", engine, if_exists="replace", index=False, schema=branch)
    return {"rows": len(df), "source": "erp"}
```

Register it in `config.yml`:
```yaml
connectors:
  erp:
    enabled: true
    schedule: "0 */4 * * *"
    branches: [iaf, army, navy]
  kafka:
    enabled: true
    topics:
      - iaf.aircraft.telemetry
      - army.asset.position
      - navy.vessel.ais
  airbyte:
    enabled: true
    connections:
      iaf_csv: "conn-uuid-iaf"
      army_csv: "conn-uuid-army"
```

---

## 8. Report Building & BI Tools Integration

### 8.1 Power BI (Best for Azure / Microsoft environment)

**Option A — DirectQuery from Neo4j:**
```
Neo4j → Power BI Neo4j Connector (marketplace) → Live dashboards
```

**Option B — Export to PostgreSQL → Power BI Gateway:**
```bash
# In Bhavishyavani / Shodhan — write to reporting schema
CREATE MATERIALIZED VIEW reporting.readiness_summary AS
SELECT
    'IAF' as branch,
    aircraft_id as asset_id,
    aircraft_type as asset_type,
    squadron as unit,
    final_readiness_score,
    CASE
        WHEN final_readiness_score >= 5  THEN 'Operational'
        WHEN final_readiness_score >= 3  THEN 'Watch'
        ELSE 'Critical'
    END as status,
    updated_at
FROM iaf.aircraft_readiness
UNION ALL
SELECT 'Army', asset_id, asset_type, unit, final_readiness_score, ... FROM army.asset_readiness
UNION ALL
SELECT 'Navy', vessel_id, vessel_type, flotilla, final_readiness_score, ... FROM navy.vessel_readiness;

-- Refresh every 15 minutes
REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.readiness_summary;
```

Power BI connects to this view via **Power BI Gateway (on-prem)** or direct PostgreSQL connector.

### 8.2 Apache Superset (Open-Source, Self-Hosted)

Best for teams wanting full control, works on all clouds.

```bash
# Deploy Superset alongside SANKALP
helm repo add superset https://apache.github.io/superset
helm install superset superset/superset \
  --namespace sankalp-bi \
  --set configOverrides.secret="YOUR_SECRET" \
  --set env.DATABASE_DB=superset \
  --set env.DATABASE_HOST=YOUR_PG_HOST
```

**Connect Superset to SANKALP databases:**
```python
# In Superset Admin → Databases → +Database
# SQLAlchemy URI examples:
# PostgreSQL (readiness data):
postgresql+psycopg2://user:pass@pg-host:5432/sankalp

# Neo4j (via neo4j-sqlalchemy driver):
neo4j+bolt://user:pass@neo4j-host:7687/neo4j
```

**Superset charts to build:**
- Fleet Readiness Heatmap (branch × squadron × score)
- Mission Timeline (area chart by type)
- Operational Status Donut (per branch)
- Doctrine Evaluation Table
- Threat Scenario Coverage Bar

### 8.3 Grafana (Operational Monitoring + Business Metrics)

```yaml
# grafana-datasource.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasources
data:
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: SANKALP PostgreSQL
      type: postgres
      url: pg-host:5432
      database: sankalp
      user: grafana_ro
      secureJsonData:
        password: "${PG_GRAFANA_PASSWORD}"
      jsonData:
        sslmode: require
        postgresVersion: 1600

    - name: SANKALP Neo4j
      type: hamedkhan23-neo4j-datasource   # community plugin
      url: bolt://neo4j-host:7687
      jsonData:
        neo4jVersion: "5"

    - name: Prometheus
      type: prometheus
      url: http://prometheus:9090
```

**Key Grafana Dashboards to build:**
- Live Readiness Gauges (IAF / Army / Navy) — refresh every 30s
- Pipeline Execution Metrics (Ganana / Shodhan / Bandhan run times)
- Alert History Timeline
- Agent Worker Queue Depth
- LLM API Latency & Token Usage

### 8.4 Looker Studio / Google Looker (GCP)

For GCP deployments, connect Looker Studio directly to:
- BigQuery export of readiness data (scheduled via Dataflow)
- Cloud SQL (PostgreSQL) via Looker Studio connector

```python
# agents/bigquery_export.py  —  GCP only
from google.cloud import bigquery

def export_readiness_to_bq(engine):
    client = bigquery.Client()
    
    df = pd.read_sql("SELECT * FROM reporting.readiness_summary", engine)
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("branch", "STRING"),
            bigquery.SchemaField("asset_id", "STRING"),
            bigquery.SchemaField("final_readiness_score", "FLOAT"),
            bigquery.SchemaField("status", "STRING"),
        ]
    )
    
    client.load_table_from_dataframe(
        df,
        "PROJECT.sankalp_reporting.readiness_summary",
        job_config=job_config
    ).result()
```

### 8.5 MCP Server as a Universal Data API

The existing `mcp_server.py` already exposes SANKALP data via the MCP protocol. In production, deploy it as an authenticated HTTP endpoint and connect it to:

- **Claude for Teams / Enterprise** — instant AI-powered natural language querying
- **Custom internal portals** — embed MCP tool responses in React/Next.js dashboards
- **Slack / Teams bots** — `evaluate_doctrine("northern infiltration")` via slash commands

```python
# mcp_server_production.py — add auth middleware
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer

app = FastAPI()
security = HTTPBearer()

@app.middleware("http")
async def verify_token(request, call_next):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not verify_jwt(token):  # implement with python-jose
        raise HTTPException(status_code=401)
    return await call_next(request)
```

---

## 9. Security & Compliance

### 9.1 Network Security

```
Internet
  └── DDoS Protection (Always-on)
        └── WAF (OWASP rules, geo-blocking)
              └── CDN (CloudFront / Azure Front Door / Cloud Armor)
                    └── ALB / AGW (HTTPS only, TLS 1.2+)
                          └── VPC/VNet (private subnets only for app + data)
                                └── NSG / Security Groups (deny-by-default)
```

### 9.2 Authentication & Authorisation

```python
# auth.py  —  Add to Streamlit app
import streamlit as st
from msal import ConfidentialClientApplication   # Azure AD
# or: from google.oauth2 import id_token          # GCP
# or: import boto3 cognito                        # AWS

def require_auth():
    """Gate entire Streamlit app behind SSO."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        # Redirect to IdP login
        auth_url = get_auth_url()   # implement per cloud IdP
        st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', 
                    unsafe_allow_html=True)
        st.stop()
```

**Role mapping (RBAC):**
```python
ROLES = {
    "admin":         ["read", "write", "delete", "ontology_edit", "admin"],
    "analyst":       ["read", "ontology_query"],
    "operator":      ["read", "mission_log", "alert_ack"],
    "readonly":      ["read"],
}
```

### 9.3 Secrets Management

**Never put secrets in `config.yml` or `.env` files in production.** Use cloud-native secrets:

```python
# secrets.py  —  unified secrets loader
import os

def get_secret(name: str) -> str:
    cloud = os.getenv("CLOUD_PROVIDER", "local")
    
    if cloud == "azure":
        from azure.keyvault.secrets import SecretClient
        from azure.identity import DefaultAzureCredential
        client = SecretClient(vault_url=os.getenv("KEY_VAULT_URL"),
                              credential=DefaultAzureCredential())
        return client.get_secret(name).value
    
    elif cloud == "aws":
        import boto3
        sm = boto3.client("secretsmanager")
        return sm.get_secret_value(SecretId=name)["SecretString"]
    
    elif cloud == "gcp":
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{os.getenv('GCP_PROJECT')}/secrets/{name}/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode("utf-8")
    
    else:
        return os.getenv(name)   # local dev fallback
```

### 9.4 Data Encryption

- **At rest:** Enable storage encryption on all database services (AES-256)
- **In transit:** TLS 1.2+ everywhere; Neo4j uses `neo4j+s://` (bolt+tls)
- **Application-level:** Encrypt PII fields before writing to PostgreSQL using `pgcrypto`

---

## 10. CI/CD Pipeline

### 10.1 GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: SANKALP CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: sankalp

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: pip install -r requirements.txt pytest
    - run: pytest tests/ -v --tb=short

  build:
    needs: test
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [dashboard, agents]
    steps:
    - uses: actions/checkout@v4
    - name: Build & push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        file: Dockerfile.${{ matrix.service }}
        push: true
        tags: |
          ${{ env.REGISTRY }}/dhirajpatra/sankalp-${{ matrix.service }}:latest
          ${{ env.REGISTRY }}/dhirajpatra/sankalp-${{ matrix.service }}:${{ github.sha }}

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
    - name: Deploy to staging (EKS/AKS/GKE)
      run: |
        kubectl set image deployment/sankalp-dashboard \
          dashboard=${{ env.REGISTRY }}/dhirajpatra/sankalp-dashboard:${{ github.sha }} \
          --namespace=sankalp-staging

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production   # requires manual approval
    steps:
    - name: Deploy to production
      run: |
        kubectl set image deployment/sankalp-dashboard \
          dashboard=${{ env.REGISTRY }}/dhirajpatra/sankalp-dashboard:${{ github.sha }} \
          --namespace=sankalp
```

### 10.2 Dockerfile Split (POC has one; production needs two)

```dockerfile
# Dockerfile.dashboard  —  Streamlit UI only
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir streamlit neo4j pandas altair folium streamlit-folium python-dotenv psycopg2-binary redis
COPY agents/ ./agents/
COPY config.yml config_loader.py ./
EXPOSE 8501
HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health
CMD ["streamlit", "run", "agents/darshan.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```dockerfile
# Dockerfile.agents  —  Pipeline workers only
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agents/ ./agents/
COPY config.yml config_loader.py sankalp_orchestrator.py ./
CMD ["python", "sankalp_orchestrator.py"]
```

---

## 11. Monitoring & Observability

### 11.1 OpenTelemetry Instrumentation

```python
# telemetry.py  —  add to every agent
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def init_telemetry(service_name: str):
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

# Usage in Ganana agent
tracer = init_telemetry("sankalp.ganana")

def ingest():
    with tracer.start_as_current_span("ganana.ingest") as span:
        span.set_attribute("branch", "iaf")
        # ... existing ingest code
```

### 11.2 Key Metrics to Alert On

| Metric | Warning Threshold | Critical Threshold | Alert Channel |
|---|---|---|---|
| Readiness score drop (any branch) | > 10% drop in 1h | > 20% drop in 1h | PagerDuty / Slack |
| Pipeline failure | 1 failed run | 2 consecutive failures | Slack |
| Neo4j query latency | > 500ms avg | > 2s avg | Email |
| Dashboard error rate | > 1% | > 5% | Slack |
| LLM API latency | > 3s p99 | > 10s p99 | Email |
| DB connection pool saturation | > 70% | > 90% | PagerDuty |

---

## 12. Cost Estimates

### 12.1 Azure (Monthly, Production — India region)

| Service | Config | Est. Cost (USD/month) |
|---|---|---|
| AKS (System pool 3×D4s_v5) | Always-on | ~$600 |
| AKS (App pool 2–10×D4s_v5) | Autoscale | ~$400–2,000 |
| PostgreSQL Flexible (D4ds_v5, HA) | 128 GB | ~$450 |
| Neo4j AuraDB Enterprise | 16 GB RAM | ~$800–1,500 |
| Redis Cache (C2 Standard) | — | ~$150 |
| Azure Blob Storage (1 TB) | GRS | ~$50 |
| Azure OpenAI (if used) | 1M tokens/day | ~$200–600 |
| Application Gateway (WAF v2) | — | ~$250 |
| Front Door (Standard) | — | ~$100 |
| Log Analytics + AppInsights | 10 GB/day | ~$150 |
| **Total** | | **~$3,200–6,000/month** |

### 12.2 AWS (Monthly, ap-south-1)

| Service | Config | Est. Cost (USD/month) |
|---|---|---|
| ECS Fargate (Dashboard, 2 tasks) | 1vCPU/2GB | ~$120 |
| ECS Fargate (Agents, 4 tasks) | 2vCPU/4GB | ~$240 |
| Aurora PostgreSQL Serverless v2 | 0.5–16 ACU | ~$200–800 |
| Neo4j AuraDB Business Critical | 16 GB | ~$800–1,500 |
| ElastiCache Redis (r7g.large) | 2 nodes | ~$300 |
| S3 (1 TB) | Standard | ~$25 |
| Amazon Bedrock (if used) | 1M tokens/day | ~$150–400 |
| ALB + CloudFront + WAF | — | ~$150 |
| CloudWatch + X-Ray | — | ~$100 |
| **Total** | | **~$2,100–4,200/month** |

### 12.3 GCP (Monthly, asia-south1)

| Service | Config | Est. Cost (USD/month) |
|---|---|---|
| Cloud Run (Dashboard) | 2 vCPU / 4 GB, min 2 | ~$150 |
| Cloud Run Jobs (Agents) | 2 vCPU / 4 GB | ~$100 |
| Cloud SQL PostgreSQL (HA) | db-perf-N-4, 128 GB | ~$400 |
| Neo4j AuraDB (GCP marketplace) | Business Critical | ~$800–1,500 |
| Memorystore Redis (5 GB) | Standard | ~$200 |
| Cloud Storage (1 TB) | Standard | ~$25 |
| Vertex AI (Gemini Flash) | 1M tokens/day | ~$75–200 |
| Cloud Armor + LB | — | ~$100 |
| Cloud Monitoring | — | ~$80 |
| **Total** | | **~$1,900–3,600/month** |

> **GCP is typically cheapest** for this workload. **Azure is preferred** for Indian defence / government compliance (MeitY, NIC Cloud Policy).

---

## 13. Migration Checklist: POC → Production

### Phase 1: Infrastructure Setup (Week 1–2)
- [ ] Choose cloud provider and region
- [ ] Set up VPC/VNet with private subnets
- [ ] Deploy managed PostgreSQL (HA)
- [ ] Deploy Neo4j AuraDB (or self-managed cluster)
- [ ] Deploy Redis cache
- [ ] Configure secrets manager
- [ ] Set up container registry
- [ ] Set up Kubernetes cluster or ECS

### Phase 2: Code Hardening (Week 2–3)
- [ ] Replace SQLite with PostgreSQL in all agents
- [ ] Replace `sqlite3.connect()` with SQLAlchemy `get_engine()`
- [ ] Run Alembic migrations
- [ ] Replace APScheduler with cloud scheduler (EventBridge / Cloud Scheduler / AKS CronJob)
- [ ] Add `secrets.py` module — remove all hardcoded values from code
- [ ] Split `Dockerfile` into `dashboard` and `agents` images
- [ ] Add health check endpoints
- [ ] Add OpenTelemetry instrumentation
- [ ] Write unit tests for all agents (`tests/` directory)

### Phase 3: CI/CD & Deployment (Week 3–4)
- [ ] Configure GitHub Actions (or Azure DevOps / Cloud Build)
- [ ] Build and push Docker images to container registry
- [ ] Deploy to staging environment
- [ ] Run integration tests against staging
- [ ] Configure autoscaling policies
- [ ] Set up WAF rules and DDoS protection
- [ ] Enable SSO authentication (Azure AD / Cognito / GCP IAP)
- [ ] Configure RBAC roles

### Phase 4: Data Connectors (Week 4–5)
- [ ] Deploy Airbyte (or managed alternative)
- [ ] Configure S3 / Blob / GCS sources (replace CSV file drops)
- [ ] Set up Kafka cluster (if real-time telemetry needed)
- [ ] Add ERP / external API connectors via new Ganana agents
- [ ] Schedule all ingestion pipelines
- [ ] Validate data lineage end-to-end

### Phase 5: Reporting & BI (Week 5–6)
- [ ] Create `reporting` schema in PostgreSQL with materialised views
- [ ] Deploy Superset or connect Power BI / Looker
- [ ] Build core dashboards (readiness, missions, doctrine)
- [ ] Deploy Grafana for operational metrics
- [ ] Set up MCP Server as authenticated HTTP endpoint
- [ ] Configure alert routing (PagerDuty / Slack / Teams)

### Phase 6: Go-Live (Week 6–8)
- [ ] Load test (target: 100 concurrent users, < 3s p95 response)
- [ ] DR drill (failover to standby region)
- [ ] Security penetration test
- [ ] Compliance review (DPDP / ISO 27001 / MeitY if applicable)
- [ ] User acceptance testing with IAF / Army / Navy stakeholders
- [ ] Go-live with canary deployment (5% → 25% → 100% traffic)
- [ ] Enable production monitoring & alerting
- [ ] Hand over runbook to operations team

---

## Quick Start Commands

### Azure
```bash
# Clone and setup
git clone https://github.com/dhirajpatra/sankalp.git && cd sankalp

# Deploy infrastructure
cd infra/azure && terraform init && terraform apply

# Build and push images
az acr login --name acrSankalpProd
docker build -f Dockerfile.dashboard -t acrSankalpProd.azurecr.io/sankalp-dashboard:latest .
docker push acrSankalpProd.azurecr.io/sankalp-dashboard:latest

# Deploy to AKS
az aks get-credentials --resource-group rg-sankalp-prod --name aks-sankalp-prod
kubectl apply -f k8s/
```

### AWS
```bash
# Authenticate ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS \
  --password-stdin ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com

# Build and push
docker build -f Dockerfile.dashboard -t sankalp-dashboard:latest .
docker tag sankalp-dashboard:latest ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/sankalp-dashboard:latest
docker push ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/sankalp-dashboard:latest

# Deploy infrastructure
cd infra/aws && terraform init && terraform apply

# Update ECS service
aws ecs update-service --cluster sankalp-prod --service sankalp-dashboard \
  --force-new-deployment
```

### GCP
```bash
# Authenticate and set project
gcloud auth configure-docker asia-south1-docker.pkg.dev
gcloud config set project YOUR_PROJECT_ID

# Build and push
docker build -f Dockerfile.dashboard \
  -t asia-south1-docker.pkg.dev/PROJECT/sankalp/dashboard:latest .
docker push asia-south1-docker.pkg.dev/PROJECT/sankalp/dashboard:latest

# Deploy
gcloud run deploy sankalp-dashboard \
  --image=asia-south1-docker.pkg.dev/PROJECT/sankalp/dashboard:latest \
  --region=asia-south1 --platform=managed --min-instances=2
```

---

*Built for Indian Defence — जय हिन्द 🇮🇳*  
*Contact: [dhirajpatra](https://linkedin.com/in/dhirajpatra) | MIT License*
