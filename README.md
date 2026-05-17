# ECD Automation — ecdautomation.com

East Coast Designers | AI Automation — production website.

## Run locally

```bash
cp .env.example .env
# fill in your values in .env
npm install
node server.js
```

Open http://localhost:3000

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI chatbot |
| `META_PIXEL_ID` | Yes | Facebook/Meta Pixel ID |
| `ADMIN_PASSWORD` | No | Admin CRM password (default: `admin` — change this!) |
| `RESEND_API_KEY` | No | Resend API key for lead email notifications |
| `PORT` | No | Server port (default: 3000) |

## Deploy to Railway

1. Push this repo to GitHub
2. Create a new project in Railway → Deploy from GitHub repo
3. Add environment variables in Railway dashboard
4. Add custom domain: `ecdautomation.com`

## Namecheap DNS

After Railway provides your deployment URL, add these DNS records in Namecheap:

| Type | Host | Value |
|------|------|-------|
| CNAME | www | your-app.railway.app |
| CNAME | @ | your-app.railway.app |

SSL provisions automatically within 5-15 minutes.

## Pages

- `/` — Main landing page
- `/admin.html` — Lead CRM (login: admin / your password)
- `/privacy.html` — Privacy policy
- `/terms.html` — Terms of service

## Before launch checklist

- [ ] Replace `META_PIXEL_ID_PLACEHOLDER` in `public/index.html` with real Pixel ID
- [ ] Paste Calendly/Cal.com iframe into the `#calendarEmbed` section
- [ ] Change admin password from `admin` to something secure
- [ ] Test lead form end-to-end
- [ ] Verify Meta Pixel fires on form submit
