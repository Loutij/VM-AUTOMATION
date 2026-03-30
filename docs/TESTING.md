# VM Automation - Testing

## Test Structure

```
tests/
├── unit/              # Fast, isolated tests (models, services, utils)
├── integration/       # Tests with DB/Redis (API endpoints, Celery tasks)
├── e2e/               # End-to-end tests (full deployment workflows)
└── conftest.py        # Shared fixtures (test DB, mock hypervisor, etc.)
```

## Running Tests

```bash
# All tests with coverage
pytest tests/ -v --cov=src

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_models.py -v

# With coverage report
pytest tests/ --cov=src --cov-report=html
```

## Mock Mode

Set `HYPERV_MOCK_MODE=true` in your `.env` to run tests without a real Hyper-V host. This is required for CI environments.

Mock mode simulates:
- WinRM connections and PowerShell execution
- VM creation, start, stop, and delete operations
- ISO remastering and VHD provisioning

## Writing New Tests

- Add shared fixtures to `tests/conftest.py`
- Use `@pytest.mark.asyncio` for async test functions
- Use `httpx.AsyncClient` for API endpoint tests
- Mock external dependencies (WinRM, file system) in unit tests

## Test Configuration

Test settings are defined in `pyproject.toml` under `[tool.pytest.ini_options]`:
- `asyncio_mode = "auto"`
- Default test paths and markers

## CI/CD Integration

GitHub Actions runs the full test suite on every PR:
- Python tests with `HYPERV_MOCK_MODE=true`
- Frontend linting (`npm run lint`)
- Type checking (`npm run typecheck`)
