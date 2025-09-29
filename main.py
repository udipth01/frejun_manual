from fastapi import APIRouter, HTTPException
import os
import logging
import httpx
import uuid

router = APIRouter()
logger = logging.getLogger("frejun")

TELER_API_KEY = os.getenv("TELER_API_KEY")
BACKEND_DOMAIN = os.getenv("BACKEND_DOMAIN")

CALLS = {}

@router.post("/initiate-call")
async def initiate_call_manual(lead_id: str, from_number: str):
    """
    Dynamically fetch to_number from Bitrix lead and initiate call via FreJun.
    """
    if not (lead_id and from_number):
        raise HTTPException(status_code=400, detail="Missing parameters")
    
    # Fetch lead phone from Bitrix
    BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{BITRIX_WEBHOOK_URL}/crm.lead.get.json", params={"id": lead_id})
        res.raise_for_status()
        lead_data = res.json().get("result", {})
        phones = lead_data.get("PHONE", [])
        if not phones:
            raise HTTPException(status_code=400, detail="Lead has no phone number")
        to_number = phones[0].get("VALUE")

    call_id = str(uuid.uuid4())
    CALLS[call_id] = {"lead_id": lead_id, "to_number": to_number, "from_number": from_number}
    logger.info(f"Initiating manual call {call_id} from {from_number} to {to_number} for lead {lead_id}")

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

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        logger.info(f"FreJun API response: {response.status_code}, {response.text}")

    return {"call_id": call_id, "to_number": to_number, "status": "initiated"}
