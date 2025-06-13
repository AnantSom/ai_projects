# app.py - Unified Flask app for MCQ Generator + Website Manager

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

# Load environment variables
load_dotenv()
api_key = os.getenv("MY_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")
print("Connecting to host:", os.getenv("DB_HOST"))

# Reliable DB connection with retry for Docker support
max_retries = 10
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
        print(f"⏳ Waiting for DB... ({10 - max_retries + 1}/10)")
        print(e)
        max_retries -= 1
        time.sleep(2)

if max_retries == 0:
    raise Exception("❌ Could not connect to database after 10 attempts")


# -------------------- Homepage --------------------
@app.route("/")
def homepage():
    return render_template('index.html')


# -------------------- MCQ Generator --------------------
@app.route("/mcq")
def mcq_home():
    return render_template('mcq/mcq_index.html')

@app.route("/mcq", methods=["POST"])
def mcq_generate():
    video_url = request.form.get("video_url")
    mcq_count = request.form.get("mcq_count", "5")
    embed_url = convert_to_embed_url(video_url)

    try:
        mcq_count = int(mcq_count)
        mcqs, error = generate_mcqs_from_video(video_url, mcq_count)
        if error:
            return render_template("mcq/mcq_index.html", error=error)

        encoded_json = base64.b64encode(json.dumps(mcqs).encode()).decode()
        return render_template("mcq/result.html", questions=mcqs, video_url=embed_url, answers_json=encoded_json)

    except Exception as e:
        return render_template("mcq/mcq_index.html", error=str(e))

@app.route("/mcq/submit", methods=["POST"])
def submit_answers():
    try:
        encoded_json = request.form["answers_json"]
        questions = json.loads(base64.b64decode(encoded_json).decode())
        user_answers = []
        correctness = []

        for i, q in enumerate(questions):
            selected = request.form.get(f"q{i}", "")
            user_answers.append(selected)
            correctness.append(selected == q["answer"])

        total = len(questions)
        correct = sum(correctness)
        percentage = round((correct / total) * 100, 2)

        return render_template("mcq/submission_result.html",
                               video_url=request.form.get("video_url"),
                               questions=questions,
                               user_answers=user_answers,
                               correctness=correctness,
                               score=correct,
                               total=total,
                               percentage=percentage,
                               zip=zip)

    except Exception:
        return render_template("mcq/mcq_index.html", error="Error processing answers")

def get_transcript(video_url):
    try:
        video_id = video_url.split("v=")[-1].split("&")[0]
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join([entry["text"] for entry in transcript])
    except:
        return None

def generate_mcqs_from_video(youtube_url, mcq_count):
    transcript = get_transcript(youtube_url)
    if not transcript:
        return [], "Transcript unavailable or captions missing."

    prompt = (
        f"Generate exactly {mcq_count} multiple choice questions as JSON array. "
        "Each with: 'question', 'options' (4), 'answer'. No explanation or markdown.\n\n"
        "[{\"question\": \"...\", \"options\": [...], \"answer\": \"...\"}]\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        response = model.generate_content(prompt)
        mcqs_json = response.text.strip()
        if mcqs_json.startswith("```"):
            mcqs_json = re.sub(r"^```(?:json)?|```$", "", mcqs_json.strip(), flags=re.MULTILINE).strip()
        return json.loads(mcqs_json), None
    except Exception as e:
        return [], f"Error generating MCQs: {str(e)}"

def convert_to_embed_url(youtube_url):
    parsed_url = urlparse(youtube_url)
    if "youtube.com" in parsed_url.netloc:
        video_id = parse_qs(parsed_url.query).get("v", [None])[0]
    elif "youtu.be" in parsed_url.netloc:
        video_id = parsed_url.path.lstrip("/")
    else:
        return youtube_url
    return f"https://www.youtube.com/embed/{video_id}"


# -------------------- User Auth + Website Manager --------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            return redirect('/login')
        except Exception as e:
            conn.rollback()
            return f"Signup failed: {e}"
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
            user = cur.fetchone()
            if user:
                session['username'] = username
                session['user_id'] = user[0]
                return redirect('/dashboard')
            else:
                return "Invalid credentials. <a href='/login'>Try again</a>"
        except Exception as e:
            conn.rollback()
            return f"Login error: {e}"
    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect('/login')

    message = ""

    try:
        if request.method == 'POST':
            if 'website' in request.form and 'name' in request.form:
                cur.execute("INSERT INTO websites (user_id, url, name) VALUES (%s, %s, %s)",
                            (session['user_id'], request.form['website'], request.form['name']))
                conn.commit()
                message = "Website added!"
            elif 'delete_id' in request.form:
                cur.execute("DELETE FROM websites WHERE id = %s AND user_id = %s",
                            (request.form['delete_id'], session['user_id']))
                conn.commit()
                message = "Website deleted."

        cur.execute("SELECT id, name, url FROM websites WHERE user_id = %s", (session['user_id'],))
        websites = cur.fetchall()

    except Exception as e:
        conn.rollback()
        message = f"Error: {e}"
        websites = []

    return render_template('dashboard.html', username=session['username'], websites=websites, message=message)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# -------------------- Start Flask Server --------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
