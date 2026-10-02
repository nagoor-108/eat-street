# Kakinada Eat Street

## Run locally

1. Install Python 3.10 or later.
2. In PowerShell, create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. For a new database with demo data, run `python init_db.py`. The command prints a random demo password. It will not overwrite an existing database; use `python init_db.py --reset` only when you explicitly want to erase and reseed it.
4. Start the application with `python run.py`, then open `http://localhost:8080`.

Set a long, private `SECRET_KEY` in `.env` before deployment. Set `SESSION_COOKIE_SECURE=true` when the app is served over HTTPS.
 