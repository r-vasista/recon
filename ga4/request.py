import requests
from ga4.utils import generate_ga4_token

def ga4_request(property_id, endpoint, body):
    """
    Fully Dynamic GA4 API Caller
    endpoint: runReport, runRealtimeReport, runPivotReport, runFunnelReport...
    body: ANY GA4 request body
    """
    token = generate_ga4_token()
    if not token:
        return {"error": "Token generation failed"}

    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=body, headers=headers)

    return response.json()