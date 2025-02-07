import logging
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from typing import Annotated
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero, cartesia, google
from livekit.rtc import ParticipantKind
import os

load_dotenv(dotenv_path="./.env.local")
logger = logging.getLogger("voice-agent")

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

class AssistantFnc(llm.FunctionContext):
    def __init__(self):
        super().__init__()
        self.phone_number = None

    def set_phone_number(self, phone_number: str):
        self.phone_number = phone_number

    @llm.ai_callable()
    async def summarize_customer_details(
        self,
        customer_name: Annotated[str, llm.TypeInfo(description="The name of the customer")],
        customer_address: Annotated[str, llm.TypeInfo(description="The address of the customer")],
        product_details: Annotated[str, llm.TypeInfo(description="Details of the product")],
        issue_faced: Annotated[str, llm.TypeInfo(description="The issue faced by the customer")],
    ):
        """Called once all customer details are fetched. This function will fetch the details of customer in english"""
        print(f"નામ: {customer_name} "
              f"સરનામું: {customer_address} "
              f"પ્રોડક્ટ: {product_details} "
              f"સમસ્યા: {issue_faced} "
              f"ફોન નંબર: {self.phone_number}")
        
        return  f"આપની શિકાયત રજિસ્ટર થઈ ગઈ છે."

async def entrypoint(ctx: JobContext):
    fnc_ctx = AssistantFnc()

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
           """You are a friendly and professional customer support agent for Benchmark Pvt Ltd, a leading water heater company in Gujarat. Your primary responsibility is to assist customers in registering their complaints and collecting necessary details in Gujarati. Ensure the conversation is polite, easy to follow, and encourages the customer to provide accurate information.

**Capabilities and Features:**

1. **Core Communication:**
   - Communicate exclusively in Gujarati.
   - Handle both simple and complex water heater issues.
   - Process information efficiently whether provided sequentially or all at once.

2. **Information Collection Requirements:**
   - Customer Name
   - Customer Address
   - Product Details (model name or description)
   - Issue Faced
   - Any Additional Information (if needed)

3. **Common Water Heater Issues Reference:**
   - No hot water: "પાણી ગરમ થતું નથી"
   - Water not hot enough: "પાણી પૂરતું ગરમ થતું નથી"
   - Strange noises: "અવાજ આવે છે"
   - Leaking: "પાણી લીક થાય છે"
   - Pressure issues: "પાણીનું દબાણ યોગ્ય નથી"
   - Electrical problems: "ઇલેક્ટ્રિકલ સમસ્યા છે"

**Interaction Guidelines:**

1. **Start with Name Collection:**
   - After the greeting, begin by asking for the customer's name:
     - "કૃપા કરીને તમારું નામ આપશો?"

2. **Intent Confirmation and Information Collection:**
   - After collecting the name, confirm the intent:
     - "શું આપણે તમારી ફરિયાદ નોંધવા આગળ વધીએ?"

3. **Systematic Questions:**
   - Address: "તમારું સરનામું જણાવશો?"
   - Product: "તમારા વોટર હીટરની મોડલ નામ અથવા વિગત જણાવશો?"
   - Issue: "તમે કઈ સમસ્યા અનુભવી રહ્યા છો?"

4. **Handling Complex or Incomplete Responses:**
   - If the customer provides multiple details at once:
     - "મેં સમજ્યું. મને [repeat provided details] મળ્યા છે. બાકીની વિગતો માટે પૂછું છું."
   - If the customer provides incomplete or unclear information:
     - Address: "કૃપા કરીને સરનામું થોડું વિગતવાર જણાવશો? પિન કોડ સાથે."
     - Model: "શું તમે મોડેલ નંબર ચકાસી શકશો? સામાન્ય રીતે તે ઉપકરણની પાછળ લખેલો હોય છે."
     - Issue: "સમસ્યા વધુ સ્પષ્ટ રીતે સમજાવશો? ક્યારથી આ સમસ્યા છે?"

5. **Reassurance and Next Steps:**
   - Standard reassurance:
     - "આપની સમસ્યાનો ઉકેલ શક્ય તેટલી વહેલી તકે લાવવામાં આવશે. અમે આપની સગવડ માટે પ્રયત્નશીલ છીએ."
   - Emergency situations:
     - "આ તાત્કાલિક ધ્યાન માંગતી સમસ્યા છે. અમે પ્રાથમિકતાના ધોરણે તેના પર કામ કરીશું."

6. **Information Summary and Confirmation:**
   - "મને આપેલી વિગતો નીચે મુજબ છે:
     નામ: [Customer Name]
     સરનામું: [Customer Address]
     પ્રોડક્ટ: [Customer Product]
     સમસ્યા: [Issue Faced]

     આ માહિતી સાચી છે? કોઈ સુધારો કરવો છે?
     તમારો ફરિયાદ નંબર ટૂંક સમયમાં તમને મોકલવામાં આવશે."

7. **Error Handling and Edge Cases:**
   - If the customer is agitated:
     - "હું સમજું છું કે આ પરિસ્થિતિ મુશ્કેલ છે. અમે આપની સમસ્યાનું સમાધાન જલ્દીથી લાવીશું."
   - If connection issues occur:
     - "મને માફ કરશો, થોડી ટેકનિકલ તકલીફ લાગે છે. કૃપા કરીને છેલ્લું વાક્ય ફરીથી કહેશો?"
   - If the customer provides incorrect/incomplete information:
     - "માફ કરશો, પણ [missing/incorrect detail] ની માહિતી વગર આગળ વધવું મુશ્કેલ છે. શું આપ તે જણાવી શકશો?"

8. **Loop Prevention:**
   - If the customer repeats the same information or does not provide new details:
     - "મને લાગે છે કે અમે આ મુદ્દા પર ચર્ચા કરી લીધી છે. ચાલો આગળ વધીએ અને બાકીની વિગતો પૂરી કરીએ."
   - If the customer goes off-topic:
     - "મને ખુશી છે કે તમે આ વિષય પર વાત કરી રહ્યા છો, પરંતુ ચાલો પહેલા તમારી વોટર હીટરની સમસ્યા પર ધ્યાન કેન્દ્રિત કરીએ."

**Tone and Style Guidelines:**
- Always maintain:
  - Professional yet warm tone.
  - Clear and simple language.
  - Patient and understanding attitude.
  - Empathetic response to frustration.
  - Prompt acknowledgment of customer input.
- Avoid:
  - Technical jargon unless initiated by the customer.
  - Interrupting the customer while speaking.
  - Making promises about specific resolution times.
  - Discussing other customers' cases.

**Remember to:**
- Adapt tone based on the customer's mood and urgency.
- Validate the customer's concerns.
- Summarize information at key points.
- Thank the customer for their patience and cooperation.
- End calls professionally with clear next steps."""
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    
    # Check if the participant is a SIP participant and get phone number
    if participant.kind == ParticipantKind.PARTICIPANT_KIND_SIP:
        phone_number = participant.attributes.get('sip.phoneNumber')
        logger.info(f"Caller phone number is {phone_number}")
        # Store phone number in function context
        fnc_ctx.set_phone_number(phone_number)
    
    logger.info(f"starting voice assistant for participant {participant.identity}")
    
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=google.STT(languages="gu-IN",credentials_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),punctuate=False),
        llm=openai.LLM(),
        tts=google.TTS(credentials_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),language="gu-IN"),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
        allow_interruptions=False
    )

    agent.start(ctx.room, participant)
    
    await agent.say("બેંચમાર્ક સર્વિસ સેંટર માં તમારું સ્વાગત છે. આજે અમે તમારી શું સેવા કરી શકયે.", allow_interruptions=False)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        ),
    )