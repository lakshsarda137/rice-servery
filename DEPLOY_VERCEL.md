# Step-by-Step Guide: Deploy to Vercel

## Prerequisites
- A GitHub account
- Your code pushed to a GitHub repository

---

## Method 1: Deploy via Vercel Dashboard (Easiest)

### Step 1: Create Vercel Account
1. Go to [vercel.com](https://vercel.com)
2. Click **"Sign Up"**
3. Choose **"Continue with GitHub"** (recommended)
4. Authorize Vercel to access your GitHub account

### Step 2: Import Your Project
1. After logging in, click **"Add New..."** → **"Project"**
2. You'll see a list of your GitHub repositories
3. Find your `servery_picker` repository and click **"Import"**

### Step 3: Configure Project Settings
1. **Root Directory**: Set to `rice-servery` (since your app is in that folder)
   - Click **"Edit"** next to Root Directory
   - Enter: `rice-servery`
   - Click **"Continue"**

2. **Framework Preset**: Leave as "Other" (Vercel will auto-detect Python)

3. **Build Settings**: 
   - Build Command: Leave empty (Vercel handles this automatically)
   - Output Directory: Leave empty
   - Install Command: `pip install -r requirements.txt`

4. **Environment Variables**: 
   - Add if needed (you don't need any for this app)
   - Click **"Add"** for each variable if you have any

### Step 4: Deploy
1. Click **"Deploy"** button
2. Wait 1-2 minutes for deployment to complete
3. You'll see a success message with your live URL!

### Step 5: Access Your App
- Your app will be live at: `https://your-project-name.vercel.app`
- Vercel automatically creates a new deployment on every push to your main branch

---

## Method 2: Deploy via Vercel CLI (Advanced)

### Step 1: Install Vercel CLI
```bash
npm install -g vercel
```

### Step 2: Navigate to Your Project
```bash
cd /Users/LakshSarda/Desktop/servery_picker/rice-servery
```

### Step 3: Login to Vercel
```bash
vercel login
```
- This will open a browser window for authentication

### Step 4: Deploy
```bash
vercel
```

Follow the prompts:
- **Set up and deploy?** → Yes
- **Which scope?** → Your account
- **Link to existing project?** → No (first time) or Yes (if updating)
- **Project name?** → Press Enter for default or enter custom name
- **Directory?** → Press Enter (current directory is fine)
- **Override settings?** → No

### Step 5: Production Deploy
```bash
vercel --prod
```

---

## Important Configuration Files

### ✅ Already Created: `vercel.json`
Your `vercel.json` is already configured correctly:
```json
{
  "version": 2,
  "builds": [
    {
      "src": "servery_finder_web.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "servery_finder_web.py"
    }
  ],
  "env": {
    "ENV": "production"
  }
}
```

### ✅ Already Created: `requirements.txt`
Your dependencies are listed:
```
fastapi>=0.104.0
uvicorn>=0.24.0
jinja2>=3.1.0
python-multipart>=0.0.6
pytz>=2023.3
```

---

## Troubleshooting

### Issue: "Module not found" errors
**Solution**: Make sure `requirements.txt` is in the `rice-servery` directory and all dependencies are listed.

### Issue: Templates not found
**Solution**: Ensure the `templates/` folder is in the same directory as `servery_finder_web.py` (which it is).

### Issue: Build fails
**Solution**: 
1. Check Vercel build logs for specific errors
2. Make sure Python version is compatible (Vercel uses Python 3.9+)
3. Verify all imports are correct

### Issue: App works locally but not on Vercel
**Solution**:
1. Check that `vercel.json` is in the root directory (`rice-servery/`)
2. Verify the `src` path in `vercel.json` matches your file name
3. Check Vercel logs: Go to your project → "Deployments" → Click on a deployment → "Logs"

---

## Custom Domain (Optional)

### Step 1: Add Domain in Vercel
1. Go to your project in Vercel dashboard
2. Click **"Settings"** → **"Domains"**
3. Enter your domain name
4. Follow DNS configuration instructions

### Step 2: Update DNS
- Add the CNAME record Vercel provides to your domain registrar
- Wait for DNS propagation (can take up to 48 hours, usually much faster)

---

## Automatic Deployments

Vercel automatically deploys when you:
- Push to the `main` branch (production)
- Push to other branches (preview deployments)
- Open a Pull Request (preview deployment)

Each deployment gets a unique URL, so you can test before merging!

---

## Quick Checklist

Before deploying, make sure:
- [x] `vercel.json` exists in `rice-servery/` directory
- [x] `requirements.txt` exists and has all dependencies
- [x] `templates/` folder is in `rice-servery/` directory
- [x] Code is pushed to GitHub
- [x] All imports work correctly

---

## Need Help?

- Vercel Docs: [vercel.com/docs](https://vercel.com/docs)
- Vercel Support: [vercel.com/support](https://vercel.com/support)
- FastAPI on Vercel: [vercel.com/docs/functions/serverless-functions/runtimes/python](https://vercel.com/docs/functions/serverless-functions/runtimes/python)

---

## Your App Structure (for reference)

```
rice-servery/
├── servery_finder_web.py    ← Main app file
├── requirements.txt          ← Dependencies
├── vercel.json              ← Vercel config
└── templates/
    └── index.html           ← Frontend template
```

Everything is already set up correctly! Just follow Method 1 above to deploy. 🚀

