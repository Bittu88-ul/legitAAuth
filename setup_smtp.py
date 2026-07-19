import smtplib
import json
import os

CONFIG_FILE = "backend/smtp_config.json"

def main():
    print("==================================================")
    print("       LegitAuth SMTP Configuration Wizard        ")
    print("==================================================")
    print("\nTo send real OTP emails, you need a Gmail App Password.")
    print("If you don't have one, go to: https://myaccount.google.com/apppasswords")
    print("\n--------------------------------------------------")
    
    email = input("Enter your Gmail Address: ").strip()
    password = input("Enter your 16-letter App Password: ").strip().replace(" ", "")
    
    print("\n[+] Testing connection to Gmail SMTP server...")
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email, password)
        server.quit()
        
        print("[+] Login SUCCESS! Credentials are valid.")
        
        config = {
            "SMTP_EMAIL": email,
            "SMTP_PASSWORD": password
        }
        
        os.makedirs("backend", exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
            
        print(f"[+] Credentials saved to {CONFIG_FILE}")
        print("[!] Please restart the OTP Server (port 8001) to apply changes.")
        
    except smtplib.SMTPAuthenticationError:
        print("[-] Login FAILED! Invalid email or App Password.")
        print("[-] Make sure you generated an APP PASSWORD, not your normal password.")
    except Exception as e:
        print(f"[-] Connection FAILED: {e}")

if __name__ == "__main__":
    main()
