#Imports

import asyncio
import json
import logging
import os

import aiosqlite
import openai
from nextcord.ext import commands

from database.user_database import upsert_user_thread
from functions.function_calls import (
    generate_image_with_dalle,
    get_crypto_info_from_coinmarketcap,
    get_stock_info,
    get_trending_cryptos,
    mediawiki_query,
    query_arxiv,
    query_wolfram_alpha,
)

# Initialize logging
logging.basicConfig(level=logging.INFO, filename='discord.log', filemode='a', 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('discord')

logger.info("Starting HeliusChatBot session.")

# Configure OpenAI client
client = openai.OpenAI()
openai.api_key = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

# Check for essential configurations
if not openai.api_key:
    logger.critical("No OPENAI_API_KEY found. Please set the OPENAI_API_KEY environment variable.")
    raise ValueError("No OPENAI_API_KEY found. Please set the OPENAI_API_KEY environment variable.")

if not ASSISTANT_ID:
    logger.critical("No ASSISTANT_ID found. Please set the ASSISTANT_ID environment variable.")
    raise ValueError("No ASSISTANT_ID found. Please set the ASSISTANT_ID environment variable.")

logger.info("OpenAI client configured successfully with ASSISTANT_ID.")

# Dynamic function call mapping
function_mapping = {
    'get_stock_info': get_stock_info,
    'query_wolfram_alpha': query_wolfram_alpha,
    'get_crypto_info_from_coinmarketcap': get_crypto_info_from_coinmarketcap,
    'mediawiki_query': mediawiki_query,
    'generate_image_with_dalle': generate_image_with_dalle,
    'query_arxiv': query_arxiv,
    'get_trending_cryptos': get_trending_cryptos,
    # Add other function mappings here
}

logger.info("Function mappings have been initialized.")

async def wait_on_run(client, thread_id, run_id, check_interval=4.5):
    logger.info(f"Waiting on run {run_id} in thread {thread_id}")
    while True:
        await asyncio.sleep(check_interval)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.status in ["requires_action", "completed"]:
            logger.info(f"Run {run_id} status: {run.status}")
            return run

class HeliusChatBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_semaphore = asyncio.Semaphore(50)  # Control API call rate
        self.user_threads = {}  # User-specific threads
        self.last_bot_message_id = {}  # Track last message IDs per user
        self.helius_assistant_id = ASSISTANT_ID
        self.allowed_channel_ids = [1209270991948349461, 1137349870194270270, 1101204273339056139]  # Customize as needed
        self.message_queues = {}  # Queue for managing messages per thread
        logger.info("HeliusChatBot cog initialized.")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"{self.bot.user} is connected to Discord.")
        async with aiosqlite.connect('database/user_threads.db') as db:
            async with db.execute("SELECT user_id, thread_id FROM user_threads") as cursor:
                async for row in cursor:
                    self.user_threads[int(row[0])] = row[1]
        logger.info("User threads loaded from the database.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.channel.id not in self.allowed_channel_ids:
            return

        logger.info(f"Message from {message.author}: {message.content}")

        is_mention = self.bot.user in message.mentions
        is_reply = message.reference and message.reference.message_id == self.last_bot_message_id.get(message.author.id)

        if is_mention or is_reply:
            user_id = message.author.id
            thread_id = self.user_threads.get(user_id)

            if thread_id is None:
                thread_id = await self.create_thread_for_user(user_id)

            # Queue management
            if thread_id not in self.message_queues:
                self.message_queues[thread_id] = asyncio.Queue()
            await self.message_queues[thread_id].put((user_id, message))
            if self.message_queues[thread_id].qsize() == 1:  # If this is the only message, start processing
                asyncio.create_task(self.process_message_queue(thread_id))

    async def process_message_queue(self, thread_id):
        while not self.message_queues[thread_id].empty():
            user_id, message = await self.message_queues[thread_id].get()
            async with self.api_semaphore:
                try:
                    async with message.channel.typing():
                        await self.process_user_message(user_id, thread_id, message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await message.channel.send("Sorry, I encountered an error handling your request.")
                finally:
                    self.message_queues[thread_id].task_done()

    async def create_thread_for_user(self, user_id):
        loop = asyncio.get_event_loop()
        thread = await loop.run_in_executor(None, lambda: client.beta.threads.create())
        self.user_threads[user_id] = thread.id
        logger.info(f"New thread created for user {user_id}: {thread.id}")
        # Upsert the thread ID into the database asynchronously
        await upsert_user_thread(user_id, thread.id)
        return thread.id

    async def process_user_message(self, user_id, thread_id, message):
        loop = asyncio.get_event_loop()
        # Add the user's message to the thread
        await loop.run_in_executor(None, lambda: client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message.content))
        logger.info(f"Message from user {user_id} added to thread {thread_id}.")
    
        # Create a new run for the current thread and wait for its completion
        run_id = await loop.run_in_executor(None, lambda: client.beta.threads.runs.create(thread_id=thread_id, assistant_id=self.helius_assistant_id).id)
        run = await wait_on_run(client, thread_id, run_id)
    
        # Check if the run requires action and process accordingly
        if run.status == "requires_action":
            tool_outputs = []
            for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                logger.info(f"Function {function_name} with arguments {arguments} needs to be called.")
    
                # Execute the function if it's in our mapping
                if function_name in function_mapping:
                    function_to_call = function_mapping[function_name]
                    try:
                        output = await function_to_call(**arguments)
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps(output)
                        })
                        logger.info(f"Function {function_name} called successfully.")
                    except Exception as e:
                        logger.error(f"Error calling function {function_name}: {e}")
                        tool_outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": json.dumps({"error": str(e)})
                        })
    
            # Submit the results of the function calls and update the run status
            await loop.run_in_executor(None, lambda: client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs
            ))
            logger.info(f"Tool outputs submitted for run {run.id}.")
    
            # Re-check the run status after submitting tool outputs
            run = await wait_on_run(client, thread_id, run.id)
            if run.status == "completed":
                # Retrieve and send the latest message from the assistant to the user
                final_message = await self.get_final_message_from_thread(thread_id)
                await self.send_final_message(user_id, message.channel, final_message)
            else:
                logger.error(f"Run {run.id} did not complete as expected. Status: {run.status}")
                await message.channel.send("Sorry, I encountered an issue processing your request. Please try again.")
        else:
            # In case the status is not 'requires_action' but is 'completed', directly fetch the final message
            final_message = await self.get_final_message_from_thread(thread_id)
            await self.send_final_message(user_id, message.channel, final_message)


    async def get_final_message_from_thread(self, thread_id):
        loop = asyncio.get_event_loop()
        # Retrieve all messages from the thread
        messages = await loop.run_in_executor(None, lambda: client.beta.threads.messages.list(thread_id=thread_id, order="desc", limit=1).data)
        # Filter messages to only retrieve those sent by the assistant
        assistant_messages = [msg for msg in messages if msg.role == "assistant"]
        if assistant_messages:
            # Assuming messages are structured with a content list and you're interested in the first item's text value
            return assistant_messages[0].content[0].text.value if assistant_messages[0].content else "I've processed your request."
        else:
            return "I've processed your request, but I don't have anything more to say."

  
    async def send_final_message(self, user_id, channel, final_message):
        if len(final_message) > 2000:
            for part in [final_message[i:i+2000] for i in range(0, len(final_message), 2000)]:
                await channel.send(part)
        else:
            sent_message = await channel.send(final_message)
            self.last_bot_message_id[user_id] = sent_message.id
        logger.info(f"Final response sent to user {user_id}.")

def setup(bot):
    try:
        bot.add_cog(HeliusChatBot(bot))
        logger.info("HeliusChatBot cog has been added to the bot.")
    except Exception as e:
        logger.error(f"Error adding HeliusChatBot cog to the bot: {e}")
