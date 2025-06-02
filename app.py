# app.py - Main Flask application
import os
import re
import base64
import json
import logging
from flask import Flask, render_template, request
from dotenv import load_dotenv
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("MY_API_KEY")
logger.debug(f"Loading API key from environment: {'Found' if api_key else 'Not found'}")
if api_key:
    logger.debug(f"API key length: {len(api_key)} characters")
else:
    logger.error("MY_API_KEY not found in environment variables")

# Configure Gemini AI
try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    logger.debug("Gemini AI configured successfully")
except Exception as e:
    logger.error(f"Failed to configure Gemini AI: {e}")
    raise

app = Flask(__name__)
logger.debug("Flask app initialized")

# Utility functions
def get_transcript(video_url):
    logger.debug(f"Attempting to get transcript for URL: {video_url}")
    try:
        # Extract video ID
        video_id = video_url.split("v=")[-1].split("&")[0]
        logger.debug(f"Extracted video ID: {video_id}")
        
        # Fetch transcript
        logger.debug("Calling YouTubeTranscriptApi.get_transcript()")
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        logger.debug(f"Successfully received transcript with {len(transcript)} entries")
        
        # Process transcript
        text = " ".join([entry["text"] for entry in transcript])
        logger.debug(f"Processed transcript length: {len(text)} characters")
        logger.debug(f"First 100 characters of transcript: {text[:100]}...")
        
        return text
    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        logger.debug(f"Exception type: {type(e).__name__}")
        return None

def generate_mcqs_from_video(youtube_url, mcq_count):
    logger.debug(f"Starting MCQ generation for URL: {youtube_url}, count: {mcq_count}")
    
    # Get transcript
    transcript = get_transcript(youtube_url)
    if not transcript:
        logger.error("Failed to fetch transcript")
        return [], "Failed to fetch transcript. Make sure the video has captions."

    logger.debug("Building prompt for Gemini AI")
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
    logger.debug(f"Prompt length: {len(prompt)} characters")

    try:
        logger.debug("Sending request to Gemini AI")
        response = model.generate_content(prompt)
        mcqs_json = response.text.strip()
        logger.debug(f"Received response from Gemini AI, length: {len(mcqs_json)} characters")

        # Clean markdown formatting if present
        original_json = mcqs_json
        if mcqs_json.startswith("```"):
            logger.debug("Detected markdown formatting, cleaning...")
            mcqs_json = re.sub(r"^```(?:json)?|```$", "", mcqs_json.strip(), flags=re.MULTILINE).strip()
            logger.debug("Markdown formatting cleaned")

        logger.debug(f"Raw Gemini response: {mcqs_json}")
        
        # Parse JSON
        logger.debug("Attempting to parse JSON response")
        mcqs_data = json.loads(mcqs_json)
        logger.debug(f"Successfully parsed JSON with {len(mcqs_data)} questions")
        
        # Validate structure
        for i, mcq in enumerate(mcqs_data):
            logger.debug(f"Question {i+1}: {mcq.get('question', 'NO QUESTION')[:50]}...")
            if not all(key in mcq for key in ['question', 'options', 'answer']):
                logger.warning(f"Question {i+1} missing required fields")
        
        return mcqs_data, None
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}")
        logger.debug(f"Invalid JSON content: {mcqs_json}")
        return [], "Gemini did not return valid JSON. Try again."
    except Exception as e:
        logger.error(f"Error during MCQ generation: {e}")
        logger.debug(f"Exception type: {type(e).__name__}")
        return [], f"Error while generating MCQs: {str(e)}"

def convert_to_embed_url(youtube_url):
    logger.debug(f"Converting URL to embed format: {youtube_url}")
    
    parsed_url = urlparse(youtube_url)
    logger.debug(f"Parsed URL - netloc: {parsed_url.netloc}, path: {parsed_url.path}")
    
    if "youtube.com" in parsed_url.netloc:
        logger.debug("Detected youtube.com URL")
        query = parse_qs(parsed_url.query)
        video_id = query.get("v", [None])[0]
        if video_id:
            embed_url = f"https://www.youtube.com/embed/{video_id}"
            logger.debug(f"Converted to embed URL: {embed_url}")
            return embed_url
    elif "youtu.be" in parsed_url.netloc:
        logger.debug("Detected youtu.be URL")
        video_id = parsed_url.path.lstrip("/")
        embed_url = f"https://www.youtube.com/embed/{video_id}"
        logger.debug(f"Converted to embed URL: {embed_url}")
        return embed_url
    
    logger.warning(f"Could not convert URL to embed format, returning original: {youtube_url}")
    return youtube_url

# Main homepage route
@app.route("/")
def homepage():
    logger.debug("Homepage accessed")
    return render_template('index.html')

# MCQ Generator routes
@app.route("/mcq")
def mcq_home():
    logger.debug("MCQ home page accessed")
    return render_template('mcq/mcq_index.html')

@app.route("/mcq", methods=["POST"])
def mcq_generate():
    logger.debug("MCQ generation POST request received")
    
    # Get form data
    video_url = request.form.get("video_url")
    mcq_count = request.form.get("mcq_count", "5")
    logger.debug(f"Form data - video_url: {video_url}, mcq_count: {mcq_count}")
    
    # Convert URL
    embed_url = convert_to_embed_url(video_url)
    
    try:
        mcq_count = int(mcq_count)
        logger.debug(f"MCQ count converted to integer: {mcq_count}")
        
        # Generate MCQs
        logger.debug("Starting MCQ generation process")
        mcqs, error = generate_mcqs_from_video(video_url, mcq_count=mcq_count)
        
        if error:
            logger.error(f"MCQ generation failed: {error}")
            return render_template("mcq/mcq_index.html", error=error)
        
        logger.debug(f"MCQ generation successful, got {len(mcqs)} questions")
        
        # Encode for template
        logger.debug("Encoding MCQs to base64 JSON")
        encoded_json = base64.b64encode(json.dumps(mcqs).encode()).decode()
        logger.debug(f"Encoded JSON length: {len(encoded_json)} characters")
        
        logger.debug("Rendering result template")
        return render_template("mcq/result.html", 
                             questions=mcqs, 
                             video_url=embed_url, 
                             answers_json=encoded_json)
                             
    except ValueError as e:
        logger.error(f"Invalid MCQ count value: {mcq_count}")
        return render_template("mcq/mcq_index.html", error="Invalid MCQ count")
    except Exception as e:
        logger.error(f"Unexpected error in MCQ generation: {e}")
        logger.debug(f"Exception type: {type(e).__name__}")
        return render_template("mcq/mcq_index.html", error=str(e))

@app.route("/mcq/submit", methods=["POST"])
def submit_answers():
    logger.debug("Answer submission POST request received")
    
    try:
        # Decode answers
        encoded_json = request.form["answers_json"]
        logger.debug(f"Received encoded JSON length: {len(encoded_json)} characters")
        
        decoded_json = base64.b64decode(encoded_json).decode()
        questions = json.loads(decoded_json)
        logger.debug(f"Successfully decoded {len(questions)} questions")

        # Process user answers
        user_answers = []
        correctness = []
        logger.debug("Processing user answers")

        for i, q in enumerate(questions):
            selected = request.form.get(f"q{i}", "")
            user_answers.append(selected)
            is_correct = selected == q["answer"]
            correctness.append(is_correct)
            logger.debug(f"Q{i+1}: Selected='{selected}', Correct='{q['answer']}', Match={is_correct}")

        total = len(questions)
        correct = sum(correctness)
        logger.debug(f"Final score: {correct}/{total} ({correct/total*100:.1f}%)")

        logger.debug("Rendering submission result template")
        return render_template("mcq/submission_result.html",
                             video_url=request.form.get("video_url"),
                             questions=questions,
                             user_answers=user_answers,
                             correctness=correctness,
                             score=correct,
                             total=total,
                             zip=zip)
                             
    except Exception as e:
        logger.error(f"Error processing answer submission: {e}")
        logger.debug(f"Exception type: {type(e).__name__}")
        return render_template("mcq/mcq_index.html", error="Error processing answers")

# Placeholder for future projects
@app.route("/summarize")
def summarize_home():
    logger.debug("Summarize page accessed")
    return "<h1>Summarize Project</h1><p>Coming soon...</p><p><a href='/'>Back to Home</a></p>"

if __name__ == "__main__":
    logger.info("Starting Flask application")
    logger.debug("Debug mode enabled, host: 0.0.0.0, port: 10000")
    app.run(debug=True, host='0.0.0.0', port=10000)