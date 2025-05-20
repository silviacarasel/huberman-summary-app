# 🧠 Huberman Lab Summary App

This Python app monitors Andrew Huberman's YouTube channel, summarizes the latest videos using GPT, and sends the summary via email.

## 🔍 Features

- Fetch latest YouTube video from Huberman Lab
- Filter by duration (10–60 min)
- Extract transcript (even auto-generated)
- Summarize with OpenAI (GPT-4o)
- Format as HTML
- Send via SendGrid
- Track processed videos to avoid duplicates

## 🛠️ How It Works

1. Load environment variables from `.env`
2. Check latest video and duration
3. Fetch transcript using `youtube-transcript-api`
4. Summarize using GPT with structured prompt
5. Send formatted summary via SendGrid
6. Store processed video IDs in `processed_videos.json`

## 🔧 Setup

1. Clone the repo:
```bash
git clone https://github.com/yourusername/huberman-summary-app.git
cd huberman-summary-app

