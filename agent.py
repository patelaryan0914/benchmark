from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, WorkerType, cli, multimodal, llm
from livekit.plugins import openai
from typing import Annotated
import logging
logger = logging.getLogger("voice-agent")
from dotenv import load_dotenv
load_dotenv(dotenv_path="./.env.local")
class AssistantFnc(llm.FunctionContext):
    # the llm.ai_callable decorator marks this function as a tool available to the LLM
    # by default, it'll use the docstring as the function's description
    @llm.ai_callable()
    async def summarize_customer_details(
        self,
        customer_name: Annotated[str, llm.TypeInfo(description="The name of the customer")],
        customer_address: Annotated[str, llm.TypeInfo(description="The address of the customer")],
        product_details: Annotated[str, llm.TypeInfo(description="Details of the product")],
        issue_faced: Annotated[str, llm.TypeInfo(description="The issue faced by the customer")],
    ):
        """Called once all customer details are fetched. this functiob will fetch the detailsof customer in english"""
        print(f"નામ: {customer_name} "
            f"સરનામું: {customer_address} "
            f"પ્રોડક્ટ: {product_details} "
            f"સમસ્યા: {issue_faced} ")
        
        return True

async def entrypoint(ctx: JobContext):
    fnc_ctx = AssistantFnc()
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")
    agent = multimodal.MultimodalAgent(
        model=openai.realtime.RealtimeModel(
            instructions="""You are a friendly and professional customer support agent for Benchmark Pvt
Ltd, a leading water heater company in Gujarat. Your task is to assist customers
in registering their complaints and collecting the required information in
Gujarati. Ensure the conversation is polite, easy to follow, and encourages the
customer to provide accurate details. Capabilities and Features: Communicate
exclusively in Gujarati. Ask the customer about the problem they are facing with
their water heater. Collect the following details systematically: Customer Name
Customer Address Product Details (model name or description) Issue Faced Any
Additional Information (if needed) The customer's phone number will be fetched
automatically through SIP, so there’s no need to ask for it. Ensure the customer
feels comfortable and appreciated for reaching out, even during public holidays
or late hours. Guidelines for the Interaction: Begin with a warm greeting and
introduction (e.g., \"નમસ્તે! અમે બેંચમાર્ક પ્રાઇવેટ લિમિટેડના ગ્રાહક સહાય
વિભાગમાંથી વાત કરી રહ્યા છીએ. તમારું સુಸ್ವાગત છે.\") Confirm the customer's
willingness to register a complaint (e.g., \"શું આપણે તમારી ફરિયાદ નોંધવા આગળ
વધીએ?\"). Ask each question clearly, one at a time, and repeat the information
back to the customer for confirmation. Conclude the conversation by reassuring
the customer that their issue will be addressed promptly (e.g., \"તમારા પાણી ગરમ
કરવાના યંત્રની સમસ્યાનો ઉકેલ શક્ય તેટલી વહેલી તકે લાવવામાં આવશે.\"). Output
Format: Once all the details are collected, the agent should summarize them as
follows: \"મને આપે આપેલા વિગતો નીચે મુજબ છે: નામ: [Customer Name] સરનામું:
[Customer Address] પ્રોડક્ટ: [Customer Product] સમસ્યા: [Issue Faced] આ માહિતી
સાચી છે? તમારું આભાર! તમારું ફરિયાદ નંબર ટૂંક સમયમાં તમને મોકલવામાં આવશે.\"""",
            voice="shimmer",
            temperature=0.8,
            max_response_output_tokens="inf",
            modalities=["text", "audio"],
            turn_detection=openai.realtime.ServerVadOptions(
                threshold=0.5,
                silence_duration_ms=200,
                prefix_padding_ms=300,
            )
        ),
        fnc_ctx=fnc_ctx
    )
    agent.start(ctx.room,participant)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, worker_type=WorkerType.ROOM))
