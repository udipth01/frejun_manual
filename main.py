from fastapi import APIRouter, HTTPException, FastAPI
import os
import logging
import httpx
import uuid

app = FastAPI()

router = APIRouter()
logger = logging.getLogger("frejun")
logger.setLevel(logging.INFO)
# Ensure console output
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)

TELER_API_KEY = os.getenv("TELER_API_KEY")
BACKEND_DOMAIN = os.getenv("BACKEND_DOMAIN")
BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")

CALLS = {}

@router.post("/initiate-call")
async def initiate_call_manual(lead_id: str, from_number: str):
    logger.info(f"Received request to initiate call. lead_id={lead_id}, from_number={from_number}")

    if not (lead_id and from_number):
        logger.error("Missing lead_id or from_number")
        raise HTTPException(status_code=400, detail="Missing parameters")
    
    # Fetch lead phone from Bitrix
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching lead data from Bitrix: {BITRIX_WEBHOOK_URL}/crm.lead.get.json?id={lead_id}")
            res = await client.get(f"{BITRIX_WEBHOOK_URL}/crm.lead.get.json", params={"id": lead_id})
            res.raise_for_status()
            lead_data = res.json().get("result", {})
            phones = lead_data.get("PHONE", [])
            if not phones:
                logger.error(f"No phone numbers found for lead {lead_id}")
                raise HTTPException(status_code=400, detail="Lead has no phone number")
            to_number = phones[0].get("VALUE")
            logger.info(f"Lead phone fetched: {to_number}")
    except Exception as e:
        logger.exception("Failed to fetch lead phone from Bitrix")
        raise HTTPException(status_code=500, detail=f"Bitrix fetch error: {str(e)}")
    
    call_id = str(uuid.uuid4())
    CALLS[call_id] = {"lead_id": lead_id, "to_number": to_number, "from_number": from_number}
    from_number = from_number.strip()
    if not from_number.startswith("+"):
        from_number = f"+{from_number}"

    logger.info(f"Prepared call_id={call_id} payload: from {from_number} to {to_number}")

    # Trigger FreJun API
    url = "https://api.frejun.ai/v1/call/outgoing"
    headers = {
        "Authorization": f"Bearer {TELER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "from_number": from_number,
        "to_number": to_number,
        "incoming_call_url": f"https://{BACKEND_DOMAIN}/frejun-flow",
        "outgoing_call_url": f"https://{BACKEND_DOMAIN}/frejun-handler",
        "metadata": {"lead_id": lead_id, "call_id": call_id}
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Sending call request to FreJun: {payload}")
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"FreJun API response: {response.status_code}, {response.text}")
            if response.status_code != 200:
                logger.error("FreJun API call failed")
    except Exception as e:
        logger.exception("Error calling FreJun API")
        raise HTTPException(status_code=500, detail=f"FreJun API error: {str(e)}")

    return {"call_id": call_id, "to_number": to_number, "status": "initiated"}

@app.post("/frejun-flow")
async def frejun_flow(payload: dict):
    logger.info(f"FreJun incoming call event: {payload}")
    return {"status": "ok"}

@app.post("/frejun-handler")
async def frejun_handler(payload: dict):
    logger.info(f"FreJun outgoing call event: {payload}")
    return {"status": "ok"}


app.include_router(router)

