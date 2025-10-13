class VoiceAssistant {
    constructor() {
        this.ws = null;
        this.isListening = false;
        this.isConnected = false;
        this.recognition = null;
        
        this.initializeElements();
        this.initializeWebSocket();
        this.initializeSpeechRecognition();
    }

    initializeElements() {
        this.micButton = document.getElementById('micButton');
        this.statusDiv = document.getElementById('status');
        this.conversationDiv = document.getElementById('conversation');
        this.memoryList = document.getElementById('memoryList');
        this.showMemoriesBtn = document.getElementById('showMemories');

        this.micButton.addEventListener('click', () => this.toggleListening());
        this.showMemoriesBtn.addEventListener('click', () => this.loadMemories());
    }

    initializeWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            this.isConnected = true;
            this.updateStatus('Conectado ✓', 'success');
        };

        this.ws.onmessage = (event) => {
            this.addMessage(event.data, 'assistant');
            this.speakText(event.data);
        };

        this.ws.onclose = () => {
            this.isConnected = false;
            this.updateStatus('Desconectado - Reconectando...', 'error');
            setTimeout(() => this.initializeWebSocket(), 3000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('Error de conexión', 'error');
        };
    }

    initializeSpeechRecognition() {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            this.recognition.lang = 'es-ES';
            this.recognition.maxAlternatives = 1;

            this.recognition.onstart = () => {
                this.isListening = true;
                this.micButton.classList.add('listening');
                this.updateStatus('Escuchando... 🎤', 'listening');
            };

            this.recognition.onend = () => {
                this.isListening = false;
                this.micButton.classList.remove('listening');
                if (this.isConnected) {
                    this.updateStatus('Conectado ✓', 'success');
                } else {
                    this.updateStatus('Desconectado', 'error');
                }
            };

            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                this.addMessage(transcript, 'user');
                this.sendMessage(transcript);
            };

            this.recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                this.isListening = false;
                this.micButton.classList.remove('listening');
                this.updateStatus('Error de reconocimiento: ' + event.error, 'error');
            };

        } else {
            this.updateStatus('El reconocimiento de voz no es compatible con este navegador', 'error');
            this.micButton.disabled = true;
            this.micButton.innerHTML = '<span class="mic-icon">🚫</span><span>No compatible</span>';
        }
    }

    toggleListening() {
        if (!this.recognition) return;

        if (this.isListening) {
            this.recognition.stop();
        } else {
            try {
                this.recognition.start();
            } catch (error) {
                console.error('Error starting recognition:', error);
                this.updateStatus('Error al iniciar el micrófono', 'error');
            }
        }
    }

    sendMessage(message) {
        if (this.isConnected && this.ws) {
            this.ws.send(message);
        } else {
            this.updateStatus('No conectado al servidor', 'error');
        }
    }

    addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        messageDiv.innerHTML = `<strong>${sender === 'user' ? 'Tú' : 'Acompaña'}:</strong> ${text}`;
        
        this.conversationDiv.appendChild(messageDiv);
        this.conversationDiv.scrollTop = this.conversationDiv.scrollHeight;
    }

    updateStatus(text, type) {
        this.statusDiv.textContent = text;
        this.statusDiv.className = `status status-${type}`;
    }

    speakText(text) {
        if ('speechSynthesis' in window) {
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'es-ES';
            utterance.rate = 0.9;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
            
            
            const voices = speechSynthesis.getVoices();
            const spanishVoice = voices.find(voice => 
                voice.lang.includes('es') || voice.lang.includes('ES')
            );
            
            if (spanishVoice) {
                utterance.voice = spanishVoice;
            }
            
            speechSynthesis.speak(utterance);
        }
    }

    async loadMemories() {
        try {
            const response = await fetch('/memory/cofre');
            const data = await response.json();
            
            this.memoryList.innerHTML = '';
            
            if (data.important_memories && data.important_memories.length > 0) {
                data.important_memories.forEach(memory => {
                    const memoryItem = document.createElement('div');
                    memoryItem.className = 'memory-item';
                    memoryItem.innerHTML = `
                        <strong>Recuerdo #${memory.id}:</strong> ${memory.content}
                        <br><small>${new Date(memory.timestamp).toLocaleDateString('es-ES')}</small>
                    `;
                    this.memoryList.appendChild(memoryItem);
                });
            } else {
                this.memoryList.innerHTML = '<div class="memory-item">Aún no hay recuerdos guardados en el cofre.</div>';
            }
        } catch (error) {
            console.error('Error loading memories:', error);
            this.memoryList.innerHTML = '<div class="memory-item">Error al cargar los recuerdos.</div>';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new VoiceAssistant();
});

if ('speechSynthesis' in window) {
    speechSynthesis.onvoiceschanged = () => {
        console.log('Voces cargadas:', speechSynthesis.getVoices());
    };
}