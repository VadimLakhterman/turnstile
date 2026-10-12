# Deployment Plan — Demo on AWS

Status: **planned, not yet provisioned**. Scope: public HTTPS demo of Turnstile on AWS (Base Sepolia testnet).

## Decision

A demo runs on a **single EC2 instance with Docker Compose** (Caddy for HTTPS, the API, Postgres in a container).
It is the cheapest option that still gives a real public HTTPS endpoint, and it tears down cleanly with `terraform destroy`.

Options considered (monthly, us-east-2, approximate):

| Option | Fixed cost | Why not for the demo |
|---|---|---|
| EKS (Auto Mode) + RDS | ~$180 | Control plane + NAT + ALB overhead for a single service |
| ECS Fargate + RDS | ~$60–90 | Right choice for production; more than a demo needs |
| Lambda + API Gateway + Aurora Serverless v2 | ~$0–40 | API Gateway's ~30 s timeout can cut off slow origins *after* the agent has paid; 6 MB response cap |
| App Runner | — | Closed to new customers since 2026-04-30 |
| **EC2 + Docker Compose** | **~$18** | Chosen. No HA and self-managed DB — acceptable for testnet |

**Upgrade path:** the same `docker/Dockerfile` image and `DATABASE_URL` move unchanged to ECS Fargate + RDS when this
stops being a demo. Add Alembic migrations before then (tables are currently created with `create_all` on startup).

## Architecture

```
Internet ──443──> Elastic IP ──> EC2 t4g.small (Amazon Linux 2023, Docker)
                                   ├─ caddy     (auto Let's Encrypt, 80→443)
                                   ├─ api       (docker/Dockerfile image from ECR)
                                   └─ postgres  (named volume on EBS)
```

## Components

### Terraform — `deploy/demo/terraform/`

- Default VPC (no NAT gateway, no ALB)
- EC2 `t4g.small` (ARM), Amazon Linux 2023, 20 GB gp3 encrypted root volume, Elastic IP
- Security group: inbound 80 and 443 only. **No port 22** — shell access via SSM Session Manager
- Instance IAM role: `AmazonSSMManagedInstanceCore` + ECR pull for the `turnstile` repository
- ECR repository `turnstile` (scan on push, keep the last 10 images)
- SSM Parameter Store SecureStrings for secrets (`PLATFORM_WALLET`, `BASE_RPC_URL`, `POSTGRES_PASSWORD`)
- `user_data`: install Docker + Compose plugin, write compose file / Caddyfile, render `.env` from SSM, `docker compose up -d`
- Route 53 `A` record → Elastic IP (only if the domain is hosted in Route 53)
- Remote state: S3 bucket with native S3 locking

### On the instance — `deploy/demo/`

- `docker-compose.demo.yml`
  - `caddy` — ports 80/443, volume for certificates
  - `api` — image from ECR, `env_file: .env`
  - `db` — `postgres:16-alpine`, named volume, not published to the host
- `Caddyfile`:
  ```
  api.<domain> {
      reverse_proxy api:8000
  }
  ```

### Deploy script — `deploy/demo/deploy.sh`

1. `docker buildx build --platform linux/arm64 -f docker/Dockerfile -t <ecr>/turnstile:<git-sha> --push .`
2. `aws ssm send-command` → on the instance: set the image tag, `docker compose pull && docker compose up -d`

Images are tagged with the git SHA; `latest` is never deployed.

### Backups (optional on testnet)

Nightly cron on the instance: `pg_dump | gzip` → small S3 bucket with a 14-day lifecycle rule.

## Rollout steps

1. Bootstrap Terraform state bucket
2. `terraform apply` — review the plan before applying
3. Store secrets in SSM Parameter Store
4. Run `deploy.sh` for the first image
5. Seed a demo client (`aws ssm start-session`, then `docker compose exec db psql ...`)
6. Verify:
   - `curl https://api.<domain>/healthz` → `{"status": "ok"}`
   - `curl -I http://api.<domain>/healthz` → redirect to HTTPS
   - `GET /v1/gateway/<client_id>` → payment instructions
   - Full flow with a Base Sepolia USDC payment → proxied response

## Cost

| Item | Monthly |
|---|---|
| EC2 `t4g.small` | ~$12 |
| EBS 20 GB gp3 | ~$2 |
| Public IPv4 (Elastic IP) | ~$4 |
| **Total (running)** | **~$18** |
| Instance stopped between demos | ~$6 |

## Open questions

1. **AWS account / profile** — existing local profiles point to the Axia account; confirm which account to use.
2. **Domain** — own domain (in Route 53?) or a free `<elastic-ip>.sslip.io` hostname.
3. **Region** — default `us-east-2`.
