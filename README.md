# Telegram Growth Engine

Multi-tenant Telegram bot platform for channel management, auto-approve join requests, welcome DMs, analytics, and bot cloning.

## Features
- Auto-approve join requests with instant/drip/manual modes
- Welcome DM with variable substitution and media support
- Multi-language welcome messages
- Force subscribe requirements
- Broadcast engine with segmentation and scheduling
- Drip/batch approve system
- Bot cloning (white-label)
- Cross-promotion network
- Analytics dashboard with charts
- Premium tier system (Free/Premium/Business)
- Auto poster for groups
- Referral system with coins
- Superadmin panel

## Tech Stack
- Python 3.11+ with python-telegram-bot 21.3
- Supabase PostgreSQL via asyncpg
- Deployed on Render
- APScheduler for background jobs
- aiohttp for webhook server + health checks

## Quick Setup
1. Clone this repo
2. Create Supabase project, run `database/migrations/001_initial_schema.sql`
3. Create bot via @BotFather
4. Set environment variables (see `.env.example`)
5. Deploy to Render
6. Set up UptimeRobot to ping `/health` endpoint
7. Add bot as admin to your Telegram channel

## Environment Variables
See `.env.example` for all required variables.

## Architecture
- Multi-tenant: each channel owner sees only their data
- Superadmin sees everything
- Clone bots run as separate Application instances sharing the same DB
- Webhook-based with health endpoint for UptimeRobot
