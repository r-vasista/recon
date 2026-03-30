from google.oauth2 import service_account
import google.auth.transport.requests
from django.conf import settings
import os

def generate_ga4_token():
    try:
        SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

        # Resolve absolute path to service account file
        KEY_PATH = os.path.join(settings.BASE_DIR, "ga4/service-account.json")

        credentials = service_account.Credentials.from_service_account_file(
            KEY_PATH,
            scopes=SCOPES
        )

        # Refresh token
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)

        # Return actual token string
        return credentials.token

    except Exception as e:
        print("GA4 TOKEN ERROR:", e)
        return None