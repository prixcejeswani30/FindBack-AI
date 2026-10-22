# FindBack AI

FindBack AI is a campus-focused lost-and-found application that helps people report found belongings, search for missing items and verify ownership claims.

## Features

- Account registration and sign-in with a verification step.
- Found-item reports with descriptions, categories, locations, dates and up to three photos.
- Natural-language search across active found-item reports.
- Ranked matching based on text similarity and item details, with an explanation for each result.
- Private ownership claims reviewed by an administrator.
- Claim status tracking and controlled return coordination after approval.

## Technology

- Python and Flask
- SQLite
- Jinja templates, HTML and CSS
- scikit-learn and the project's matching module
- Werkzeug password hashing and session handling

## Run locally

1. Install Python 3.10 or later.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Start the application:

   ```powershell
   python app.py
   ```

5. Open http://127.0.0.1:5000.

The application creates its SQLite database and required tables when it starts. Uploaded item images are stored under `static/uploads`.

## Account verification

The current local build uses a test verification code. Replace this with a proper verification provider before using the application with real accounts.

## Project structure

- `app.py` — Flask routes, database access and application workflows.
- `ai_matcher.py` — item matching and ranking.
- `templates/` — page templates.
- `static/style.css` — application styles.
- `static/uploads/` — uploaded item photos.
- `requirements.txt` — Python dependencies.

## Before a public deployment

Configure a strong secret key through the `SECRET_KEY` environment variable, use a production-ready database and file-storage service, and add production authentication, upload validation, rate limiting, backups and privacy/retention controls.
