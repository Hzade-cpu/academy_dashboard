# Academy Dashboard

A Flask web application for managing sports academy centers, coaches, and financial analytics.

## Features
- **Dashboard**: View and manage centers with monthly financial data
- **Coaches Management**: Track coaches and their salaries across centers
- **Analytics**: Charts and tables for financial analysis
- **Salary Threshold**: Auto-calculates targets to keep salary ≤ 29.9% of revenue
- **Secure Login**: Password hashing, session management, rate limiting

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Access at `http://localhost:5000` or `http://YOUR_IP:5000` from other devices on the same network.

Default login: `admin` / `admin`

---

## Deployment Options

### Option 1: Render (Recommended - Free Tier)

1. **Create GitHub Repository**
   - Go to [github.com](https://github.com) and sign up/in
   - Click "New repository"
   - Name: `academy-dashboard`
   - Keep as Public or Private
   - Click "Create repository"

2. **Upload Files to GitHub**
   From your project folder, run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/academy-dashboard.git
   git push -u origin main
   ```

3. **Deploy on Render**
   - Go to [render.com](https://render.com) and sign up (use GitHub login)
   - Click "New" → "Web Service"
   - Connect your GitHub account if needed
   - Select your `academy-dashboard` repository
   - Settings:
     - Name: `academy-dashboard` (or any name)
     - Runtime: `Python 3`
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `gunicorn wsgi:app`
   - Click "Create Web Service"

4. **Set Environment Variables** (in Render dashboard)
   - Go to your service → "Environment"
   - Add: `SECRET_KEY` = (generate a random string: `python -c "import secrets; print(secrets.token_hex(32))"`)
   - Add: `PRODUCTION` = `true`

5. **Access Your App**
   - Your app will be at: `https://academy-dashboard.onrender.com`
   - Note: Free tier may sleep after 15 min of inactivity

---

### Option 2: PythonAnywhere (Free Tier)

1. **Create Account**
   - Go to [pythonanywhere.com](https://www.pythonanywhere.com)
   - Sign up for a free "Beginner" account

2. **Upload Files**
   - Go to "Files" tab
   - Create folder: `mysite` or `academy_dashboard`
   - Upload all project files (or use git clone)

3. **Create Web App**
   - Go to "Web" tab
   - Click "Add a new web app"
   - Choose "Manual configuration"
   - Select Python 3.10

4. **Configure WSGI**
   - Click on the WSGI configuration file link
   - Replace contents with:
   ```python
   import sys
   path = '/home/YOUR_USERNAME/mysite'
   if path not in sys.path:
       sys.path.append(path)
   
   from app import app as application
   ```

5. **Set Up Virtual Environment** (optional but recommended)
   - In Bash console:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 myenv
   pip install -r requirements.txt
   ```
   - In Web tab, set virtualenv path: `/home/YOUR_USERNAME/.virtualenvs/myenv`

6. **Reload Web App**
   - Click "Reload" button in Web tab
   - Access at: `https://YOUR_USERNAME.pythonanywhere.com`

---

### Option 3: Railway (Simple Deployment)

1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repository
5. Railway auto-detects Flask and deploys
6. Add environment variables in Settings

---

## Important Notes

### Database
- The SQLite database (`instance/academy.db`) is included in deployment
- For production, consider migrating to PostgreSQL for better reliability
- Free tier services may reset files periodically - backup your data!

### Security
- Change the default admin password immediately after deployment
- Set a strong `SECRET_KEY` environment variable
- HTTPS is automatic on most platforms

### Updating
- Push changes to GitHub
- Render/Railway auto-deploy on push
- PythonAnywhere: Pull changes and click "Reload"

---

## File Structure

```
academy_dashboard/
├── app.py              # Main application
├── utils.py            # Shared utilities
├── wsgi.py             # WSGI entry point
├── requirements.txt    # Python dependencies
├── Procfile            # Process file for deployment
├── runtime.txt         # Python version
├── blueprints/         # Application modules
│   ├── auth.py         # Authentication
│   ├── dashboard.py    # Dashboard views
│   ├── coaches.py      # Coach management
│   ├── analytics.py    # Analytics/reports
│   └── settings.py     # User settings
├── templates/          # HTML templates
└── instance/           # Database & secrets
    └── academy.db      # SQLite database
```

## Support

For issues, check:
1. Console/logs for error messages
2. Ensure all files are uploaded
3. Verify environment variables are set
4. Check database file permissions
