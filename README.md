# Rosie Scanner

An AI-powered system that allows engineers to ask plain-English questions about their AWS environment and receive accurate, actionable answers.

## Overview

Rosie scans your AWS environment, indexes the inventory, and provides an intelligent chat interface powered by LangChain ReAct agents. Ask questions like:

- "What version of PostgreSQL are we running?"
- "Which Lambda functions are still on deprecated runtimes?"
- "Which EC2 instances have not been patched in 90 days?"
- "Do we have any publicly accessible databases?"
- "Which IAM roles haven't been used recently?"

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Rosie Scanner                         │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Collector  │   Storage   │    Agent    │   API / UI        │
│    Layer    │    Layer    │    Layer    │    Layer          │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ EC2         │ JSON Cache  │ ReAct Agent │ FastAPI           │
│ RDS         │ OpenSearch  │ 6 Tools     │ OpenAI-compat     │
│ Lambda      │ Vector Store│ LLMOps Eval │ Streamlit UI      │
│ ECS         │             │             │                   │
│ S3          │             │             │                   │
│ IAM         │             │             │                   │
│ SSM         │             │             │                   │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

## Quick Start

### Docker Compose (Recommended)

```bash
export OPENAI_API_KEY=your-api-key  # or use LLM_PROVIDER=bedrock
docker compose up -d
```

- API: http://localhost:8000
- UI: http://localhost:8501
- OpenSearch: http://localhost:9200

### Local Development

```bash
pip install -r requirements.txt

# Start the API
uvicorn rosie.api.main:app --reload

# Collect AWS inventory
curl -X POST http://localhost:8000/collect \
  -H "Content-Type: application/json" \
  -d '{"region": "us-east-1", "account_id": "YOUR_ACCOUNT_ID"}'

# Ask a question
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "rosie", "messages": [{"role": "user", "content": "What EC2 instances are running?"}]}'

# Launch the UI
streamlit run rosie/ui/app.py
```

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM backend: `openai`, `bedrock`, `ollama` |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-sonnet-20240229-v1:0` | AWS Bedrock model ID |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama base URL |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |
| `OPENSEARCH_HOST` | `localhost` | OpenSearch host |
| `OPENSEARCH_PORT` | `9200` | OpenSearch port |
| `ROSIE_CACHE_DIR` | `/tmp/rosie_cache` | Directory for JSON inventory cache |

## Collectors

Each collector module (EC2, RDS, Lambda, ECS, S3, IAM, SSM) returns standardized resource objects:

```json
{
  "resource_id": "i-0abc12345",
  "resource_type": "ec2:instance",
  "name": "web-server-01",
  "region": "us-east-1",
  "account_id": "123456789012",
  "details": { ... },
  "tags": { "Environment": "prod" },
  "collected_at": "2024-01-15T10:30:00+00:00"
}
```

Collectors run concurrently using `ThreadPoolExecutor(max_workers=6)`, reducing total collection time from minutes to seconds.

## Agent Tools

The ReAct agent has access to 6 tools:

1. `list_resources_by_type` — List all resources of a given type
2. `get_resource_by_id` — Get details of a specific resource
3. `search_resources` — Full-text search across all resources
4. `filter_by_region` — Filter resources by AWS region
5. `get_inventory_summary` — Count resources by type
6. `list_unpatched_instances` — Find SSM instances not recently active

## API

The API is OpenAI-compatible. You can point any OpenAI client at it:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="any")
response = client.chat.completions.create(
    model="rosie",
    messages=[{"role": "user", "content": "What EC2 instances are running?"}]
)
print(response.choices[0].message.content)
```

### Endpoints

- `GET /health` — Health check
- `GET /v1/models` — List available models
- `POST /v1/chat/completions` — OpenAI-compatible chat
- `POST /collect` — Trigger AWS inventory collection
- `GET /inventory` — View cached inventory

## Deployment (ECS Fargate)

```bash
cd terraform
terraform init
terraform plan -var="vpc_id=vpc-xxx" -var='subnet_ids=["subnet-xxx","subnet-yyy"]'
terraform apply
```

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## LLM Backends

| Provider | Config |
|---|---|
| OpenAI | Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` |
| AWS Bedrock | Set `LLM_PROVIDER=bedrock` (uses IAM role) |
| Ollama (local) | Set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL` |
