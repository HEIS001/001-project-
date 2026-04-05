# WorkSight — Intelligent Staff Attendance Platform

## Quick Start

1. Install: `pip install flask`
2. Run: `python app.py`
3. Open: `http://localhost:5000`

## How It Works

### Company Owner
1. Click "Register Your Company" on the homepage
2. Fill in company info — then click "Capture Location" while INSIDE your building
3. You'll receive a unique Staff Join Code (e.g. AB12CD34)
4. Share this code with your staff
5. Log in to the Admin Dashboard to monitor everything

### Staff Members
1. Go to /staff
2. Enter your company join code
3. Complete 4 steps: verify → details → selfie → GPS check
4. Click Sign In or Sign Out

## AI Insights
WorkSight uses the Anthropic Claude API. To enable in production:
- Set env variable: ANTHROPIC_API_KEY=sk-ant-...
- Or add your key to the headers in app.py's ai_insight() route

## File Structure
```
worksight/
├── app.py                      Main Flask app
├── requirements.txt
├── README.md
├── instance/
│   └── worksight.db            Auto-created SQLite database
├── static/
│   ├── icons/
│   │   └── worksight-icon.svg  Website icon / favicon
│   └── selfies/                Saved staff selfies
└── templates/
    ├── index.html              Landing page + login + register
    ├── staff.html              Staff sign-in portal (4-step flow)
    └── admin.html              Admin dashboard with AI + charts
```

## Security
- Passwords hashed (SHA-256)
- GPS verified server-side
- Each company sees only its own data
- Session-based admin auth

© 2025 WorkSight
