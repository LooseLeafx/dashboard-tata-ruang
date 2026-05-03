# 🔐 SECURITY CHECKLIST & BEST PRACTICES

Panduan keamanan praktis untuk dashboard Anda.

---

## ✅ PRE-DEPLOYMENT SECURITY CHECKLIST

Sebelum deploy ke production, pastikan:

### Credentials & Secrets

- [ ] ✅ File `.gitignore` sudah ada dan benar
  ```
  credentials.json
  drive_config.json
  kunci_akses.json
  .env
  .env.local
  secrets.toml
  ```

- [ ] ✅ `credentials.json` TIDAK ada di git
  ```bash
  git status
  # Jangan ada credentials.json di output!
  ```

- [ ] ✅ API keys TIDAK di-hardcode di code
  ```python
  # ❌ JANGAN
  API_KEY = "sk-123456789"
  PASSWORD = "admin123"
  
  # ✅ LAKUKAN
  import os
  API_KEY = os.getenv("API_KEY")
  PASSWORD = os.getenv("PASSWORD")
  ```

- [ ] ✅ Database passwords dari environment variables
  ```python
  DB_PASSWORD = os.getenv("DB_PASSWORD")
  ```

### Dependencies

- [ ] ✅ `requirements.txt` up-to-date
  ```bash
  pip freeze > requirements.txt
  ```

- [ ] ✅ Tidak ada vulnerable packages
  ```bash
  pip-audit
  # Instal: pip install pip-audit
  ```

- [ ] ✅ Pinned versions untuk stability
  ```
  streamlit==1.28.1
  pandas==1.5.3
  # Bukan: streamlit, pandas (latest)
  ```

### Code Security

- [ ] ✅ CSRF protection enabled
  ```python
  # Di app.py, sudah ada:
  # enableXsrfProtection = true (di config.toml)
  ```

- [ ] ✅ SQL injection prevention (jika pakai database)
  ```python
  # ❌ JANGAN
  query = f"SELECT * FROM users WHERE id={user_id}"
  
  # ✅ LAKUKAN
  query = "SELECT * FROM users WHERE id = %s"
  cursor.execute(query, (user_id,))
  ```

- [ ] ✅ Input validation
  ```python
  # Validate user input
  if not isinstance(selected_srs, str):
      st.error("Invalid input")
      st.stop()
  
  if len(selected_srs) > 100:
      st.error("Input terlalu panjang")
      st.stop()
  ```

### Data Protection

- [ ] ✅ Tidak ada sensitive data di logs
  ```python
  # ❌ JANGAN
  logger.info(f"Password: {password}")
  
  # ✅ LAKUKAN
  logger.info("User login attempt")
  ```

- [ ] ✅ Passwords di-hash (jika ada database lokal)
  ```python
  from werkzeug.security import generate_password_hash
  
  hashed = generate_password_hash("password123")
  ```

### Access Control

- [ ] ✅ Authentication implemented (jika diperlukan)
  ```python
  # Check if user is authorized
  if user_role != "admin":
      st.error("Unauthorized access")
      st.stop()
  ```

- [ ] ✅ Rate limiting untuk prevent abuse
  ```python
  # Di app.py, sudah ada contoh di DEPLOYMENT_GUIDE
  ```

### Production Checklist

- [ ] ✅ Error messages tidak reveal system info
  ```python
  # ❌ JANGAN
  st.error(f"Database error: {e}")
  
  # ✅ LAKUKAN
  st.error("Gagal memproses data. Hubungi admin.")
  logger.error(f"DB Error: {e}")  # Log ke file, bukan tampilkan
  ```

- [ ] ✅ HTTPS enabled (automatic di Streamlit Cloud)
  ```
  ✓ https://dashboard-tata-ruang.streamlit.app
  ✗ http://dashboard-tata-ruang.streamlit.app
  ```

- [ ] ✅ Server-side validation (tidak hanya client-side)

---

## 🔐 STEP-BY-STEP: SECURE YOUR APP

### Step 1: Create `.env` file (Local Only)

```bash
# File: .env (JANGAN COMMIT!)
GOOGLE_CREDS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your-folder-id
DB_HOST=localhost
DB_USER=tata_ruang_user
DB_PASSWORD=strong_password_here
DASHBOARD_PASSWORD=secret_admin_password
STREAMLIT_SERVER_PORT=8501
```

### Step 2: Use .env di Code

```python
# Install: pip install python-dotenv
from dotenv import load_dotenv
import os

load_dotenv()

# Access variables
google_creds_path = os.getenv("GOOGLE_CREDS_PATH")
db_password = os.getenv("DB_PASSWORD")

# Fallback jika tidak ada
db_host = os.getenv("DB_HOST", "localhost")
```

### Step 3: Setup `.gitignore` Properly

Verifikasi file ini ada di root:

```bash
# Check .gitignore
cat .gitignore
```

Pastikan include:
```
credentials.json
drive_config.json
.env
.env.*
secrets.toml
```

### Step 4: Upload Secrets ke Streamlit Cloud

**Untuk Streamlit Cloud:**

1. Buka https://share.streamlit.io
2. Click app Anda > Settings
3. Tab "Secrets"
4. Add secrets (copy dari .env):

```
GOOGLE_CREDS = {
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  ...
}

DATABASE_PASSWORD = "your-db-password"
ADMIN_PASSWORD = "admin-secret"
```

Access di code:
```python
import streamlit as st

google_creds = st.secrets["GOOGLE_CREDS"]
admin_password = st.secrets["ADMIN_PASSWORD"]
```

### Step 5: Database Security (jika ada)

#### Setup User dengan Limited Permissions

```sql
-- Jangan gunakan root!
CREATE USER 'tata_ruang_user'@'localhost' IDENTIFIED BY 'strong_password_123';

-- Grant only needed permissions
GRANT SELECT, INSERT, UPDATE ON tata_ruang_db.* TO 'tata_ruang_user'@'localhost';
GRANT DELETE ON tata_ruang_db.activities TO 'tata_ruang_user'@'localhost';

FLUSH PRIVILEGES;
```

#### Connection String (Secure)

```python
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    ssl_disabled=False  # Enable SSL
)
```

### Step 6: Implement Authentication (Optional)

#### Simple Password Protection

```python
import streamlit as st
import hashlib

def check_password():
    """Returns `True` if the user had a correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets.get("admin_password", "admin"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("😕 Password tidak benar")
        return False
    else:
        # Password correct.
        return True


if check_password():
    st.success("✅ Welcome!")
    # ... rest of app ...
```

Tambah ke `.env`:
```
ADMIN_PASSWORD=secret123
```

#### More Advanced: Google OAuth

```python
# Pakai library: streamlit-authenticator
# pip install streamlit-authenticator

import streamlit_authenticator as stauth

names = ["John Smith", "Rebecca Briggs"]
usernames = ["jsmith", "rbriggs"]
passwords = ["123", "456"]

hashed_passwords = stauth.Hasher(passwords).generate()

authenticator = stauth.Authenticate(
    names, usernames, hashed_passwords,
    "some_cookie_name", "some_signature_key", cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login()

if authentication_status:
    st.write(f'Welcome *{name}*')
    # ... app ...
    authenticator.logout("Logout", "sidebar")
elif authentication_status is False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')
```

---

## 📝 MONITORING & AUDITING

### Setup Logging

```python
import logging
from datetime import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('audit.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Log important events
def log_action(action, user, details=""):
    """Log user action untuk audit trail"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "user": user,
        "details": details
    }
    logger.info(json.dumps(log_entry))

# Usage
log_action("view_data", "admin", f"viewed {len(df)} rows")
log_action("export_data", "user123", "exported to CSV")
log_action("failed_login", "unknown", "invalid password")
```

### Review Logs

```bash
# View recent logs
tail -f audit.log

# Search for errors
grep "ERROR" audit.log

# Search by date
grep "2024-05-03" audit.log

# Count failed attempts
grep "failed_login" audit.log | wc -l
```

---

## 🛡️ REGULAR SECURITY MAINTENANCE

### Weekly
- [ ] Review audit logs for suspicious activity
- [ ] Check for failed login attempts
- [ ] Monitor error logs

### Monthly
- [ ] Update dependencies
  ```bash
  pip list --outdated
  pip install --upgrade <package>
  pip freeze > requirements.txt
  ```
- [ ] Check for vulnerable packages
  ```bash
  pip-audit
  ```
- [ ] Rotate API keys (jika ada)
- [ ] Backup database

### Quarterly
- [ ] Security audit
- [ ] Review .gitignore
- [ ] Check SSL certificate expiry
- [ ] Update system packages (jika VPS)

### Annually
- [ ] Security penetration testing
- [ ] Update dependencies major versions
- [ ] Review and update security policies

---

## 🚨 INCIDENT RESPONSE

### Jika credentials leaked/exposed:

1. **IMMEDIATE**: Rotate leaked credentials
   ```bash
   # Generate new API key di Google Cloud Console
   # Update .env dan Streamlit Cloud secrets
   ```

2. **Check logs** untuk unauthorized access
   ```bash
   grep "failed_login\|ERROR" audit.log
   ```

3. **Revoke** old credentials/tokens
4. **Notify** affected users (jika ada)
5. **Document** incident (what happened, when, action taken)

### Jika sistem compromise:

1. Take application offline immediately
2. Check logs untuk find the entry point
3. Backup clean version dari production
4. Review dan patch vulnerability
5. Deploy clean version
6. Monitor closely untuk days
7. Document lessons learned

---

## 📚 SECURITY RESOURCES

- [OWASP Top 10](https://owasp.org/Top10/)
- [Streamlit Security](https://docs.streamlit.io/knowledge-base/deploy/security-infrastructure)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [git Secret Manager](https://docs.github.com/en/code-security/secret-scanning)

---

## ✨ SECURITY SUMMARY

**Remember:**
- 🔒 Never commit secrets
- 🔑 Use environment variables / secrets manager
- 🛡️ Validate all user inputs
- 📝 Log important actions
- 🔄 Keep dependencies updated
- 🕵️ Monitor logs regularly
- 🚨 Have incident response plan

**Your Motto:** "Security is not a feature, it's a responsibility!"

---

**Last Updated:** May 3, 2026  
**Version:** 1.0
