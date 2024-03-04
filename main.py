# ________  ________      ___    ___ ________  _________  ________          ________  ___  ___  _________  ___  ________  _________  ___  ________
#|\   ____\|\   __  \    |\  \  /  /|\   __  \|\___   ___\\   __  \        |\   __  \|\  \|\  \|\___   ___\\  \|\   ____\|\___   ___\\  \|\   ____\
#\ \  \___|\ \  \|\  \   \ \  \/  / | \  \|\  \|___ \  \_\ \  \|\  \       \ \  \|\  \ \  \\\  \|___ \  \_\ \  \ \  \___|\|___ \  \_\ \  \ \  \___|
# \ \  \    \ \   _  _\   \ \    / / \ \   ____\   \ \  \ \ \  \\\  \       \ \   __  \ \  \\\  \   \ \  \ \ \  \ \_____  \   \ \  \ \ \  \ \  \
#  \ \  \____\ \  \\  \|   \/  /  /   \ \  \___|    \ \  \ \ \  \\\  \       \ \  \ \  \ \  \\\  \   \ \  \ \ \  \|____|\  \   \ \  \ \ \  \ \  \____
#   \ \_______\ \__\\ _\ __/  / /      \ \__\        \ \__\ \ \_______\       \ \__\ \__\ \_______\   \ \__\ \ \__\____\_\  \   \ \__\ \ \__\ \_______\
#    \|_______|\|__|\|__|\___/ /        \|__|         \|__|  \|_______|        \|__|\|__|\|_______|    \|__|  \|__|\_________\   \|__|  \|__|\|_______|
#                      \|___|/                                                                                   \|_________|

#          ___  _____ ______   ________  ________  ___  ________   _______   _______   ________
#         |\  \|\   _ \  _   \|\   __  \|\   ____\|\  \|\   ___  \|\  ___ \ |\  ___ \ |\   __  \
#         \ \  \ \  \\\__\ \  \ \  \|\  \ \  \___|\ \  \ \  \\ \  \ \   __/|\ \   __/|\ \  \|\  \
#          \ \  \ \  \\|__| \  \ \   __  \ \  \  __\ \  \ \  \\ \  \ \  \_|/_\ \  \_|/_\ \   _  _\
#           \ \  \ \  \    \ \  \ \  \ \  \ \  \|\  \ \  \ \  \\ \  \ \  \_|\ \ \  \_|\ \ \  \\  \|
#            \ \__\ \__\    \ \__\ \__\ \__\ \_______\ \__\ \__\\ \__\ \_______\ \_______\ \__\\ _\
#             \|__|\|__|     \|__|\|__|\|__|\|_______|\|__|\|__| \|__|\|_______|\|_______|\|__|\|__|
#
# SShift DAO - 2023
# http://www.sshift.xyz
#
import logging
import logging.handlers
import os

import nextcord
from nextcord.ext import commands

from database.user_database import create_table
from server import keep_alive


def setup_logging():
  """Configure logging for the bot."""
  logger = logging.getLogger('discord')
  logger.setLevel(logging.DEBUG)

  handler = logging.handlers.RotatingFileHandler(filename='discord.log',
                                                 encoding='utf-8',
                                                 maxBytes=10**7,
                                                 backupCount=1)
  console_handler = logging.StreamHandler()

  fmt = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
  handler.setFormatter(fmt)
  console_handler.setFormatter(fmt)

  logger.addHandler(handler)
  logger.addHandler(console_handler)

  return logger

def load_cogs(bot, logger):
  """Load all cogs from the cogs directory."""
  cogs_directory = "cogs"

  # Load all cogs
  for filename in os.listdir(cogs_directory):
    if filename.endswith(".py"):
      cog_path = f"{cogs_directory}.{filename[:-3]}"  # Removes the .py extension
      try:
        bot.load_extension(cog_path)
        logger.info(f"Loaded cog: {cog_path}")
      except Exception as e:
        logger.error(f"Failed to load cog: {cog_path}. Error: {e}")

# Set up logging
logger = setup_logging()

# Create an Intents object with all intents enabled
intents = nextcord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
  logger.info(f'Logged in as {bot.user.name}!')

  # Initialize the database
  await create_table()
  logger.info('Database initialized.')

# Load cogs
load_cogs(bot, logger)

keep_alive()

# Start the bot
bot.run(os.getenv('DISCORD_TOKEN'))