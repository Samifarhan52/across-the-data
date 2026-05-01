# ACROSS THE DATA

Run locally:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Open: http://127.0.0.1:5000

Default admin login:
- Email: farhanulla.shaik@gmail.com
- Password: Admin@12345

Change before deployment using environment variables:
- APP_NAME
- ADMIN_EMAIL
- ADMIN_PASSWORD
- SECRET_KEY
- WHATSAPP_NUMBER
- SUPPORT_EMAIL
- UPI_ID

Deploy on Vercel:
1. Push this folder to GitHub.
2. Import GitHub repo in Vercel.
3. Add the environment variables above.
4. Deploy.

Note: SQLite works for local testing. For production-scale use on Vercel, connect a hosted database such as PostgreSQL because Vercel serverless file storage is not permanent.
