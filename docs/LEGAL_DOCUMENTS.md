# Legal Documents Setup

Guide for adding Terms of Service and Privacy Policy to your AirBeeps deployment.

## Overview

By default, the Terms & Privacy links are **hidden** on the signup form. Enable them only when you have proper legal documents.

## Quick Setup

### 1. Create Your Documents

Edit these markdown files:
- `frontend/content/en/terms.md` - Terms of Service
- `frontend/content/en/privacy.md` - Privacy Policy

### 2. Enable in Admin Panel

Go to Admin → System Config → "Show Terms & Privacy on Signup" and toggle ON.

### 3. Multi-language (Optional)

Add translations:
- `frontend/content/es/terms.md` (Spanish)
- `frontend/content/fr/privacy.md` (French)
- etc.

The app automatically shows the user's language version.

## Important Notes

⚠️ **Get Legal Review** - These documents should be reviewed by a qualified attorney before production use.

⚠️ **Update Dates** - Include "Last Updated" dates and notify users of changes.

⚠️ **Context Matters** - Legal requirements vary by:
- Your jurisdiction
- User locations (GDPR, CCPA, etc.)
- Type of data you collect
- Whether it's commercial use

## When You Don't Need Them

Skip legal docs if:
- Personal/hobby project with no other users
- Internal company tool
- Development/testing environment
- You're linking to external legal docs

## Document Templates

The placeholder files contain minimal examples. For production:

1. **Use a template service** - LegalZoom, Termly, etc.
2. **Hire a lawyer** - Especially for commercial/SaaS
3. **Copy from similar services** - But customize for your use case

## Key Sections to Include

### Terms of Service
- What your service does
- User responsibilities
- Acceptable use policy
- Limitation of liability
- Dispute resolution
- Changes to terms

### Privacy Policy
- What data you collect
- How you use it
- Who you share with
- User rights (access, delete, export)
- Data retention
- Contact information

## Testing

Before enabling:
1. Add your documents
2. Preview at `/terms` and `/privacy`
3. Verify formatting and links work
4. Enable the toggle in admin
5. Test signup flow in incognito mode
