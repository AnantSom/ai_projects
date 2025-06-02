# app.py - Main Flask application
import os
import re
import base64
import json
from flask import Flask, render_template, request
from dotenv import load_dotenv
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

# Load environment variables
load_dotenv()
print("MY_API_KEY from env:", os.getenv("MY_API_KEY"))

# Configure Gemini AI
genai.configure(api_key=os.getenv("MY_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

app = Flask(__name__)

# Utility functions
def get_transcript(video_url):
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
        print (f'video_id , {video_id}')
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        print(f'received transcripts: ,{transcript}')
        text = " ".join([entry["text"] for entry in transcript])
        return text
    except Exception as e:
        print (e)
        return None

def generate_mcqs_from_video(youtube_url, mcq_count):
    transcript = get_transcript(youtube_url)
    if not transcript:
        return [], "Failed to fetch transcript. Make sure the video has captions."

    prompt = (
        f"Generate exactly {mcq_count} multiple choice questions in English as a JSON array. "
        "Each question must have:\n"
        "- a 'question' field (string)\n"
        "- an 'options' field (array of 4 strings)\n"
        "- an 'answer' field matching one of the options\n\n"
        "⚠️ Do not include any explanations, markdown formatting, or introductory text. "
        "Respond only with a valid raw JSON array like this:\n\n"
        "[\n"
        "  {\n"
        "    \"question\": \"What is 2 + 2?\",\n"
        "    \"options\": [\"2\", \"3\", \"4\", \"5\"],\n"
        "    \"answer\": \"4\"\n"
        "  }\n"
        "]\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        response = model.generate_content(prompt)
        mcqs_json = response.text.strip()

        # Clean markdown formatting if present
        if mcqs_json.startswith("```"):
            mcqs_json = re.sub(r"^```(?:json)?|```$", "", mcqs_json.strip(), flags=re.MULTILINE).strip()

        print("Gemini raw response >>>", mcqs_json)
        mcqs_data = json.loads(mcqs_json)
        return mcqs_data, None
    except json.JSONDecodeError:
        print("Gemini output (invalid JSON):", mcqs_json)
        return [], "Gemini did not return valid JSON. Try again."
    except Exception as e:
        return [], f"Error while generating MCQs: {str(e)}"

def convert_to_embed_url(youtube_url):
    parsed_url = urlparse(youtube_url)
    if "youtube.com" in parsed_url.netloc:
        query = parse_qs(parsed_url.query)
        video_id = query.get("v", [None])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
    elif "youtu.be" in parsed_url.netloc:
        video_id = parsed_url.path.lstrip("/")
        return f"https://www.youtube.com/embed/{video_id}"
    return youtube_url

# Main homepage route
@app.route("/")
def homepage():
    return render_template('index.html')

# MCQ Generator routes
@app.route("/mcq")
def mcq_home():
    return render_template('mcq/mcq_index.html')

@app.route("/mcq", methods=["POST"])
def mcq_generate():
    video_url = request.form.get("video_url")
    embed_url = convert_to_embed_url(video_url)
    mcq_count = request.form.get("mcq_count", "5")
    
    try:
        mcq_count = int(mcq_count)
        mcqs, error = generate_mcqs_from_video(video_url, mcq_count=mcq_count)
        if error:
            return render_template("mcq/mcq_index.html", error=error)
        
        encoded_json = base64.b64encode(json.dumps(mcqs).encode()).decode()
        return render_template("mcq/result.html", 
                             questions=mcqs, 
                             video_url=embed_url, 
                             answers_json=encoded_json)
    except Exception as e:
        return render_template("mcq/mcq_index.html", error=str(e))

@app.route("/mcq/submit", methods=["POST"])
def submit_answers():
    encoded_json = request.form["answers_json"]
    decoded_json = base64.b64decode(encoded_json).decode()
    questions = json.loads(decoded_json)

    user_answers = []
    correctness = []

    for i, q in enumerate(questions):
        selected = request.form.get(f"q{i}", "")
        user_answers.append(selected)
        correctness.append(selected == q["answer"])

    total = len(questions)
    correct = sum(correctness)

    return render_template("mcq/submission_result.html",
                         video_url=request.form.get("video_url"),
                         questions=questions,
                         user_answers=user_answers,
                         correctness=correctness,
                         score=correct,
                         total=total,
                         zip=zip)

# Placeholder for future projects
@app.route("/summarize")
def summarize_home():
    return "<h1>Summarize Project</h1><p>Coming soon...</p><p><a href='/'>Back to Home</a></p>"

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=10000)