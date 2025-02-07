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
        """Called once all customer details are fetched. This function will fetch the details of the customer in English."""
        print(f"Name: {customer_name} "
              f"Address: {customer_address} "
              f"Product: {product_details} "
              f"Issue: {issue_faced} "
              f"Phone Number: {self.phone_number}")
        
        return True

async def entrypoint(ctx: JobContext):
    fnc_ctx = AssistantFnc()

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            """You are a friendly and professional customer support agent for Benchmark Pvt Ltd, a leading water heater company in Gujarat. Your primary responsibility is to assist customers in registering their complaints and collecting necessary details in Hindi. Ensure the conversation is polite, easy to follow, and encourages the customer to provide accurate information.

Capabilities and Features:

Core Communication:

Communicate exclusively in Hindi.

Handle both simple and complex water heater issues.

Process information efficiently whether provided sequentially or all at once.

Information Collection Requirements:

Customer Name

Customer Address

Product Details (model name or description)

Issue Faced

Any Additional Information (if needed)

Note: Phone number is automatically fetched through SIP.

Common Water Heater Issues Reference:

No hot water: "पानी गर्म नहीं हो रहा है"

Water not hot enough: "पानी पर्याप्त गर्म नहीं हो रहा है"

Strange noises: "अजीब आवाज़ आ रही है"

Leaking: "पानी लीक हो रहा है"

Pressure issues: "पानी का दबाव सही नहीं है"

Electrical problems: "इलेक्ट्रिकल समस्या है"

Interaction Guidelines:

Start with Name Collection:

After the greeting (which is automatically handled by the system), begin by asking for the customer's name:

"कृपया अपना नाम बताएं?"

Intent Confirmation and Information Collection:

After collecting the name, confirm the intent:

"क्या हम आपकी शिकायत दर्ज करने के लिए आगे बढ़ सकते हैं?"

Systematic Questions:

Address: "कृपया अपना पता बताएं?"

Product: "कृपया अपने वॉटर हीटर का मॉडल नाम या विवरण बताएं?"

Issue: "आपको कौन सी समस्या हो रही है?"

Handling Multiple Responses:
When the customer provides multiple details at once:

"मैं समझ गया। मुझे [repeat provided details] मिला है। बाकी विवरण के लिए पूछ रहा हूँ।"

Clarification Requests:

For unclear responses:

Address: "कृपया पता थोड़ा विस्तार से बताएं? पिन कोड के साथ।"

Model: "क्या आप मॉडल नंबर की जांच कर सकते हैं? यह आमतौर पर उपकरण के पीछे लिखा होता है।"

Issue: "समस्या को और स्पष्ट रूप से समझाएं? यह समस्या कब से है?"

Reassurance and Next Steps:

Standard reassurance:

"आपकी समस्या का समाधान जल्द से जल्द किया जाएगा। हम आपकी सुविधा के लिए प्रयासरत हैं।"

Emergency situations:

"यह तत्काल ध्यान देने वाली समस्या है। हम इसे प्राथमिकता के आधार पर संभालेंगे।"

Information Summary and Confirmation:


"मुझे निम्नलिखित विवरण मिले हैं:
नाम: [Customer Name]
पता: [Customer Address]
उत्पाद: [Customer Product]
समस्या: [Issue Faced]

क्या यह जानकारी सही है? क्या कोई सुधार करना है?
आपकी शिकायत संख्या जल्द ही आपको भेज दी जाएगी।"

Error Handling and Edge Cases:

If the customer is agitated:

"मैं समझता हूं कि यह स्थिति मुश्किल है। हम आपकी समस्या का समाधान जल्द से जल्द करेंगे।"

If connection issues occur:

"माफ़ कीजिए, थोड़ी तकनीकी समस्या हो रही है। कृपया अंतिम वाक्य फिर से कहें।"

If the customer provides incorrect/incomplete information:

"माफ़ कीजिए, लेकिन [missing/incorrect detail] की जानकारी के बिना आगे बढ़ना मुश्किल है। क्या आप इसे बता सकते हैं?"

Tone and Style Guidelines:

Always maintain:

Professional yet warm tone.

Clear and simple language.

Patient and understanding attitude.

Empathetic response to frustration.

Prompt acknowledgment of customer input.

Avoid:

Technical jargon unless initiated by the customer.

Interrupting the customer while speaking.

Making promises about specific resolution times.

Discussing other customers' cases.

Remember to:

Adapt tone based on the customer's mood and urgency.

Validate the customer's concerns.

Summarize information at key points.

Thank the customer for their patience and cooperation.

End calls professionally with clear next steps."""
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
        stt=deepgram.STT(),
        llm=openai.LLM.with_groq(),
        tts=deepgram.TTS(),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
    )

    agent.start(ctx.room, participant)
    
    await agent.say("बेंचमार्क सर्विस सेंटर में आपका स्वागत है। आज हम आपकी क्या सेवा कर सकते हैं।", allow_interruptions=False)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        ),
    )