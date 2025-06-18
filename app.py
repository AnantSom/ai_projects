# app.py - Unified Flask app for all AI projects

from flask import Flask, render_template, request, redirect, session
import os
import base64
import json
import re
from dotenv import load_dotenv
import psycopg2
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
import time

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- App Setup ---
load_dotenv()
api_key = os.getenv("MY_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

# Reliable DB connection with retry for Docker support
max_retries = 10
conn, cur = None, None
while max_retries > 0:
    try:
        db_host = os.getenv("DB_HOST", "localhost")
        conn = psycopg2.connect(
            host=db_host,
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        cur = conn.cursor()
        print("✅ Connected to PostgreSQL")
        break
    except Exception as e:
        print(f"⏳ Waiting for DB... ({11 - max_retries}/10) - {e}")
        max_retries -= 1
        time.sleep(2)
if not conn:
    raise Exception("❌ Could not connect to database after 10 attempts")


# --- Helper Functions ---
def clean_json_response(text):
    """
    Robustly finds and extracts a JSON array from the AI's response text.
    """
    start_index = text.find('[')
    end_index = text.rfind(']')
    if start_index != -1 and end_index != -1 and end_index > start_index:
        return text[start_index:end_index + 1]
    # Fallback for simple markdown cleaning
    if text.startswith("```"):
        return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return text

def convert_to_embed_url(youtube_url):
    parsed_url = urlparse(youtube_url)
    video_id = None
    if "youtube.com" in parsed_url.netloc:
        video_id = parse_qs(parsed_url.query).get("v", [None])[0]
    elif "youtu.be" in parsed_url.netloc:
        video_id = parsed_url.path.lstrip("/")
    return f"https://www.youtube.com/embed/{video_id}" if video_id else None


# --- Homepage ---
@app.route("/")
def homepage():
    return render_template('index.html')


# --- MCQ Generator (from YouTube URL) ---
def get_transcript(video_url):
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry["text"] for entry in transcript_list])
    except Exception:
        return None

@app.route("/mcq")
def mcq_video_home():
    return render_template('mcq_video_index.html')

@app.route("/mcq", methods=["POST"])
def mcq_video_generate():
    video_url = request.form.get("video_url")
    mcq_count = request.form.get("mcq_count", "5")
    embed_url = convert_to_embed_url(video_url)
    if not embed_url:
        return render_template("mcq_video_index.html", error="Invalid YouTube URL provided.")
    try:
        transcript = get_transcript(video_url)
        if not transcript:
            return render_template("mcq_video_index.html", error="Could not retrieve transcript. Video may have captions disabled.")
        prompt = (f"Generate exactly {mcq_count} multiple choice questions from transcript as a valid JSON array. Do not include markdown or any other text.\n\n{transcript}")
        response = model.generate_content(prompt)
        cleaned_text = clean_json_response(response.text)
        mcqs = json.loads(cleaned_text)
        encoded_json = base64.b64encode(json.dumps(mcqs).encode()).decode()
        return render_template("mcq_video_result.html", questions=mcqs, video_url=embed_url, answers_json=encoded_json)
    except Exception as e:
        raw_response_text = response.text if 'response' in locals() else "Response not available."
        print(f"--- ERROR: Video MCQ ---\n{e}\nRaw Response:\n{raw_response_text}\n--------------------")
        return render_template("mcq_video_index.html", error=f"An error occurred parsing the AI response: {e}")

@app.route("/mcq/submit", methods=["POST"])
def mcq_video_submit():
    try:
        encoded_json = request.form["answers_json"]
        questions = json.loads(base64.b64decode(encoded_json).decode())
        user_answers, correctness = [], []
        for i, q in enumerate(questions):
            selected = request.form.get(f"q{i}", "")
            user_answers.append(selected)
            correctness.append(selected == q["answer"])
        total, score = len(questions), sum(correctness)
        percentage = round((score / total) * 100, 2) if total > 0 else 0
        return render_template("mcq_video_submission_result.html",
                               video_url=request.form.get("video_url"), questions=questions,
                               user_answers=user_answers, correctness=correctness,
                               score=score, total=total, percentage=percentage, zip=zip)
    except Exception as e:
        return render_template("mcq_video_index.html", error=f"Error processing answers: {e}")


# --- MCQ Generator (from Topic) ---
@app.route("/mcq-topic")
def mcq_topic_home():
    return render_template('mcq_topic_index.html')

@app.route("/mcq-topic", methods=["POST"])
def mcq_topic_generate():
    topic = request.form.get("topic")
    mcq_count = request.form.get("mcq_count", "5")
    try:
        prompt = (f"Generate exactly {mcq_count} multiple-choice questions about '{topic}' as a valid JSON array. Do not include markdown or any other text.")
        response = model.generate_content(prompt)
        cleaned_text = clean_json_response(response.text) # Apply the robust cleaning
        mcqs = json.loads(cleaned_text) # Parse the cleaned text
        encoded_json = base64.b64encode(json.dumps(mcqs).encode()).decode()
        return render_template("mcq_topic_result.html", questions=mcqs, topic=topic, answers_json=encoded_json)
    except Exception as e:
        # Add the same robust error logging
        raw_response_text = response.text if 'response' in locals() else "Response not available."
        print(f"--- ERROR: Topic MCQ ---\n{e}\nRaw Response:\n{raw_response_text}\n--------------------")
        return render_template("mcq_topic_index.html", error=f"An error occurred parsing the AI response: {e}")


@app.route("/mcq-topic/submit", methods=["POST"])
def mcq_topic_submit():
    try:
        encoded_json = request.form["answers_json"]
        questions = json.loads(base64.b64decode(encoded_json).decode())
        user_answers, correctness = [], []
        for i, q in enumerate(questions):
            selected = request.form.get(f"q{i}", "")
            user_answers.append(selected)
            correctness.append(selected == q["answer"])
        total, score = len(questions), sum(correctness)
        percentage = round((score / total) * 100, 2) if total > 0 else 0
        return render_template("mcq_topic_submission_result.html",
                               topic=request.form.get("topic"), questions=questions,
                               user_answers=user_answers, correctness=correctness,
                               score=score, total=total, percentage=percentage, zip=zip)
    except Exception as e:
        return render_template("mcq_topic_index.html", error=f"Error processing answers: {e}")


# --- User Auth + Website Manager ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            return redirect('/login')
        except Exception:
            conn.rollback()
            return render_template('signup.html', error=f"Signup failed. Username might already exist.")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cur.execute("SELECT id, username FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        if user:
            session['user_id'], session['username'] = user[0], user[1]
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: return redirect('/login')
    message, websites = "", []
    try:
        if request.method == 'POST':
            user_id = session['user_id']
            if 'website' in request.form and 'name' in request.form:
                cur.execute("INSERT INTO websites (user_id, url, name) VALUES (%s, %s, %s)",
                            (user_id, request.form['website'], request.form['name']))
                message = "Website added!"
            elif 'delete_id' in request.form:
                cur.execute("DELETE FROM websites WHERE id = %s AND user_id = %s",
                            (request.form['delete_id'], user_id))
                message = "Website deleted."
            conn.commit()
        cur.execute("SELECT id, name, url FROM websites WHERE user_id = %s ORDER BY id", (session['user_id'],))
        websites = cur.fetchall()
    except Exception as e:
        conn.rollback()
        message = f"Database Error: {e}"
    return render_template('dashboard.html', username=session['username'], websites=websites, message=message)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# --- Main Execution ---
if __name__ == '__main__':
    app.run(
        debug=True,
        host=os.getenv("FLASK_RUN_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_RUN_PORT", 5000))
    )