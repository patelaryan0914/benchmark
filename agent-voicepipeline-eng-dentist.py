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
from livekit.protocol import sip as proto_sip
from livekit import api
import os
from livekit.plugins import turn_detector

load_dotenv(dotenv_path="./.env.local")
logger = logging.getLogger("voice-agent")

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

class AssistantFnc(llm.FunctionContext):
    def __init__(self):
        super().__init__()
        self.phone_number = None
        self.participant_identity = None
        self.room_name = None
        self.livekit_api = None
        
    def set_phone_number(self, phone_number: str):
        self.phone_number = phone_number

    def transfer_details(self,room_name:str,participant_identity:str):
        self.participant_identity = participant_identity
        self.room_name = room_name

    @llm.ai_callable()
    def book_appointment(self,customer_name: str, reason: str, date_time: str):
      """
    Books a new dental appointment.
    Args:
        name: Customer's full name.
        reason: Reason for the dental visit.
        date_time: Preferred date and time for the appointment.
    Returns:
        Confirmation message.
      """
      print(f"Name: {customer_name} "
              f"Reason: {reason} "
              f"date_time: {date_time} "
              f"Phone Number: {self.phone_number}")
        
      return f"Your Appoinment has been booked on date {date_time}"

    @llm.ai_callable()
    async def transfer_call(self) -> None:
        """
        Transfer the SIP call to another number. This will essentially end the current call and start a new one,
        the PhoneAssistant will no longer be active on the call.

        Args:
            participant_identity (str): The identity of the participant.
            transfer_to (str): The phone number to transfer the call to.
        """
        transfer_to="+916355703851"
        logger.info(f"Transferring call for participant {self.participant_identity} to {transfer_to}")

        try:
            # Initialize LiveKit API client if not already done
            if not self.livekit_api:
                livekit_url = os.getenv('LIVEKIT_URL')
                api_key = os.getenv('LIVEKIT_API_KEY')
                api_secret = os.getenv('LIVEKIT_API_SECRET')
                logger.debug(f"Initializing LiveKit API client with URL: {livekit_url}")
                self.livekit_api = api.LiveKitAPI(
                    url=livekit_url,
                    api_key=api_key,
                    api_secret=api_secret
                )

            # Create transfer request
            transfer_request = proto_sip.TransferSIPParticipantRequest(
                participant_identity=self.participant_identity,
                room_name=self.room_name,
                transfer_to=transfer_to,
                play_dialtone=True
            )
            logger.debug(f"Transfer request: {transfer_request}")

            # Perform transfer
            await self.livekit_api.sip.transfer_sip_participant(transfer_request)
            logger.info(f"Successfully transferred participant {self.participant_identity} to {transfer_to}")

        except Exception as e:
            logger.error(f"Failed to transfer call: {e}", exc_info=True)
            await self.say("I'm sorry, I couldn't transfer your call. Is there something else I can help with?")

async def entrypoint(ctx: JobContext):
    fnc_ctx = AssistantFnc()

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
           """You are a virtual assistant for B square Dental Care, providing professional and empathetic customer service in English."

        "Your role is to assist customers in booking, modifying, or canceling their dentist appointments, as well as answering general inquiries. Here are the key scenarios you must handle:"

        "1. *New Appointment Booking:*"
        "   a. Greet the customer and ask for their name: 'May I have your name, please?'"
        "   b. Ask for the reason for the visit (e.g., routine check-up, cleaning, pain, or a specific dental issue): 'What brings you to Smile Dental Care today?'"
        "   c. Collect the preferred date and time for the appointment: 'When would you like to schedule your appointment?'"
        "   e. After finalizing the appointment, confirm all details and use the book_appointment function."
        "   f. Inform the customer about SMS or email confirmation: 'Your appointment has been scheduled. You will receive a confirmation message shortly.'"

        "2. *Modifying an Existing Appointment:*"
        "   a. Ask for their phone number to retrieve the appointment: 'May I have your registered phone number to locate your appointment details?'"
        "   b. Share the details of their current appointment: 'Your appointment is scheduled for [date and time] with Dr. [name].'"
        "   c. Ask what they would like to modify: 'What would you like to change about your appointment? The date, time, or reason for the visit?'"
        "   d. Follow the booking sequence to find a new slot and confirm the changes."
        "   e. After modifying the appointment, confirm the updates and inform about the confirmation message."

        "3. *Canceling an Appointment:*"
        "   a. Ask for their registered phone number to locate the appointment: 'May I have your registered phone number to find your appointment details?'"
        "   b. Confirm the appointment details: 'You have an appointment scheduled for [date and time] with Dr. [name]. Would you like to cancel it?'"
        "   c. Use the cancel_appointment function to cancel the appointment."
        "   d. Inform the customer: 'Your appointment has been canceled. You will receive a confirmation message shortly.'"

        "4. *Tranfer on going call*"
        "   a. Tranfer the call if user says to."
        "   b. Run the function 'transfer_call()'."

        "Important Guidelines:"
        "- Always confirm details with the customer before proceeding."
        "- Maintain a professional and empathetic tone throughout."
        "- If a customer asks a general query (e.g., clinic timings or services), provide accurate information."
        "- End the call politely with: 'Thank you for choosing Smile Dental Care. Goodbye!'"
        "- Use the end_call function to disconnect after the conversation."

        "Functions you MUST use in the process:"
        "   - book_appointment(name, reason, date_time)"
        "   - modify_appointment(phone_number, new_date_time)"
        "   - cancel_appointment(phone_number)"
        "   - transfer_call()"
        "   - end_call()"""
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    print(participant)
    # Check if the participant is a SIP participant and get phone number
    if participant.kind == ParticipantKind.PARTICIPANT_KIND_SIP:
        phone_number = participant.attributes.get('sip.phoneNumber')
        logger.info(f"Caller phone number is {phone_number}")
        # Store phone number in function context
        fnc_ctx.set_phone_number(phone_number)
        fnc_ctx.transfer_details(ctx.room.name,participant.identity)
    
    logger.info(f"starting voice assistant for participant {participant.identity}")
    
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(language="en-IN"),
        llm=openai.LLM(),
        tts=deepgram.TTS(),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
        allow_interruptions=False,
        turn_detector=turn_detector.EOUModel(),
    )

    agent.start(ctx.room, participant)
    
    await agent.say("Welcome to B Square Dental. How may we assist you today?", allow_interruptions=False)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="outbound-caller",
        ),
    )