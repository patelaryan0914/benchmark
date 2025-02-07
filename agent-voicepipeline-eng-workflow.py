import logging
import os
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero, cartesia , google

from typing import Annotated
# for reading mobile number
import re
import random
#Add this to store data in mongodb
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from pymongo import MongoClient
from pydantic import ValidationError
import pytz

from bson.objectid import ObjectId
from twilio.rest import Client

import uuid
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")
#  SDR_fMMgrZw29nq2 --> Dispatch
# ST_HUjLeojXB9vw --> Inbound

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)
def check_previous_complaints(mobile_number):
    """
    Check for previously existing complaints in MongoDB based on the given mobile number.
    Returns complaint details if found, 0 if not found.
    
    Args:
        mobile_number (str): Customer's mobile number
        
    Returns:
        dict/int: Complaint details if found, 0 if not found
    """
    try:
        mongo_url = os.getenv("MONGO_URI")
        if not mongo_url:
            raise ValueError("MONGO_URI is not set in environment variables.")

        client = MongoClient(mongo_url)
        db = client["customer_service"]
        collection = db["customer_info"]

        # Find the most recent complaint
        complaint = collection.find_one(
            {"mobile": mobile_number},
            sort=[("timestamp", -1)]
        )

        if complaint:
            return complaint
        return 0

    except Exception as e:
        logger.error(f"Error checking previous complaints: {str(e)}")
        return 0
    
    finally:
        if 'client' in locals():
            client.close()

def get_mobile_number(input_string):
    """
    Extracts the mobile number from the given string.
    
    Args:
        input_string (str): The string containing the mobile number.
        
    Returns:
        str: The extracted mobile number or None if not found.
    """
    if not input_string:
        logger.error("Input string is empty")
        return None
        
    # Regular expression to match a mobile number (e.g., +91 followed by 10 digits)
    match = re.search(r'\+91\d{10}', input_string)
    if match:
        return match.group()
    
    logger.warning(f"No valid mobile number found in input: {input_string}")
    return None

# Initialize the Twilio Client

# Send an SMS
def send_sms(to_number, message):
    
    from_number = "+15707295650"  # Replace with your Twilio phone number
    try:
        message = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        print(f"Message sent successfully! SID: {message.sid}")
    except Exception as e:
        print(f"Failed to send message: {e}")
        
def get_counter_from_object_id(object_id)->str:
    # Convert ObjectId to string
    object_id_str = str(object_id)
    
    # Extract the last 4 characters (counter part)
    counter_hex = object_id_str[20:]
    
    # Convert hex to integer
    # counter = int(counter_hex, 16)
    return counter_hex


# Example Usage
# # Add this to store data in mongodb
class CustomerData(BaseModel):
    mobile: Optional[str] = Field(..., description="Customer's mobile number")
    name: str = Field(..., description="Customer's name in English")
    address: str = Field(..., description="Customer's address in English")
    product: str = Field(..., description="Product owned by the customer in English")
    issue: str = Field(..., description="Issue or complaint the customer is facing")
    status: str = Field(default="pending", description="Status of the issue (e.g., pending, resolved)")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Time when the data was added")
    priority: str = Field(default=1, description="Priority of the issue (e.g., 1,2,3,4,5)")
    complaint_number: Optional[str] = Field(..., description="Complaint number derived from ObjectId")


def store_customer_data_in_mongodb(data: dict):
    """
    Stores customer data in MongoDB after validating it against a schema.

    Args:
        data (dict): A dictionary containing customer data to be stored.

    Returns:
        str: The ID of the inserted document.
    """
    client = None
    try:
        # Validate data using the schema
        validated_data = CustomerData(**data)
        
        
        # Add timestamp in IST
        ist_timezone = pytz.timezone("Asia/Kolkata")
        validated_data.timestamp = datetime.now(ist_timezone)

        # Load MongoDB URI from environment variables
        mongo_url = os.getenv("MONGO_URI")
        if not mongo_url:
            raise ValueError("MONGO_URI is not set in environment variables.")

        # Connect to MongoDB
        client = MongoClient(mongo_url)
        db = client["customer_service"]
        collection = db["customer_info"]

        # Insert the validated data into the collection
        result = collection.insert_one(validated_data.dict())
        logger.info(f"Customer data stored in MongoDB with ID: {result.inserted_id}")

        return str(result.inserted_id)

    except Exception as e:
        logger.error(f"Failed to store customer data in MongoDB: {str(e)}")
        raise

    finally:
        if client:
            client.close()


class CustomerServiceFnc(llm.FunctionContext):
    def __init__(self):
        super().__init__()
        self.room = None
        self.participants = {}  # Store participant-specific data

    def set_room(self, room):
        self.room = room

    def add_participant(self, participant_id, participant):
        self.participants[participant_id] = participant

    @llm.ai_callable()
    async def submit_customer_info(
        self,
        name: Annotated[str, llm.TypeInfo(description="Customer's name in English")],
        address: Annotated[str, llm.TypeInfo(description="Customer's address in English")],
        product: Annotated[str, llm.TypeInfo(description="Product owned by customer in English")],
        issue: Annotated[str, llm.TypeInfo(description="Issue or complaint the customer is facing with the product in English")],
    ):
        """
        Called when all customer information has been collected. This function will submit the customer information to the system.
        """
        if not self.room:
            logger.error("Room context not set")
            return

       
        # Log the collected information with participant context
        logger.info(                                                                                             
            f"Submitting customer info for  - "
            f"Name: {name}, Address: {address}, Product: {product}, Issue: {issue}"
        )
        
        room_name = self.room.name
        # Format the data for submission with participant information
        customer_data = (
            f"NAME: {name}, ADDRESS: {address}, PRODUCT: {product}, ISSUE: {issue}, MOBILE: {get_mobile_number(room_name)}"
        )
        # You can also access room properties if needed
        logger.info(f"Submission from room: {room_name}")
        print(customer_data)
        
        try:
            # Prepare the data for submission
            customer_data = {
                "name": name,
                "address": address,
                "product": product,
                "issue": issue,
                "status":"pending",
                "mobile": get_mobile_number(room_name),
                "priority":"1",
                "complaint_number":str(random.randint(100, 9999))
                
            }

            # Log the customer data
            logger.info(f"Collected customer data: {customer_data}")

            # Store the data in MongoDB
            inserted_id = store_customer_data_in_mongodb(customer_data)
            # send_sms(customer_data['mobile'], "Hello! This is a test message.")
            send_sms(customer_data['mobile'], f"Hello {customer_data['name']}. Your Complaint Number is {customer_data['complaint_number']}")
            logger.info(f"Data stored successfully with ID: {inserted_id}")
            print(f"Customer data successfully stored in MongoDB with ID: {inserted_id}")

        except Exception as e:
            logger.error(f"Error while storing data: {e}")
            print(f"Error while storing data: {e}")
    @llm.ai_callable()     
    async def end_call(self):
        """
        Ends the call after successful completion of the conversation.
        This should be called after the final message has been spoken to the customer.
        """
        if not self.room:
            logger.error("Room context not set")
            return
        
        try:
            # Get the current participant being served
            participant = next(iter(self.participants.values()), None)
            if participant:
                logger.info(f"Disconnecting participant: {participant.identity}")
                await self.room.disconnect()  # Disconnect from the room
                logger.info("Call ended successfully")
                return "Call ended successfully"
            else:
                logger.error("No participant found to disconnect")
                return "No participant found to disconnect"
        except Exception as e:
            logger.error(f"Error ending call: {str(e)}")
            return f"Error ending call: {str(e)}"
        
    @llm.ai_callable()
    async def update_complaint_priority(
        self,
        complaint_number: Annotated[str, llm.TypeInfo(description="Customer's complaint number")],
    ):
        """
        Updates the priority of an existing complaint when a customer calls again regarding the same complaint.
        This function should be called when a customer mentions their existing complaint number.
        """
        try:
            mongo_url = os.getenv("MONGO_URI")
            if not mongo_url:
                raise ValueError("MONGO_URI is not set in environment variables.")

            client = MongoClient(mongo_url)
            db = client["customer_service"]
            collection = db["customer_info"]

            # Find the complaint using complaint number
            existing_complaint = collection.find_one(
                {"complaint_number": complaint_number, "status": "pending"}
            )

            if existing_complaint:
                current_priority = existing_complaint.get('priority', 1)
                new_priority = min(int(current_priority) + 1, 5)  # Cap priority at 5
                
                # Update the priority
                result = collection.update_one(
                    {"complaint_number": complaint_number},
                    {"$set": {
                        "priority": str(new_priority),
                        "timestamp": datetime.now(pytz.timezone("Asia/Kolkata"))
                    }}
                )
                
                logger.info(f"Updated priority for complaint #{complaint_number} "
                           f"from {current_priority} to {new_priority}")
                
                # Send SMS notification about priority update
                logger.info(f"existing_complaint: {existing_complaint}")
                mobile = existing_complaint['mobile']
                if mobile:
                    message = (
                        f"Your complaint (#{complaint_number}) priority has been increased to {new_priority}. "
                        "We will address it on priority basis."
                    )
                    send_sms(mobile, message)
                
                return f"Priority updated for complaint #{complaint_number} from {current_priority} to {new_priority}"

            return f"No pending complaint found with number {complaint_number}"

        except Exception as e:
            error_msg = f"Error updating complaint priority: {str(e)}"
            logger.error(error_msg)
            return error_msg
        
        finally:
            if 'client' in locals():
                client.close()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    fnc_ctx = CustomerServiceFnc()
    fnc_ctx.set_room(ctx.room)
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    fnc_ctx.add_participant(participant.identity, participant)
    room_name = ctx.room.name
    mobile_number = get_mobile_number(room_name)
    previous_complaint = check_previous_complaints(mobile_number)
    logger.info(f"previous_complaint: {'Number Exists' if previous_complaint != 0 else 'New Complaint'}")

    if previous_complaint != 0:
        initial_ctx = llm.ChatContext().append(
            role="system",
            text=(
               "You are a virtual call assistant for Benchmark Service Center. "
"I can see that you have contacted us before. Here are the details of your last complaint:\n"
f"- Complaint Number: {previous_complaint['complaint_number']}\n"
f"- Name: {previous_complaint['name']}\n"
f"- Product: {previous_complaint['product']}\n"
f"- Issue: {previous_complaint['issue']}\n"
f"- Status: {previous_complaint['status']}\n"
f"- Priority: {previous_complaint['priority']}\n\n"

"Your role is to handle this situation based on the following scenarios:\n"

"1. If calling about the SAME ISSUE (Priority Escalation):\n"
"   - Express concern about the unresolved issue\n"
"   - Confirm their complaint number\n"
"   - Use update_complaint_priority function with their complaint number\n"
"   - Example: update_complaint_priority(complaint_number='{previous_complaint['complaint_number']}')\n"
"   - After escalation, explain: 'I've increased the priority of your complaint. You'll receive an SMS confirmation.'\n\n"
"   - After submission, announce to user: 'You may now hang up the call'"

"2. If calling for a STATUS CHECK:\n"
"   - Share current status from the record\n"
"   - If status is 'pending' and customer is dissatisfied:\n"
"     * Say: 'I understand your concern. Let me escalate this for you.'\n"
"     * Use update_complaint_priority with their complaint number\n"
"     * Confirm the escalation\n\n"
"   - After submission, announce to user: 'You may now hang up the call'"

"3. For new complaints, you MUST follow this exact sequence:"
        "   a. First, ask ONLY for the customer's name: 'May I have your name, please?'"
        "   b. After getting the name, ask ONLY for the complete address: 'Could you please provide your complete address?'"
        "   c. After getting the address, ask ONLY about the product: 'Could you please tell me if you have a gas geyser or electric water heater, and its model name?'"
        "   d. Finally, ask about the specific issue: 'Please describe the problem you're experiencing with your product.'"
        "   e. Before submission:"
        "      - Summarize all collected information"
        "      - Ask for confirmation: 'I have collected the following information. Please confirm if everything is correct.'"
        "      - Only after confirmation, use submit_customer_info function"
        "      - Inform about SMS with complaint number"
        "   f. After submission, announce to user: 'You may now hang up the call'"

"Important Guidelines:\n"
"- Start by asking: 'Are you calling about your existing complaint number {previous_complaint['complaint_number']}, or do you have a new issue to report?'\n"
"- For same issue or escalation requests, ALWAYS use update_complaint_priority function\n"
"- Only use update_complaint_priority ONCE per call\n"
"- After using update_complaint_priority, always inform customer about SMS confirmation\n"
"- Never use submit_customer_info until ALL information is collected and confirmed"
"- Collect information one piece at a time"
"- Wait for clear response before moving to next question"
"- If any response is unclear, ask for clarification before moving forward"
"- Be empathetic and professional throughout"
"After completing the operation (either submitting new complaint or updating priority):"
"  * Thank the customer"
"  * Inform them they will receive an SMS"
"  * Say: 'Thank you for calling Benchmark Service Center. Goodbye!'"
"  * MUST use end_call function to disconnect the call"
            ),
        )
    else:
        initial_ctx = llm.ChatContext().append(
    role="system",
    text=(
        "You are a virtual female call assistant for Benchmark Service Center, providing professional and empathetic customer service in English."

        "For New Callers, there are two possible scenarios:"

        "1. Customer has an existing complaint but doesn't know the complaint number:"
        "   - Ask: 'Do you have an existing complaint with us?'"
        "   - If yes, ask for details about their previous complaint"
        "   - Use these details to find their complaint number"
        "   - Once complaint number is confirmed:"
        "     * Use update_complaint_priority function with their complaint number"
        "     * Example: update_complaint_priority(complaint_number='1234')"
        "     * Inform them about SMS confirmation of priority escalation"
        "   - After submission, announce to user: 'You may now hang up the call'"

       "2. For new complaints, you MUST follow this exact sequence:"
        "   a. First, ask ONLY for the customer's name: 'May I have your name, please?'"
        "   b. After getting the name, ask ONLY for the complete address: 'Could you please provide your complete address?'"
        "   c. After getting the address, ask ONLY about the product: 'Could you please tell me if you have a gas geyser or electric water heater, and its model name?'"
        "   d. Finally, ask about the specific issue: 'Please describe the problem you're experiencing with your product.'"
        "   e. Before submission:"
        "      - Summarize all collected information"
        "      - Ask for confirmation: 'I have collected the following information. Please confirm if everything is correct.'"
        "      - Only after confirmation, use submit_customer_info function"
        "      - Inform about SMS with complaint number"
        "   f. After submission, announce to user: 'You may now hang up the call'"

       "IMPORTANT:"
        "- Never use submit_customer_info until ALL information is collected and confirmed"
        "- Collect information one piece at a time"
        "- Wait for clear response before moving to next question"
        "- If any response is unclear, ask for clarification before moving forward"
        "- Maintain professional and empathetic tone throughout"
"After completing the operation (either submitting new complaint or updating priority):"
"  * Thank the customer"
"  * Inform them they will receive an SMS"
"  * Say: 'Thank you for calling Benchmark Service Center. Goodbye!'"
"  * MUST use end_call function to disconnect the call"
    ),
)

    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM.with_groq(),
        tts=google.TTS(credentials_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),language="en-IN"),
        chat_ctx=initial_ctx,
        fnc_ctx=fnc_ctx,
    )

    assistant.participant_id = participant.identity
    assistant.start(ctx.room, participant)

    if previous_complaint != 0:
        await assistant.say(
            f"Welcome back to Benchmark Service Center. I can see your previous complaint number {previous_complaint['complaint_number']}. "
            "How may I assist you today? Are you calling about the same issue or do you have a new complaint?",
            allow_interruptions=True
        )
    else:
        await assistant.say(
            "Welcome to Benchmark Service Center. How can I help you today?",
            allow_interruptions=True
        )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )