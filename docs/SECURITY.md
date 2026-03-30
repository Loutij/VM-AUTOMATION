# VM Automation - Security

## Authentication

- **JWT tokens**: All API endpoints require a valid JSON Web Token
- **Access token**: Short-lived (configurable via `JWT_EXPIRATION_MINUTES`), used for API requests
- **Refresh token**: Longer-lived, used to obtain new access tokens without re-authentication
- Login via `POST /auth/login` returns both tokens

## Authorization

- **Role-based access control**: Two roles — `admin` and `user`
- Admins can manage hypervisors, templates, and system settings
- Users can deploy and manage their own VMs

## Password Handling

- User passwords are hashed with **bcrypt** before storage
- Passwords are never logged or returned in API responses
- Default VM credentials are documented separately (see HANDOFF.md)

## Secrets & Encryption

- Hypervisor passwords are encrypted at rest using **Fernet** symmetric encryption
- Encryption key is derived from `SECRET_KEY` in the environment
- See `src/common/crypto.py` for implementation

## API Security

- **CORS**: Restricted to configured origins (`CORS_ORIGINS` in .env)
- **Rate limiting**: Applied to authentication endpoints to prevent brute force
- **Security headers**: Standard headers (X-Content-Type-Options, X-Frame-Options, etc.)
- **Input validation**: Pydantic models validate all request payloads
- **PowerShell injection prevention**: All parameters passed to WinRM are sanitized

## WebSocket Security

- WebSocket connections at `/ws/realtime` require a valid JWT token
- Token is validated on connection handshake
- Unauthorized connections are rejected immediately

## Environment Variables

- **Never commit `.env` files** — `.gitignore` excludes them
- Use `config/env.example` as a template
- Sensitive values: `SECRET_KEY`, `HYPERV_PASSWORD`, `DATABASE_URL`, `REDIS_URL`
- See [ENV_REFERENCE.md](ENV_REFERENCE.md) for all variables

## Vulnerability Reporting

If you discover a security vulnerability:

1. **Do not** open a public issue
2. Email the maintainers with a description and reproduction steps
3. Allow reasonable time for a fix before any public disclosure
