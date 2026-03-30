# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- VNC console: browser-based VNC/RDP access to VMs via noVNC and Guacamole
- JWT authentication on all API endpoints (access + refresh tokens)
- Role-based authorization (admin, user)
- Circuit breaker pattern for WinRM connections
- Docker Compose setup for PostgreSQL, Redis, and full stack
- Fernet encryption for stored hypervisor passwords
- WebSocket real-time deployment progress
- VM console access via browser (screenshot + terminal)
- Command palette and keyboard shortcuts in frontend
- Unit and integration test suite with mock mode

### Fixed
- PowerShell command injection via parameter sanitization
- Template path traversal and input sanitization
- Race conditions in concurrent deployment tasks
- Memory leaks in WebSocket connection handling
- ISO remastering encoding issues (UTF-8 BOM, UDF vs Joliet)
- Dark mode styling across all UI components
- Sidebar responsive behavior and theming

### Changed
- Database indexes optimized for common query patterns
- WebSocket authentication now requires valid JWT
- Improved observability with structured logging
- Deployment progress tracking with granular step reporting
- PowerShell commands use Base64 encoding for reliability

## [0.1.0] - 2026-02-01

### Added
- Initial release
- FastAPI backend with Celery task queue
- React/TypeScript frontend with Vite
- Hyper-V VM provisioning via WinRM
- Template engine for unattend.xml, preseed, cloud-init, kickstart
- Automated OS installation (Windows 10/11/Server, Debian, Ubuntu, Rocky)
- Alembic database migrations
