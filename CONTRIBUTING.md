# Contributing to Airbeeps

Thank you for your interest in contributing to Airbeeps! We welcome contributions from the community.

## Getting Started

For detailed setup instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

### Quick Setup

**Prerequisites:**
- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20+ with [pnpm](https://pnpm.io/)
- Git

**Install dependencies:**

```bash
# Linux/macOS
make install

# Windows (PowerShell)
cd backend && uv sync --all-groups && cd ..
cd frontend && pnpm install && cd ..
pre-commit install
```

## Development Workflow

### 1. Fork and Clone

Fork the repository and clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/airbeeps.git
cd airbeeps
```

### 2. Create a Branch

Create a feature branch from `main`:

```bash
git checkout -b feature/your-feature-name
```

Use clear branch names:
- `feature/add-something` for new features
- `fix/fix-something` for bug fixes
- `docs/update-something` for documentation

### 3. Make Changes

Write your code following our standards:

- **Python**: Formatted with Ruff (Black-compatible), type hints encouraged
- **TypeScript/Vue**: Formatted with Prettier, TypeScript strict mode
- **Commit messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/)

**Examples:**
```
feat(chat): add streaming response support
fix(auth): resolve token refresh race condition
docs: update API documentation
```

### 4. Run Quality Checks

Before committing, ensure your code passes all checks:

```bash
# Linux/macOS
make check

# Windows (PowerShell)
cd backend && uv run ruff check . && uv run ruff format . && uv run mypy && cd ..
cd frontend && pnpm check && cd ..
```

**Run tests:**

```bash
# Backend tests
cd backend && uv run pytest

# Frontend tests
cd frontend && pnpm test:unit
```

### 5. Commit and Push

Pre-commit hooks will automatically run checks:

```bash
git add .
git commit -m "feat(scope): your change description"
git push origin feature/your-feature-name
```

### 6. Open a Pull Request

1. Go to the [Airbeeps repository](https://github.com/airbeeps/airbeeps)
2. Click "New Pull Request"
3. Select your branch
4. Fill in the PR template with:
   - Clear description of changes
   - Related issue numbers (if any)
   - Screenshots (for UI changes)
   - Test coverage

## Code Review Process

- Maintainers will review your PR
- Address feedback and push updates
- Once approved, your PR will be merged

## Project Structure

```
airbeeps/
├── backend/           # FastAPI backend
│   ├── airbeeps/     # Main package
│   ├── tests/        # Backend tests
│   └── scripts/      # Utility scripts
├── frontend/         # Nuxt 3 frontend
│   ├── app/          # Application code
│   └── tests/        # Frontend tests
└── docs/             # Documentation
```

## Testing

We maintain comprehensive test coverage:

- **Backend**: pytest with async support
- **Frontend**: Vitest (unit) + Playwright (e2e)
- **Test mode**: Use `AIRBEEPS_TEST_MODE=1` to avoid external API calls

See [DEVELOPMENT.md](DEVELOPMENT.md#testing) for detailed testing instructions.

## Reporting Issues

Found a bug or have a feature request?

1. Check [existing issues](https://github.com/airbeeps/airbeeps/issues)
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior
   - Environment details (OS, Python/Node versions)

## Security Issues

**Do not** report security vulnerabilities in public issues. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## Questions?

- **Documentation**: Check [docs/](docs/) and [DEVELOPMENT.md](DEVELOPMENT.md)
- **Discussions**: Use [GitHub Discussions](https://github.com/airbeeps/airbeeps/discussions) for questions
- **Chat**: Join our community (link coming soon)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Thank you for contributing to Airbeeps! 🚀
