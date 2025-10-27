# Compa: Your Voice Companion

Compa is a voice assistant application that aims to provide a personalized and empathetic experience for users. It is built using a combination of backend and frontend components.

## Overview

Compa is designed to be a conversational AI assistant that can engage in meaningful conversations with users. It leverages a generative model to generate responses that are empathetic, understanding, and helpful. The backend component handles the logic and communication with the generative model, while the frontend provides a user-friendly interface for interacting with the assistant.

## Features

- Personalized Conversations: Compa is designed to engage in empathetic and understanding conversations with users. It can remember past interactions and continue the conversation based on context.
- Family Messages: Compa can retrieve and read out family messages, providing a convenient way for users to stay connected with their loved ones.
- Memory Functionality: Compa can store and recall important memories, allowing users to reminisce and engage in meaningful conversations about their past experiences.
- User-Friendly Interface: The frontend of Compa provides a simple and intuitive interface for users to interact with the assistant.

## Architecture

Compa consists of two main components: the backend and the frontend.

### Backend

The backend component of Compa is responsible for handling the logic and communication with the generative model. It includes the following key components:

- WebSocket Endpoint: The backend provides a WebSocket endpoint `/ws` for real-time communication between the frontend and the assistant.
- Memory Management: The backend manages user memory by storing and retrieving important messages and memories.
- Generative Model: The backend interacts with the generative model to generate responses based on user input.

1. main.py
   main.py is the entry point of the backend. It initializes the FastAPI application and sets up the WebSocket endpoint /ws for real-time communication between the frontend and the assistant.

The websocket_endpoint function is the handler for the WebSocket endpoint. It accepts the WebSocket connection, loads the user's memory, and enters a loop to handle incoming messages from the client. It checks if the incoming message is a request for family messages and processes the request accordingly. It also handles other types of requests, such as memory questions, and generates responses using a generative model.

2. telegram_bot.py
   telegram_bot.py contains the logic for interacting with the Telegram bot. It initializes the Telegram bot using the provided TELEGRAM_BOT_TOKEN environment variable. The get_unread_messages function retrieves unread messages from the bot's chat history. The get_messages_today function retrieves messages from today's date. The load_messages function loads all messages from the bot's chat history.

The get_unread_messages function is used by the websocket_endpoint function to retrieve unread messages for the family messages feature. The get_messages_today function is used to retrieve messages from today's date for the family messages feature. The load_messages function is used to load all messages from the bot's chat history.

### Frontend

The frontend component of Compa provides a user-friendly interface for interacting with the assistant. It includes the following key features:

- User Interface: The frontend provides a simple and intuitive interface for users to input their queries and view responses.
- WebSocket Communication: The frontend establishes a WebSocket connection with the backend to send and receive messages in real-time.
- Static Files: The frontend includes static files such as HTML, CSS, and JavaScript to render the user interface.

## Getting Started

To get started with Compa, follow these steps:

1. Clone the repository: `git clone <repository_url>`
2. Install dependencies: `pip install -r requirements.txt`
3. Start the backend: `python .\backend\main.py`

## Configuration

Compa can be configured using environment variables. The following variables are used:

- `GEMINI_TOKEN`: The API token for accessing the generative model.
- `TELEGRAM_BOT_TOKEN`: The API token for accessing the Telegram bot.

## Contributing

Contributions to Compa are welcome! If you would like to contribute, please follow write me an email about how you want to improve it, or in which way you have alredy done oscargarciatrabajos@gmail.com.

## License

Compa is licensed under the [MIT License](LICENSE).

## Acknowledgments

Compa is built using a combination of open-source libraries (and other API's) and frameworks. We would like to thank the following projects for their contributions:

- [FastAPI](https://fastapi.tiangolo.com/)
- [Python-Telegram-Bot](https://python-telegram-bot.readthedocs.io/)
- [Gemini](https://ai.google.dev/gemini-api)
