import asyncio
from dotenv import load_dotenv
from livekit import api 
from livekit.protocol.sip import CreateSIPParticipantRequest, SIPParticipantInfo
import os
load_dotenv(dotenv_path="./.env.local")
async def main():
  livekit_api = api.LiveKitAPI(url= os.getenv('LIVEKIT_URL'),
                api_key = os.getenv('LIVEKIT_API_KEY'),
                api_secret = os.getenv('LIVEKIT_API_SECRET'))

  request = CreateSIPParticipantRequest(
    sip_trunk_id = "ST_dRNzKKwsfe5Z",
    sip_call_to = "+919106690970",
    room_name = "my-sip-room",
    participant_identity = "sip-test",
    participant_name = "Aryan",
    play_dialtone = True
  )
  
  participant = await livekit_api.sip.create_sip_participant(request)
  
  print(f"Successfully created {participant}")

  await livekit_api.aclose()

asyncio.run(main())