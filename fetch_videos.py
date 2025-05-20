import os
from typing import Optional, Dict
from datetime import datetime
from isodate import parse_duration
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import openai

# Load the .env file
load_dotenv()
# After load_dotenv()
print("Environment variables check:")
print(f"SendGrid API Key present: {'Yes' if os.getenv('SENDGRID_API_KEY') else 'No'}")
print(f"From Email present: {'Yes' if os.getenv('FROM_EMAIL') else 'No'}")
print(f"To Emails present: {'Yes' if os.getenv('TO_EMAILS') else 'No'}")

# Get the keys
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CHANNEL_ID = "UC2D2CMWXMOVWx7giW1n3LIg"  # Huberman Lab Channel ID

def get_latest_videos(api_key: str, channel_id: str) -> Optional[Dict[str, str]]:
    youtube = build("youtube", "v3", developerKey=api_key)
    request = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        maxResults=1
    )
    response = request.execute()

    if response.get("items"):
        latest_video = response["items"][0]
        video_title = latest_video["snippet"]["title"]
        video_id = latest_video["id"]["videoId"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        return {"title": video_title, "url": video_url, "id": video_id}
    return None

def get_video_transcript(video_id: str) -> Optional[str]:
    """Fetches the transcript using YouTubeTranscriptApi and returns it as a string."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        formatter = TextFormatter()
        transcript_text = formatter.format_transcript(transcript_list)
        return transcript_text.strip()
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def get_video_duration(youtube, video_id: str) -> int:
    try:
        request = youtube.videos().list(
            part="contentDetails",
            id=video_id
        )
        response = request.execute()
        
        if response['items']:
            duration_str = response['items'][0]['contentDetails']['duration']  # Returns ISO 8601 duration
            duration = parse_duration(duration_str)
            return duration.total_seconds()
        return 0
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0
    
def is_video_processable(youtube, video_id: str, max_duration: int = 3600) -> bool:  # 3600 seconds = 1 hour
    duration = get_video_duration(youtube, video_id)
    if duration == 0:
        print(f"Couldn't get duration for video {video_id}")
        return False
    
    if duration > max_duration:
        print(f"Video is too long ({duration/60:.1f} minutes)")
        return False
        
    print(f"Video duration: {duration/60:.1f} minutes - Processing video...")
    return True

def is_video_processed(video_id: str) -> bool:
    json_path = '/Users/silviacarasel/Desktop/huberman_summary_app/processed_videos.json'
    try:
        with open(json_path, 'r') as f:
            processed = json.load(f)
            return video_id in processed
    except FileNotFoundError:
        return False

def mark_video_processed(video_id: str):
    json_path = '/Users/silviacarasel/Desktop/huberman_summary_app/processed_videos.json'
    try:
        try:
            with open(json_path, 'r') as f:
                processed = json.load(f)
        except FileNotFoundError:
            processed = []
        
        processed.append(video_id)
        
        with open(json_path, 'w') as f:
            json.dump(processed, f)
    except Exception as e:
        print(f"Error marking video as processed: {e}")

def summarize_transcript(transcript: str) -> Optional[str]:
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert at creating comprehensive video summaries. "
                        "Break down the content into: main topics, key points, practical takeaways, and actionable advice."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
Summarize this video transcript as if you're writing for busy professionals who don't have time to watch the full video. 
Stick to the structure below and include every section header, even if content is minimal. 
If a section has no clear information, explicitly write "No major points mentioned."

Structure:
1. Overview: (2–3 sentence summary of the video’s main theme)
2. Key Points: (bullet list of main arguments or ideas discussed)
3. Practical Takeaways: (bullet list of tips, advice, or tools viewers can apply)
4. Notable Quotes or Examples: (bullet list of memorable phrases or examples — or write "No major points mentioned")
5. Recommended Actions: (bullet list of specific next steps viewers can take — or write "No major points mentioned")

Be concise, informative, and stick to the structure.

Transcript:
{transcript}"""
                }
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error summarizing transcript: {e}")
        return None

### ### ###
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import html
import os

import re

def extract_section(text: str, title: str, next_title: str | None = None) -> str:
    """
    Returns the block of text that starts with <title> and ends before <next_title>.
    Accepts headings like:
        1. **Overview:**
        ### Overview
        Overview:
    """
    # optional prefix: ### or number. optional bold **, optional colon
    start = rf"(?:###\s*|\d+\.\s*)\*?{re.escape(title)}\*?\s*:?"
    if next_title:
        stop = rf"(?:###\s*|\d+\.\s*)\*?{re.escape(next_title)}\*?\s*:?"
        pattern = start + r"(.*?)(?=" + stop + r"|$)"
    else:        # last section
        pattern = start + r"(.*)"

    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return "Not available"
    # tidy bullets
    return match.group(1).strip().replace("- ", "<br>• ").replace("• •", "•")

def send_email(video_info: dict, summary: str):
    try:
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))

        # Clean up
        clean_summary = summary.replace('\xa0', ' ').encode('ascii', 'ignore').decode('ascii')
        clean_summary = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', clean_summary)
        clean_title = html.unescape(video_info['title'])

        overview   = extract_section(clean_summary, "Overview",   "Key Points")
        key_points = extract_section(clean_summary, "Key Points", "Practical Takeaways")
        takeaways  = extract_section(clean_summary, "Practical Takeaways", "Notable Quotes or Examples")
        quotes     = extract_section(clean_summary, "Notable Quotes or Examples", "Recommended Actions")
        actions    = extract_section(clean_summary, "Recommended Actions")

        email_content = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2>New Video Summary from Huberman Lab!</h2>
    <p><strong>Title:</strong> {clean_title}</p>
    <p><a href="{video_info['url']}" style="color: #0066cc;">Watch here!</a></p>

    <h3>Summary:</h3>
    <div style="margin-left: 20px;">
        <p><strong>Overview</strong><br><br>{extract_section(clean_summary, "Overview", "Key Points")}</p>
        <p><strong>Key Points</strong><br>{extract_section(clean_summary, "Key Points", "Practical Takeaways").replace('- ', '<br>• ')}</p>
        <p><strong>Practical Takeaways</strong><br>{extract_section(clean_summary, "Practical Takeaways", "Notable Quotes or Examples").replace('- ', '<br>• ')}</p>
        <p><strong>Notable Quotes or Examples</strong><br>{extract_section(clean_summary, "Notable Quotes or Examples", "Recommended Actions").replace('- ', '<br>• ')}</p>
        <p><strong>Recommended Actions</strong><br>{extract_section(clean_summary, "Recommended Actions").replace('- ', '<br>• ')}</p>
    </div>
</body>
</html>
"""

        message = Mail(
            from_email=os.getenv('FROM_EMAIL'),
            to_emails=os.getenv('TO_EMAILS'),
            subject=f"🧠 New Huberman Lab Summary: {clean_title}",
            html_content=email_content
        )

        response = sg.send(message)
        print(f"Email sent successfully! Status code: {response.status_code}")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_heartbeat_email():
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    message = Mail(
        from_email=os.getenv('FROM_EMAIL'),
        to_emails=os.getenv('TO_EMAILS'),
        subject='✅ Huberman Summary Script Ran',
        html_content="<p>The script ran successfully at " + datetime.now().strftime('%Y-%m-%d %H:%M') + "</p>"
    )
    sg.send(message)

if __name__ == "__main__":
    send_heartbeat_email()
    try:
        # Get latest video
        latest_video = get_latest_videos(YOUTUBE_API_KEY, CHANNEL_ID)
        if not latest_video:
            print("No videos found.")
            exit(1)
        
        # Check if video was already processed
        if is_video_processed(latest_video["id"]):
            print(f"Video {latest_video['title']} was already processed. Skipping.")
            exit(0)

        # Print video information
        print(f"Latest video: {latest_video['title']}")
        print(f"Watch it here: {latest_video['url']}")

        # Check video duration before processing
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        if not is_video_processable(youtube, latest_video["id"]):
            print("Skipping video - too long")
            exit(0)

        # Get and summarize transcript
        transcript = get_video_transcript(latest_video["id"])
        if not transcript:
            print("Transcript not available.")
            exit(1)

        print("\nTranscript fetched successfully.")
        print("Generating summary...")

        summary = summarize_transcript(transcript)
        if summary:
            print("\nSummary:")
            print("=" * 50)
            print(summary)
            print("=" * 50)
            
            # This line calls our new SendGrid function
            if send_email(latest_video, summary):
                mark_video_processed(latest_video["id"])
                print("Email sent successfully and video marked as processed!")
            else:
                print("Failed to send email.")
        else:
            print("Failed to generate summary.")

    except Exception as e:
        print(f"An error occurred: {e}")