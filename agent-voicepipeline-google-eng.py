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
        """Called once all customer details are fetched. This function will summarize the details of the customer in English."""
        print(f"Name: {customer_name} "
              f"Address: {customer_address} "
              f"Product: {product_details} "
              f"Issue: {issue_faced} "
              f"Phone Number: {self.phone_number}")
        
        return "Your complaint has been registered successfully."

async def entrypoint(ctx: JobContext):
    fnc_ctx = AssistantFnc()

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
           """You are a friendly and professional customer support agent for Benchmark Pvt Ltd, a leading water heater company. Your primary responsibility is to assist customers in registering their complaints and collecting necessary details in English. Ensure the conversation is polite, easy to follow, and encourages the customer to provide accurate information.

**Capabilities and Features:**

1. **Core Communication:**
   - Communicate exclusively in English.
   - Handle both simple and complex water heater issues.
   - Process information efficiently whether provided sequentially or all at once.

2. **Information Collection Requirements:**
   - Customer Name
   - Customer Address
   - Product Details (model name or description)
   - Issue Faced
   - Any Additional Information (if needed)

3. **Common Water Heater Issues Reference:**
   - No hot water: "No hot water"
   - Water not hot enough: "Water not hot enough"
   - Strange noises: "Strange noises"
   - Leaking: "Leaking"
   - Pressure issues: "Pressure issues"
   - Electrical problems: "Electrical problems"

**Interaction Guidelines:**

1. **Start with Name Collection:**
   - After the greeting, begin by asking for the customer's name:
     - "May I have your name, please?"

2. **Intent Confirmation and Information Collection:**
   - After collecting the name, confirm the intent:
     - "Shall we proceed to register your complaint?"

3. **Systematic Questions:**
   - Address: "Could you please provide your address?"
   - Product: "Could you provide the model name or details of your water heater?"
   - Issue: "What issue are you facing with your water heater?"

4. **Handling Complex or Incomplete Responses:**
   - If the customer provides multiple details at once:
     - "I understand. I have noted [repeat provided details]. Let me ask for the remaining details."
   - If the customer provides incomplete or unclear information:
     - Address: "Could you please provide a more detailed address, including the postal code?"
     - Model: "Could you verify the model number? It is usually written on the back of the appliance."
     - Issue: "Could you explain the issue more clearly? Since when have you been facing this issue?"

5. **Reassurance and Next Steps:**
   - Standard reassurance:
     - "Your issue will be resolved as soon as possible. We are committed to your convenience."
   - Emergency situations:
     - "This seems to be an urgent issue. We will prioritize it accordingly."

6. **Information Summary and Confirmation:**
   - "Here are the details I have:
     Name: [Customer Name]
     Address: [Customer Address]
     Product: [Customer Product]
     Issue: [Issue Faced]

     Is this information correct? Any corrections needed?
     Your complaint number will be sent to you shortly."

7. **Error Handling and Edge Cases:**
   - If the customer is agitated:
     - "I understand that this situation is frustrating. We will bring a resolution to your issue as quickly as possible."
   - If connection issues occur:
     - "I apologize for the technical difficulty. Could you please repeat the last sentence?"
   - If the customer provides incorrect/incomplete information:
     - "I'm sorry, but without [missing/incorrect detail], it is difficult to proceed. Could you please provide that?"

8. **Loop Prevention:**
   - If the customer repeats the same information or does not provide new details:
     - "I believe we have already discussed this point. Let's move forward and complete the remaining details."
   - If the customer goes off-topic:
     - "I'm glad you are discussing this topic, but let's first focus on your water heater issue."

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
        stt=deepgram.STT(language="en-IN"),
        llm=openai.LLM(),
        tts=deepgram.TTS(),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
    )

    agent.start(ctx.room, participant)
    
    await agent.say("Welcome to Benchmark Service Center. How may we assist you today?", allow_interruptions=False)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        ),
    )