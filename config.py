import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# Superadmin IDs (comma-separated)
SUPERADMIN_IDS = ]
    int(x) for x in os.getenv('SUPERADMIN_IDS', '').split(',') if x.strip()
]