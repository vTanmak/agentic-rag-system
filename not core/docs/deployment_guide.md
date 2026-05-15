# 🚀 Deployment Guide: GitHub & Railway

Since your local project is now perfectly stable and completely locked down, it's time to deploy it so you can share the public URL on your resume!

Follow these steps precisely to get your entire Agentic RAG system live.

---

## Step 1: Push to GitHub

First, we need to upload your code to a new GitHub repository.

1. Go to [GitHub.com](https://github.com/new) and create a new repository called `agentic-rag-system`. Leave it public, and **do not** add a README or `.gitignore` (since we already have them).
2. Open your terminal in VS Code (in the `Agentic RAG` directory) and run the following commands:

```bash
# Initialize git
git init

# Add all files (secrets are safely ignored by our .gitignore)
git add .

# Create your first commit
git commit -m "Initial commit: Agentic RAG with LangGraph and FastMCP"

# Link to your new GitHub repo (Replace YOUR_USERNAME)
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/agentic-rag-system.git

# Push the code!
git push -u origin main
```

> [!IMPORTANT]
> Verify on GitHub that your `.env` file and `uv.lock` did **NOT** upload. If you don't see them on GitHub, you are perfectly safe!

---

## Step 2: Set up Langfuse Cloud (Highly Recommended)

While we ran Langfuse locally in Docker using `docker-compose.yml`, deploying Langfuse yourself on Railway requires setting up extra databases and eats into your free tier limits. **For a portfolio project, Langfuse Cloud is vastly superior.**

1. Go to [Langfuse Cloud](https://cloud.langfuse.com/) and sign up for a free account.
2. Create a new project called `Agentic RAG`.
3. Go to **Settings -> API Keys** and generate a new set of keys.
4. Keep this tab open; you will need the `Public Key`, `Secret Key`, and `Host` for Railway.

---

## Step 3: Deploy to Railway

Railway is the easiest platform for deploying Docker containers and databases simultaneously.

### 1. Create the Railway Project
1. Go to [Railway.app](https://railway.app/) and log in with GitHub.
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `agentic-rag-system` repository.
4. Railway will automatically detect your `Dockerfile` and start building your `rag_app`.

### 2. Add PostgreSQL
Your app requires a Postgres database to store conversations and RAGAS scores.
1. In your Railway project dashboard, click **Create** -> **Database** -> **Add PostgreSQL**.
2. Railway will instantly provision a Postgres database.
3. Click on the new Postgres service, go to the **Connect** tab, and copy the `DATABASE_URL` (the Postgres Connection URL).

### 3. Add Qdrant (Vector DB)
1. In your Railway dashboard, click **Create** -> **Empty Service**.
2. Click on the new service, go to **Settings**, and scroll down to **Service Image**.
3. Set the image to `qdrant/qdrant:latest`.
4. Go to the **Variables** tab and add `QDRANT__TELEMETRY_DISABLED = true`.
5. Railway will deploy Qdrant. Notice the internal domain name railway assigns it (e.g., `qdrant.railway.internal`). You will use `http://qdrant.railway.internal:6333` as your `QDRANT_URL`.

### 4. Configure App Environment Variables
Now, link everything to your FastAPI Python app.
1. Click on your `agentic-rag-system` service in Railway.
2. Go to the **Variables** tab.
3. Click **Raw Editor** and paste your environment variables. It should look like this:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://YOUR_RAILWAY_POSTGRES_URL_HERE
QDRANT_URL=http://qdrant.railway.internal:6333

# Your LLM Keys
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key

# Your Langfuse Cloud Keys
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

> [!WARNING]
> Remember to modify the `DATABASE_URL` Railway gives you slightly. Railway gives you a URL starting with `postgresql://`. You MUST change it to `postgresql+asyncpg://` so that your async python driver can connect to it!

### 5. Expose the Public URL
1. Click your `agentic-rag-system` service.
2. Go to **Settings** -> **Networking** -> **Generate Domain**.
3. Railway will give you a public `.up.railway.app` URL.

---

## Step 4: Verification

1. Open your new public Railway URL in your browser.
2. You should see your UI!
3. Upload a test PDF, ask a question, and ensure it streams back.
4. Check your Langfuse Cloud dashboard — the trace should instantly appear!
5. Add your new public URL to the top of your GitHub `README.md` and to your resume.

> [!TIP]
> **Recording your Demo:** Once deployed, use OBS or Mac Screen Recording to record a 3-minute demo. Show a PDF upload, ask a hard question that forces the agent to re-retrieve, and then switch tabs to Langfuse to show the RAGAS scores. Upload the video to YouTube as "Unlisted" and link it on your resume. This proves it's real!
