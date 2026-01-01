# Security Policy

## Supported Versions

Airbeeps is currently in early development (v0.x). We provide security updates for:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

**Note**: As an alpha project, we recommend using the latest version from the `main` branch for production deployments and monitoring releases closely.

## Reporting a Vulnerability

We take security issues seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, use one of these private channels:

#### Option 1: GitHub Security Advisories (Recommended)

1. Go to the [Security tab](https://github.com/airbeeps/airbeeps/security) of this repository
2. Click "Report a vulnerability"
3. Fill in the advisory form with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

#### Option 2: Email (Alternative)

Send details to: **security@example.com** (replace with your actual security contact)

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Your name/contact (optional, for credit)

### What to Expect

- **Initial Response**: Within 48 hours
- **Status Update**: Within 5 business days
- **Fix Timeline**: Depends on severity
  - Critical: Within 7 days
  - High: Within 14 days
  - Medium/Low: Next minor release

### Disclosure Policy

- We will acknowledge your report within 48 hours
- We will work with you to understand and validate the issue
- We will prepare a fix and coordinate a release timeline
- We will publicly disclose the vulnerability after a fix is released
- We will credit you in the security advisory (unless you prefer to remain anonymous)

## Security Best Practices

When deploying Airbeeps:

### Required Security Measures

1. **Change Default Secrets**
   ```bash
   # Generate a strong secret key
   AIRBEEPS_SECRET_KEY=$(openssl rand -hex 32)
   ```

2. **Use HTTPS in Production**
   - Deploy behind a reverse proxy (nginx, Caddy, Traefik)
   - Obtain SSL/TLS certificates (Let's Encrypt, CloudFlare)
   - Set `AIRBEEPS_EXTERNAL_URL` to your HTTPS domain

3. **Secure Database**
   - Use PostgreSQL/MySQL for production (not SQLite)
   - Use strong database passwords
   - Restrict database network access

4. **Environment Variables**
   - Never commit `.env` files to version control
   - Use secure secret management (Vault, AWS Secrets Manager, etc.)
   - Rotate secrets regularly

5. **Email Configuration**
   - Enable email verification: `AIRBEEPS_MAIL_ENABLED=true`
   - Use app-specific passwords for Gmail/SMTP
   - Verify SPF/DKIM records

### Recommended Measures

- **CORS Configuration**: Restrict `AIRBEEPS_FRONTEND_URL` to your actual domain
- **Rate Limiting**: Deploy behind Cloudflare or use a reverse proxy with rate limits
- **Regular Updates**: Monitor releases and apply security patches promptly
- **Backup Strategy**: Regular backups of database and file storage
- **Monitoring**: Enable logging and monitor for suspicious activity

### OAuth Providers

When using OAuth:
- Use official OAuth apps (not test/dev credentials)
- Restrict redirect URIs to your production domain
- Keep OAuth client secrets secure
- Review OAuth scopes and minimize permissions

### File Uploads

- The `MAX_FILE_SIZE` limit is configurable (default 10MB)
- Allowed extensions are whitelisted (see `docs/configuration.md`)
- Files are scanned for content type mismatches
- Consider additional virus scanning for production

## Known Security Considerations

### Alpha Software Notice

Airbeeps is in **alpha** (v0.x). While we follow security best practices, the codebase is rapidly evolving:

- APIs may change without notice
- Security features are still maturing
- Thorough security audits have not yet been conducted

**Production Use**: Evaluate risks carefully and implement additional security layers (WAF, monitoring, backups).

### LLM API Keys

- API keys for LLM providers (OpenAI, Anthropic, etc.) are stored in the database
- Ensure database backups are encrypted
- Use API key restrictions (IP allowlists, usage quotas) at the provider level
- Consider using separate API keys per environment

### Admin Access

- First registered user becomes an admin
- Secure your deployment during initial setup
- Regularly audit admin accounts
- Consider disabling user registration after initial setup via system config

## Security Updates

Security patches will be announced via:
- GitHub Security Advisories
- Release notes in [CHANGELOG.md](CHANGELOG.md)
- Repository notifications (watch releases)

Subscribe to release notifications to stay informed.

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers who help improve Airbeeps security:

- Hall of Fame (coming soon)

---

Thank you for helping keep Airbeeps and its users safe! 🔒
