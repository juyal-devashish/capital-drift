# AWS deploy plan

**Status:** not pursued. On 2026-11-17 the decision was not to deploy on AWS, and nothing was created there. The plan is kept for reference. Two of the code changes below matter for a local `docker compose` run too: the results file missing from the image, and the missing `.dockerignore` files.

## What changed since the original plan

[plan.md](plan.md) named **App Runner**. AWS closed App Runner to new customers on April 30, 2026, and recommends **Amazon ECS Express Mode** instead ([AWS notice](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)).

Express Mode sets up the pieces itself: an ECS service on Fargate, an Application Load Balancer with HTTPS, auto scaling and an AWS-provided URL. Express Mode itself costs nothing extra; you pay for the resources it creates ([AWS blog](https://aws.amazon.com/blogs/aws/build-production-ready-applications-without-infrastructure-complexity-using-amazon-ecs-express-mode/)).

Bedrock isn't needed at run time. The deployed app never calls a model: Claude's answers are computed offline with `match-llm` and loaded with the data.

## Two options

Both run the same backend image with synthetic data only.

### A. AWS showcase (recommended for FiXA: full-stack, SQL, AWS)

| Piece | AWS service | Notes |
| --- | --- | --- |
| API | ECS Express Mode on Fargate (ARM, 0.5 vCPU, 1 GB, one task) | One task, because the backend owns a background run pool (see the Dockerfile) |
| Database | RDS for PostgreSQL, db.t4g.micro, 20 GB, private subnet | The app already runs on Postgres; migrations were checked up and down on Postgres 17 |
| Frontend | S3 bucket behind CloudFront; `/api/*` forwarded to the load balancer | One origin for the browser, so no CORS changes |
| Images | ECR (private) | |
| Secrets | Secrets Manager: database URL and auth tokens | Never in the image or the repo |
| Logs | CloudWatch Logs (the app already logs JSON) | |
| Demo data | One-off ECS task: migrate, `synth --seed 7`, `match`, `match-llm --cached-only`, `warn`, `sync-queue` | The Claude cache goes in this task's image only (see below) |

**Rough monthly cost, us-east-1, on-demand list prices checked 2026-11-17:**

| Item | Calculation | About |
| --- | --- | --- |
| Fargate ARM task | 0.5 vCPU × $0.03238/h + 1 GB × $0.00356/h, × 730 h | $14 |
| Application Load Balancer | $0.0225/h × 730 h, plus a little LCU use at $0.008/LCU-h | $17–18 |
| RDS db.t4g.micro | $0.016/h × 730 h, plus about 20 GB of storage | $12 + storage |
| Public IPv4, S3, CloudFront, ECR, Secrets Manager, logs | small at demo traffic; not priced line by line | a few dollars |
| **Total** | | **roughly $45–55 a month** |

Prices are from AWS's pricing pages for [Fargate](https://aws.amazon.com/fargate/pricing/), [Elastic Load Balancing](https://aws.amazon.com/elasticloadbalancing/pricing/) and [RDS for PostgreSQL](https://aws.amazon.com/rds/postgresql/pricing/). Free-tier credits weren't checked and may lower the total.

### B. Lean

The same ECS Express Mode service, but no RDS. A SQLite database is built into the image at deploy time, so every redeploy resets the demo. That's about $35 a month, mostly the load balancer.

It's cheaper and simpler, but shows less of the AWS and SQL side.

## Code changes needed first (one commit each, all local, no AWS)

1. **Copy `backend/results/` into the backend image.** Today the results page would return a 404 in a container: the Dockerfile copies only `app/` and `migrations/`.
2. **Add `.dockerignore` files.**
   - Backend: exclude `.env`, `data/` and `.venv`. Today the whole folder, `.env` included, is sent to the Docker builder, even though only named folders are copied into the image.
   - Frontend: exclude `node_modules` and `dist`. Today `COPY . .` would copy them into the build stage.
3. **A `seed-demo` command** that runs the demo-data steps above in order and refuses to run if data already exists, unless given `--reset`.
4. **Demo users on the sign-in page from configuration**, not hard-coded.
   - The deployed page should offer only Bea (board member) and Max (property manager), with tokens you share with FiXA's founders.
   - The admin token stays private, because admin can upload files.
   - The analyst, controller and auditor users are left out: Tick & Tie's screens have no data in this demo.
5. **A demo reset.** Anyone with the manager token can change the shared queue. Options:
   - **Scheduled:** a nightly reset (EventBridge Scheduler runs the `seed-demo --reset` task).
   - **Manual:** an admin-only "reset demo" button.

**The Claude cache** (`backend/data/llm_cache/`, 232 KB of Claude's answers about synthetic invoices) is git-ignored generated data, so it stays out of the repo. It goes into the private seeding image only, built from this machine.

## Order of work once you say go

1. You confirm:
   - the AWS account and region;
   - option A or B;
   - how long it stays up;
   - a budget alarm amount;
   - a custom domain, or the AWS-provided URLs.
2. Install the AWS CLI and sign in. You do the sign-in, so credentials never pass through me.
3. Make the code changes above. Run them locally with `docker compose`, with Postgres for option A.
4. Create resources one at a time, each with your go-ahead, in this order:
   1. budget alarm;
   2. ECR;
   3. secrets;
   4. RDS;
   5. ECS Express Mode service;
   6. the seeding task;
   7. S3 and CloudFront.
5. Check the deployed site as Bea and Max, as on days 7–8. Then send you the URLs and tokens.
6. Teardown is a written list of the same resources in reverse order, so the cost stops when the application window ends.

## Decisions for you

1. Option A (about $50 a month, shows RDS) or B (about $35, simpler)?
2. Which AWS account and region? us-east-1 is assumed above.
3. How long should it run, and at what monthly amount should the budget alarm fire?
4. Should anyone with the link be able to act as the property manager (with a nightly reset), or should the manager token go only to the founders?
5. Custom domain, or the AWS-provided URLs?
