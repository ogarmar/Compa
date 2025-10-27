# Compa: Your Voice Companion

Compa is a next-generation conversational AI assistant designed to deliver a personalized and empathetic user experience. Built with modular architecture, Compa seamlessly integrates a generative AI model, memory management, real-time communication, and family messaging features. This project is ideal for research, personal use, and as a foundation for advanced AI companion applications.

***

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

***

## Features

- **Personalized Conversations:** Remember past interactions and context for deeper engagement.
- **Empathetic Generative Responses:** AI-driven replies tailored to the user’s emotional and conversational needs.
- **Memory Functionality:** Store and recall user memories, preferences, and important events.
- **Family Messaging:** Retrieve and read family messages from Telegram, helping users stay close to loved ones.
- **Intuitive User Interface:** Accessible frontend with voice/text support and real-time connection.

***

## Architecture Overview

Compa is built on a modular architecture, enabling clear separation of responsibilities and easy extensibility. The main components are the FastAPI backend, the generative AI integration, Telegram bot support, user memory management, and a modern front end with voice capabilities.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                           │
│┌──────────┐ ┌──────────────┐ ┌───────────────────┐         │
││  HTML UI │ │ JavaScript   │ │ Web Speech API    │         │
│└────┬─────┘ └──────┬───────┘ └─────────┬─────────┘         │
└─────┼──────────────┼────────────────────┼──────────────────┘
      │       WebSocket Connection        │
┌─────┼──────────────┼────────────────────┼──────────────────┐
│     │              ▼                    │                  │
│ ┌───┴─────────────────────────────┐      │                 │
│ │       main.py (FastAPI)         │      │                 │
│ │ ┌─────────────────────────────┐ │      │                 │
│ │ │  WebSocket Endpoint (/ws)   │ │      │                 │
│ │ │ - Accept connections        │ │      │                 │
│ │ │ - Load user memory          │ │      │                 │
│ │ │ - Route messages            │ │      │                 │
│ │ └──────────┬──────────────────┘ │      │                 │
│ └────────────┼────────────────────┘      │                 │
│              │                           │                 │
│     ┌────────┼────────────┐              │                 │
│     ▼        ▼            ▼              ▼                 │
│ ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐     │
│ │ Memory  │ │ Telegram │ │ Gemini   │ │ Static Files │     │
│ │ Manager │ │   Bot    │ │  AI      │ │              │     │
│ └─────────┘ └──────────┘ └──────────┘ └──────────────┘     │
│     │          │            │                              │
│     ▼          ▼            ▼                              │
│ ┌─────────────────────────────────────┐                   │
│ │      External Services              │                   │
│ │ - User Memory Storage (JSON/DB)     │                   │
│ │ - Telegram API                      │                   │
│ │ - Google Gemini API                 │                   │
│ └─────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

***

## Repository Structure

```
Compa/
│
├── backend/
│   ├── main.py              # FastAPI backend and WebSocket
│   ├── telegram_bot.py      # Telegram bot integration
│
├── frontend/
│   ├── static/
│   │   ├── index.html       # Main UI
│   │   ├── style.css        # Interface stylesheet
│   │   └── app.js           # WebSocket, UI logic, speech features
│
├── requirements.txt         # Backend Python dependencies
├── .env                     # Environment configuration (not committed)
└── README.md                # Documentation
```

***

## Getting Started

### Prerequisites

- Python >= 3.11
- Telegram account to set up the bot
- API access to Google Gemini (via developer token)

### Installation Steps

1. **Clone the repository:**
    ```
    git clone https://github.com/ogarmar/Compa.git
    cd Compa
    ```
2. **Install Python dependencies:**
    ```
    pip install -r requirements.txt
    ```
3. **Configure environment variables (`.env`):**
    ```
    GEMINI_TOKEN=your_gemini_api_key
    TELEGRAM_BOT_TOKEN=your_telegram_bot_token
    ```
4. **Start the backend server:**
    ```
    python backend/main.py
    ```
5. **Open the frontend in your browser:**
    - Go to `http://localhost:8000` (by default)

***

## Configuration

Compa uses environment variables for sensitive information. Add the following variables to a `.env` file in your project root:

```
GEMINI_TOKEN=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

***

## Core Components

### Backend (FastAPI + WebSocket)
- Handles all application logic and connections.
- Manages WebSocket endpoint `/ws` for real-time communication.
- Loads and persists user memories.
- Processes incoming requests: general chat, family messages, and memory recall.
- Generates responses using the Gemini generative model.

### Telegram Bot Integration
- Retrieves family messages from Telegram chats.
- Handles daily and unread message requests.
- Integrates seamlessly with backend via API calls.

### Memory Management
- Tracks user conversations, events, important dates, preferences.
- Stores, loads, queries, and updates memory objects for rich context.
- Enables personalized, consistent, and context-aware responses.

### Generative AI Model (Gemini)
- Empathetic response generation.
- Integrates memory and conversational context.
- Customizable via prompt engineering.

### Frontend (HTML/CSS/JavaScript)
- WebSocket client for real-time messaging.
- Voice input with Web Speech API.
- Family messages and memory recall UI features.

***

## Data Flow

1. **User interacts via frontend (text/voice):**
   - Input sent to backend over WebSocket.
2. **Backend processes input:**
   - Loads user memory, checks message type.
   - Queries Gemini for generative response or Telegram bot for family messages.
   - Updates memory as needed.
3. **Backend responds:**
   - Sends reply back over WebSocket.
   - Response is displayed and (optionally) spoken using frontend speech synthesis.
4. **Session and memory continuity:**
   - Past interactions influence ongoing conversation.

***

## Security Considerations

- **Environment variable protection:** Do not commit `.env` files.
- **API key safety:** Store keys securely and rotate regularly.
- **WebSocket validation:** (Recommended) Authenticate connections for production.

***

## Troubleshooting

- **WebSocket connection issues?:** Confirm backend is running; check CORS settings.
- **Gemini API errors?:** Verify your token, quota, and API service status.
- **Telegram bot not responding?:** Double-check token, bot status, and internet connectivity.

***

## Contributing

Contributions are welcome! Feel free to contact oscargarciatrabajos@gmail.com to discuss your ideas, improvements, or issues. Pull requests and issues are also accepted via GitHub.

***

## License

MIT License

***

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/)
- [Python-Telegram-Bot](https://python-telegram-bot.org/)
- [Google Gemini](https://ai.google.dev/)
- All open-source contributors and projects that make Compa possible.

***

Enjoy talking, sharing and building with Compa!
