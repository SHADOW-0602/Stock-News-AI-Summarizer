# 🚀 GitHub Actions Setup - 100% Free Weekly Reports

## **Step 1: Push to GitHub**

```bash
# Initialize git repository
git init
git add .
git commit -m "Add weekly market report system"

# Create GitHub repository and push
git remote add origin https://github.com/YOUR_USERNAME/Stock-News-AI-Summarizer.git
git push -u origin main
```

## **Step 2: Add Secrets to GitHub**

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

```
SENDER_EMAIL = your_gmail@gmail.com
SENDER_PASSWORD = your_gmail_app_password
SUPABASE_URL = https://your-project.supabase.co
SUPABASE_ANON_KEY = your_supabase_anon_key
```

## **Step 3: Enable GitHub Actions**

1. Go to **Actions** tab in your repository
2. Click **"I understand my workflows, go ahead and enable them"**
3. The workflow will appear as **"Weekly Market Report"**

## **Step 4: Test Manual Run**

1. Go to **Actions** → **Weekly Market Report**
2. Click **"Run workflow"** → **"Run workflow"**
3. Check the logs to ensure it works

## **Step 5: Schedule Details**

- **Runs**: Every Saturday at 9:00 AM UTC
- **Timezone**: Adjust cron in `.github/workflows/weekly-market-report.yml`
- **Manual**: Can trigger anytime via "Run workflow" button

## **Cron Schedule Examples:**

```yaml
# Every Saturday 9 AM UTC
- cron: '0 9 * * 6'

# Every Saturday 2 PM UTC (9 AM EST)
- cron: '0 14 * * 6'

# Every Sunday 6 AM UTC
- cron: '0 6 * * 0'
```

## **✅ Benefits:**

- **100% Free** - No server costs
- **No Sleep Issues** - Runs exactly on schedule
- **Reliable** - GitHub's infrastructure
- **Easy Monitoring** - View logs in Actions tab
- **Manual Control** - Trigger anytime

## **📊 What Happens:**

1. **Saturday 9 AM**: GitHub automatically runs the workflow
2. **Fetch Data**: Gets live market prices from free sources
3. **Generate Email**: Creates beautiful HTML report
4. **Send Emails**: Sends to all subscribers in database
5. **Complete**: Workflow finishes, no server needed

## **🔧 Troubleshooting:**

**If workflow fails:**
1. Check **Actions** tab for error logs
2. Verify secrets are set correctly
3. Test manual run first
4. Check email credentials

**Common Issues:**
- Gmail app password not set
- Supabase credentials wrong
- Repository not public (for free tier)

## **🎯 Ready to Use:**

Once set up, the system runs **completely automatically** every Saturday with:
- ✅ Live market data
- ✅ Beautiful email reports  
- ✅ Subscriber management
- ✅ Zero maintenance needed

**Total setup time: 5 minutes**
**Ongoing cost: $0 forever**