# Rosie Scanner

Rosie is an AI-powered tool that lets you ask plain-English questions about your AWS environment and get accurate, actionable answers — no complex queries or dashboards required.

## Table of Contents

1. [What Does Rosie Do?](#what-does-rosie-do)
2. [Prerequisites](#prerequisites)
3. [Choosing an LLM Backend](#choosing-an-llm-backend)
4. [Quick Start](#quick-start)
   - [Option 1 — Demo Mode (No AWS Account Needed)](#option-1--demo-mode-no-aws-account-needed)
   - [Option 2 — Docker Compose with Real AWS](#option-2--docker-compose-with-real-aws)
   - [Option 3 — Local Development](#option-3--local-development)
5. [Configuration Reference](#configuration-reference)
6. [How It Works](#how-it-works)
7. [What Rosie Collects](#what-rosie-collects)
8. [What the AI Can Do](#what-the-ai-can-do)
9. [API Reference](#api-reference)
10. [Deploying to AWS (ECS Fargate)](#deploying-to-aws-ecs-fargate)
11. [Running Tests](#running-tests)

---

## What Does Rosie Do?

Rosie scans your AWS environment (EC2, RDS, Lambda, ECS, S3, IAM, SSM), stores the inventory, and exposes a chat interface powered by a LangChain ReAct agent. You can ask questions like:

- *"What version of PostgreSQL are we running?"*
- *"Which Lambda functions are still on deprecated runtimes?"*
- *"Which EC2 instances have not been patched in 90 days?"*
- *"Do we have any publicly accessible databases?"*
- *"Which IAM roles haven't been used recently?"*

Rosie answers by reasoning over the live inventory — no manual digging required.

---

## Prerequisites

Before you begin, make sure you have the following installed and available:

| Requirement | Why it's needed |
|---|---|
| [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/) | Runs the full Rosie stack (API, UI, OpenSearch) with a single command |
| [Python 3.9+](https://www.python.org/downloads/) | Required for local development |
| An LLM API key **or** a local Ollama install | Powers the AI chat — see [Choosing an LLM Backend](#choosing-an-llm-backend) |
| AWS credentials (optional) | Only needed if scanning a real AWS account — not required for demo mode |

---

## Choosing an LLM Backend

Rosie supports three AI backends. **Pick one before starting** and set the corresponding environment variables:

| Provider | When to use | Setup |
|---|---|---|
| **OpenAI** (default) | You have an OpenAI API key | `export LLM_PROVIDER=openai` and `export OPENAI_API_KEY=sk-...` |
| **AWS Bedrock** | You're on AWS and want to use Claude via IAM | `export LLM_PROVIDER=bedrock` (no extra key needed — uses your IAM role) |
| **Ollama** (local) | You want to run a local LLM with no cloud costs | `export LLM_PROVIDER=ollama` and `export OLLAMA_BASE_URL=http://localhost:11434` |

> **Not sure which to pick?** Use OpenAI if you have an API key — it's the fastest way to get started.

---

## Quick Start

Choose the setup path that matches your situation:

- **No AWS account?** → [Option 1 — Demo Mode](#option-1--demo-mode-no-aws-account-needed)
- **Have Docker + real AWS?** → [Option 2 — Docker Compose with Real AWS](#option-2--docker-compose-with-real-aws)
- **Want to run everything locally without Docker?** → [Option 3 — Local Development](#option-3--local-development)

---

### Option 1 — Demo Mode (No AWS Account Needed)

Demo mode uses [moto](https://github.com/getmoto/moto) to create a mock AWS environment with dummy resources (EC2, RDS, Lambda, ECS, S3, IAM). No real AWS account is needed. This is the easiest way to explore Rosie.

**Using Docker Compose (recommended)**

1. **Set your LLM backend.** Replace the value below with your actual API key:

   ```bash
   export OPENAI_API_KEY=your-api-key
   # If using Bedrock or Ollama instead, set LLM_PROVIDER accordingly (see Choosing an LLM Backend above)
   ```

2. **Seed the cache** — this creates fake AWS resources and saves them locally:

   ```bash
   docker compose --profile demo run --rm demo-seeder
   ```

3. **Start the full stack** — this launches the API, the Streamlit UI, and OpenSearch:

   ```bash
   docker compose up -d
   ```

4. **Open the UI** in your browser at **http://localhost:8501** and try asking:

   - *"How many EC2 instances do we have in production?"*
   - *"Which Lambda functions are running deprecated runtimes?"*
   - *"Do we have any publicly accessible RDS databases?"*
   - *"Which S3 buckets are missing public access blocks?"*
   - *"Give me a summary of all resources."*

---

**Using Local Python (no Docker)**

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Seed the cache** with mock AWS data:

   ```bash
   python demo/seed_demo.py
   ```

3. **Start the API** (this serves the AI chat endpoint):

   ```bash
   uvicorn rosie.api.main:app --reload
   # API is now running at http://localhost:8000
   ```

4. **In a separate terminal, start the UI:**

   ```bash
   streamlit run rosie/ui/app.py
   # UI is now running at http://localhost:8501
   ```

5. Open **http://localhost:8501** and start asking questions.

---

### Option 2 — Docker Compose with Real AWS

Use this option if you have Docker and want to scan your actual AWS account.

**Before you begin:** Make sure your AWS credentials are configured in your environment (e.g., via `~/.aws/credentials` or environment variables like `AWS_ACCESS_KEY_ID`).

1. **Set your LLM backend:**

   ```bash
   export OPENAI_API_KEY=your-api-key
   # or: export LLM_PROVIDER=bedrock
   ```

2. **Start the full stack:**

   ```bash
   docker compose up -d
   ```

   This starts three services:
   - **API** at http://localhost:8000
   - **UI** at http://localhost:8501
   - **OpenSearch** at http://localhost:9200

3. **Trigger an inventory scan** by calling the collect endpoint. Replace the region and account ID with your own:

   ```bash
   curl -X POST http://localhost:8000/collect \
     -H "Content-Type: application/json" \
     -d '{"region": "us-east-1", "account_id": "YOUR_ACCOUNT_ID"}'
   ```

   Rosie will scan all supported AWS services in the specified region. This may take a few seconds.

4. **Open the UI** at http://localhost:8501 and ask questions about your environment.

---

### Option 3 — Local Development

Use this option if you want to run everything locally without Docker — useful for development or making code changes.

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set your LLM backend** (see [Choosing an LLM Backend](#choosing-an-llm-backend)):

   ```bash
   export OPENAI_API_KEY=your-api-key
   ```

3. **Start the API:**

   ```bash
   uvicorn rosie.api.main:app --reload
   # API is now running at http://localhost:8000
   ```

4. **Trigger an inventory scan.** This tells Rosie to collect your AWS resource data:

   ```bash
   curl -X POST http://localhost:8000/collect \
     -H "Content-Type: application/json" \
     -d '{"region": "us-east-1", "account_id": "YOUR_ACCOUNT_ID"}'
   ```

5. **Ask a question** directly via the API (or use the UI):

   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "rosie", "messages": [{"role": "user", "content": "What EC2 instances are running?"}]}'
   ```

6. **Start the UI** in a separate terminal:

   ```bash
   streamlit run rosie/ui/app.py
   # UI is now running at http://localhost:8501
   ```

---

## Configuration Reference

All configuration is done through environment variables. Set these before starting Rosie:

| Environment Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | AI backend to use: `openai`, `bedrock`, or `ollama` |
| `OPENAI_API_KEY` | — | Your OpenAI API key (required when `LLM_PROVIDER=openai`) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-sonnet-20240229-v1:0` | AWS Bedrock model ID |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your local Ollama instance |
| `OLLAMA_MODEL` | `llama3` | Ollama model to use |
| `OPENSEARCH_HOST` | `localhost` | Hostname of the OpenSearch instance |
| `OPENSEARCH_PORT` | `9200` | Port for OpenSearch |
| `ROSIE_CACHE_DIR` | `/tmp/rosie_cache` | Where Rosie stores the JSON inventory cache |

---

## How It Works

Rosie is made up of four layers that work together:

```
┌─────────────────────────────────────────────────────────────┐
│                        Rosie Scanner                         │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Collector  │   Storage   │    Agent    │   API / UI        │
│    Layer    │    Layer    │    Layer    │    Layer          │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ EC2         │ JSON Cache  │ ReAct Agent │ FastAPI           │
│ RDS         │ OpenSearch  │ 6 Tools     │ OpenAI-compat     │
│ Lambda      │ Vector Store│ LangChain   │ Streamlit UI      │
│ ECS         │             │             │                   │
│ S3          │             │             │                   │
│ IAM         │             │             │                   │
│ SSM         │             │             │                   │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

1. **Collector Layer** — Scans AWS services concurrently and saves resource data locally.
2. **Storage Layer** — Stores inventory as JSON files and indexes it in OpenSearch for fast search.
3. **Agent Layer** — A LangChain ReAct agent reasons over the inventory using a set of tools to answer your questions.
4. **API / UI Layer** — Exposes an OpenAI-compatible API and a Streamlit chat interface.

---

## What Rosie Collects

Rosie collects data from seven AWS services: EC2, RDS, Lambda, ECS, S3, IAM, and SSM.

Each resource is stored in a standardized format:

```json
{
  "resource_id": "i-0abc12345",
  "resource_type": "ec2:instance",
  "name": "web-server-01",
  "region": "us-east-1",
  "account_id": "123456789012",
  "details": { "...": "service-specific fields" },
  "tags": { "Environment": "prod" },
  "collected_at": "2024-01-15T10:30:00+00:00"
}
```

Collectors run concurrently across all services, reducing total scan time from minutes to seconds.

---

## What the AI Can Do

The ReAct agent uses 6 built-in tools to answer questions about your inventory:

| Tool | What it does |
|---|---|
| `list_resources_by_type` | List all resources of a given type (e.g., all EC2 instances) |
| `get_resource_by_id` | Fetch full details for a specific resource |
| `search_resources` | Full-text search across all collected resources |
| `filter_by_region` | Filter resources by AWS region |
| `get_inventory_summary` | Count how many resources exist per type |
| `list_unpatched_instances` | Find EC2 instances that haven't been active in SSM recently |

The agent can combine these tools to answer multi-step questions, just like a human engineer would.

---

## API Reference

The API is OpenAI-compatible, meaning you can use any standard OpenAI client to talk to Rosie:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="any")
response = client.chat.completions.create(
    model="rosie",
    messages=[{"role": "user", "content": "What EC2 instances are running?"}]
)
print(response.choices[0].message.content)
```

### Available Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `GET` | `/v1/models` | Lists available models |
| `POST` | `/v1/chat/completions` | Send a question to the Rosie agent (OpenAI-compatible) |
| `POST` | `/collect` | Trigger an AWS inventory scan |
| `GET` | `/inventory` | View the current cached inventory |

---

## Deploying to AWS (ECS Fargate)

Rosie includes Terraform configuration for deploying to AWS ECS Fargate.

1. **Navigate to the Terraform directory:**

   ```bash
   cd terraform
   ```

2. **Initialize Terraform** (downloads required providers):

   ```bash
   terraform init
   ```

3. **Preview the planned changes** (replace the placeholder values with your VPC and subnet IDs):

   ```bash
   terraform plan -var="vpc_id=vpc-xxx" -var='subnet_ids=["subnet-xxx","subnet-yyy"]'
   ```

4. **Apply the changes** to create the AWS resources:

   ```bash
   terraform apply
   ```

---

## Running Tests

The test suite uses `pytest` and mocks AWS with `moto` so no real AWS account is needed.

1. **Install dependencies** (if you haven't already):

   ```bash
   pip install -r requirements.txt
   ```

2. **Run all tests:**

   ```bash
   pytest tests/ -v
   ```
