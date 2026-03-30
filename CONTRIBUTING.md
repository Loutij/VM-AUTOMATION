# Contributing to VM Automation

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- Git

## Development Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd VM-AUTOMATION

# Python backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..

# Environment configuration
cp config/env.example .env
# Edit .env with your values (Hyper-V credentials, DB, Redis, etc.)

# Start infrastructure services
docker compose up -d

# Apply database migrations
alembic upgrade head

# Start backend
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend (separate terminal)
cd frontend && npm run dev
```

## Branch Naming

| Prefix | Purpose |
|--------|---------|
| `feature/xxx` | New functionality |
| `fix/xxx` | Bug fixes |
| `docs/xxx` | Documentation only |
| `refactor/xxx` | Code restructuring |

## Commit Messages

Follow the conventional commit format used in this project:

```
fix(scope): short description
feat(scope): short description
docs(scope): short description
refactor(scope): short description
```

Common scopes: `api`, `frontend`, `ui`, `deploy`, `db`, `workers`, `auth`.

## Code Style

### Python
- **Black** for formatting (`black src/`)
- **isort** for import ordering (`isort src/`)
- **Ruff** for linting (`ruff check src/`)

### TypeScript
- **ESLint** (`cd frontend && npm run lint`)
- **Prettier** for formatting

## Testing

Run tests before submitting a PR:

```bash
pytest tests/ -v --cov=src
```

See [docs/TESTING.md](docs/TESTING.md) for more details.

## Pull Request Process

1. Create a branch from `main` using the naming convention above
2. Implement your changes with appropriate tests
3. Ensure all tests pass and linting is clean
4. Open a PR against `main` with a clear description
5. Address review feedback
6. Squash-merge once approved

## Project Structure

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical architecture.
