# FindBack AI — HackIndia Demo-Ready MVP

A working Flask + SQLite Lost & Found MVP designed for a live hackathon demo.

## Demo flow

1. Person X registers and posts a found item with photos/details.
2. Person Y registers and searches in natural language.
3. AI ranks the found items using TF-IDF/cosine similarity plus explainable item/color/category signals.
4. Person Y opens a possible match and submits private ownership evidence.
5. Admin reviews the claim, sees the AI verification score and claimant evidence, then approves/rejects.
6. If approved, the item becomes **claimed** and Person Y sees controlled return-coordination contact on their dashboard.

## Demo accounts

**Admin**
- Email: `admin@lostfound.demo`
- Password: `admin123`
- OTP: `123456`

**Normal users**
- Create two normal accounts (Person X and Person Y).
- Demo OTP for every login: `123456`

## Run on laptop

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`.

## Run on a phone for filming

Connect the phone and laptop to the same Wi-Fi and open the LAN address printed by Flask, for example:

`http://192.168.x.x:5000`

Keep the Flask terminal running while filming. If Windows Firewall blocks the phone, allow Python/Flask on the private network.

## Important

OTP delivery is intentionally simulated for the hackathon. In production, use a real authentication/OTP provider.
