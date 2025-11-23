// Check if app.js has already been loaded to prevent duplicate execution
if (window.__ACOMPANIA_APPJS_LOADED) {
  console.warn('app.js ya inicializado — evitando ejecución duplicada');
} else {
  // Set flag to indicate app.js is loaded
  window.__ACOMPANIA_APPJS_LOADED = true;

  (function () {
    // ============================================
    // CONFIG - Application settings and constants
    // ============================================
    // Construct WebSocket URL based on current protocol (http/https)
    const WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    // RMS (Root Mean Square) threshold for audio detection sensitivity
    let rmsThreshold = 0.17; 
    // Milliseconds of silence needed before sending recognized text
    const SILENCE_TO_SEND_MS = 1000;
    // Milliseconds interval for WebSocket keep-alive ping messages
    const KEEPALIVE_MS = 60000;
    // Delay before restarting speech recognition after it stops
    const RESTART_RECOGNITION_DELAY_MS = 300;
    // Enable detailed console logging for debugging
    const VERBOSE = false;

    // ============================================
    // LocalStorageManager - Persistent data storage
    // ============================================
    class LocalStorageManager {
      constructor() {
          // Key used to store all app data in browser localStorage
          this.storageKey = 'alzheimer_app_data';
      }

      // Generate a unique 6-digit code for device identification
      generateDeviceCode() {
          let code;
          do {
              code = Math.floor(100000 + Math.random() * 900000).toString();
          } while (code.length !== 6);
          return code;
      }

      // Generate unique device ID in format: device_XXXXXX
      generateUniqueDeviceId() {
          const code = this.generateDeviceCode();
          return `device_${code}`;
      }

      // Save application data to localStorage
      saveData(data) {
          try {
              const currentData = this.loadData() || {};
              
              // IMPORTANT: Preserve original device_id and device_code to avoid conflicts
              const dataToSave = {
                  device_id: data.device_id || currentData.device_id || this.generateUniqueDeviceId(),
                  device_code: data.device_code || currentData.device_code || this.generateDeviceCode(),
                  user_memory: data.user_memory || currentData.user_memory || {},
                  conversation_history: data.conversation_history || currentData.conversation_history || [],
                  last_updated: new Date().toISOString(),
                  created_at: currentData.created_at || new Date().toISOString()
              };
              
              localStorage.setItem(this.storageKey, JSON.stringify(dataToSave));
              console.log(`✅ Datos guardados - Device: ${dataToSave.device_id} - Código: ${dataToSave.device_code}`);
              return dataToSave;
          } catch (error) {
              console.error('Error guardando datos:', error);
              return null;
          }
      }

      // Load application data from localStorage
      loadData() {
          try {
              const saved = localStorage.getItem(this.storageKey);
              if (saved) {
                  const data = JSON.parse(saved);
                  
                  // Validate that required fields exist; regenerate if corrupted
                  if (!data.device_id || !data.device_code) {
                      console.warn('⚠️ Datos corruptos, regenerando...');
                      const newData = this.createInitialData();
                      this.saveData(newData);
                      return newData;
                  }
                  
                  console.log(`📂 Datos locales cargados - Device: ${data.device_id} - Código: ${data.device_code}`);
                  return data;
              } else {
                  // First time loading: create initial data structure
                  const initialData = this.createInitialData();
                  this.saveData(initialData);
                  return initialData;
              }
          } catch (error) {
              console.error('Error cargando datos:', error);
              const initialData = this.createInitialData();
              this.saveData(initialData);
              return initialData;
          }
      }

      // Create initial data structure for new devices
      createInitialData() {
          const device_id = this.generateUniqueDeviceId();
          const device_code = device_id.split('_')[1]; // Extract 6-digit code from device_id
          
          return {
              device_id: device_id,
              device_code: device_code,
              user_memory: {
                  user_preferences: {},
                  important_memories: [],
                  family_members: [],
                  daily_routine: {},
                  emotional_state: "calm"
              },
              conversation_history: [],
              created_at: new Date().toISOString()
          };
      }

      // Retrieve stored device ID
      getDeviceId() {
          const data = this.loadData();
          return data ? data.device_id : null;
      }

      // Retrieve stored device code
      getDeviceCode() {
          const data = this.loadData();
          return data ? data.device_code : null;
      }

      // Clear all stored data from localStorage
      clearData() {
          try {
              localStorage.removeItem(this.storageKey);
              console.log('🗑️ Datos locales eliminados');
          } catch (error) {
              console.error('Error eliminando datos:', error);
          }
      }

      // Regenerate device code in case of conflicts
      regenerateCode() {
          const data = this.loadData();
          const newCode = this.generateDeviceCode();
          const newDeviceId = `device_${newCode}`;
          
          data.device_id = newDeviceId;
          data.device_code = newCode;
          
          this.saveData(data);
          console.log(`🔄 Nuevo código generado: ${newCode}`);
          return data;
      }
  }

    // Initialize storage manager instance
    const storageManager = new LocalStorageManager();

    // ============================================
    // STATE VARIABLES - Application state management
    // ============================================
    let ws = null;                               // WebSocket connection
    let keepaliveInterval = null;                // Interval for keep-alive messages
    let audioStream = null;                      // Audio stream from microphone
    let audioCtx = null;                         // Web Audio API context
    let analyser = null;                         // Audio analyser node for RMS calculation
    let recognition = null;                      // SpeechRecognition instance
    let recognitionActive = false;               // Flag: is speech recognition currently running
    let recognitionStarting = false;             // Flag: is recognition in startup process
    let isSpeaking = false;                      // Flag: is assistant currently speaking (TTS)
    let lastSpokenMessage = '';                  // Track last spoken message to avoid repetition
    let selectedVoice = null;                    // Selected voice for text-to-speech
    let speakEnabled = true;                     // Global flag to enable/disable TTS
    let sendSilenceTimer = null;                 // Timeout for sending recognized text after silence
    let pendingFinal = '';                       // Buffer for final recognized transcripts
    let uiConversation = document.querySelector('#conversation'); // Conversation display element
    const btnId = 'showMemories';                // ID for memories button
    const memoryListId = 'memoryList';           // ID for memories list container

    // ============================================
    // VOICE PARAMETERS - Text-to-speech settings
    // ============================================
    let voiceParams = { volume: 0.95, rate: 0.90, pitch: 0.92 };

    // Track speech sessions to prevent race conditions
    let assistantSpeechSessionId = 0;
    // Flag: is user currently speaking
    let userIsTalking = false;

    // Track number of unread family messages
    let unreadMessagesCount = 0;

    // ============================================
    // DOM HELPERS - Utility functions for DOM manipulation
    // ============================================
    // Ensure conversation container exists in DOM
    function ensureConversation() {
      if (!uiConversation) {
        uiConversation = document.querySelector('.conversation') || document.createElement('div');
        uiConversation.id = 'conversation';
        uiConversation.className = 'conversation';
        document.body.appendChild(uiConversation);
      }
    }

    // Add message to conversation display
    function appendConversation(author, text) {
      ensureConversation();
      const div = document.createElement('div');
      // Classify message as assistant or user message based on author
      div.className = (author === 'Compa' || author === 'Compa' ? 'message assistant-message' : 'message user-message');
      div.innerHTML = `<strong>${author}:</strong> ${text}`;
      uiConversation.appendChild(div);
      // Auto-scroll to newest message
      uiConversation.scrollTop = uiConversation.scrollHeight;
    }

    // Get memory-related DOM elements
    function getMemoryElements() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      return { btn, list };
    }

    // ============================================
    // WEBSOCKET - Server communication
    // ============================================
    // Establish WebSocket connection and set up event handlers
    function connectWebSocket() {
    // Prevent duplicate connections
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    
    // Load device data from storage
    const localData = storageManager.loadData();
    
    // Create new WebSocket connection
    ws = new WebSocket(WS_URL);

    // Handle WebSocket connection opened
    ws.addEventListener('open', () => {
        console.log('✅ WebSocket abierto', WS_URL);
        
        // Send initial device data to server
        const initialData = {
            type: "initial_data",
            data: localData
        };
        ws.send(JSON.stringify(initialData));
        console.log('📤 Datos iniciales enviados al servidor');
    });

    // Handle incoming messages from server
    ws.addEventListener('message', (ev) => {
        try {
            const parsed = JSON.parse(ev.data);
            // Handle connection request from family member
            if (parsed && parsed.type === 'connection_request') {
            showConnectionRequestModal(parsed.request_id, parsed.user_info);
            return;
        }
        
          // Handle connection approval confirmation
          if (parsed && parsed.type === 'connection_approved') {
              appendConversation('Sistema', `✅ ${parsed.user_name} se ha conectado correctamente`);
              updateDeviceInfo(storageManager.getDeviceCode(), parsed.chat_id);
              return;
          }
            // Handle device information update from server
            if (parsed && parsed.type === 'device_info') {
                console.log('📱 Información del dispositivo recibida:', parsed);
                    const updatedData = {
                    ...localData,
                    device_id: parsed.device_id,
                    device_code: parsed.device_code
                };
                storageManager.saveData(updatedData);
                
                updateDeviceInfo(parsed.device_code, parsed.connected_chat);
                return;
            }
            
            // Handle memory saved notification from server
            if (parsed && parsed.type === 'memory_saved') {
                console.log('💾 Nuevo recuerdo guardado:', parsed);
                const message = '💾 He guardado un nuevo recuerdo importante en tu cofre.';
                appendConversation('Compa', message);
                if (speakEnabled && !isSpeaking) {
                    speakTextSoft(message);
                }
                return;
            }

            // Handle bulk data update from server
            if (parsed && parsed.type === 'data_update') {
                console.log('📥 Recibida actualización de datos del servidor');
                storageManager.saveData({
                    user_memory: parsed.user_memory,
                    conversation_history: parsed.conversation_history
                });
                return;
            }
          
          // Handle text message from assistant
          if (parsed && parsed.type === 'message' && parsed.text) {
            handleServerText(parsed.text);
            
            // If message includes family messages, read them aloud
            if (parsed.has_family_messages && Array.isArray(parsed.messages)) {
              console.log('📨 Mensajes familiares recibidos para lectura:', parsed.messages.length);
              
              setTimeout(() => {
                readFamilyMessagesSequence(parsed.messages);
              }, 1000);
            }
            
          } 
          // Handle family messages in legacy format
          else if (parsed && parsed.type === 'family_messages_to_read' && Array.isArray(parsed.messages)) {
            console.log('⚠️ Usando formato antiguo de mensajes familiares');
            handleServerText(`Tengo ${parsed.messages.length} mensajes para leerte.`);
            readFamilyMessagesSequence(parsed.messages);
          }
          
          // --- BLOQUE AÑADIDO ---
          // Handle silent notification for new messages
          else if (parsed && parsed.type === 'new_message_notification') {
            console.log('🔔 Notificación de nuevo mensaje recibida (silenciosa)');
            // Llama a la función que revisa y actualiza el contador
            checkForNewMessages(); 
            // NO llames a handleServerText()
            return; // Importante para no caer en el 'else'
          }
          // --- FIN BLOQUE AÑADIDO ---

          // Ignore WebSocket control messages (ping/pong)
          else if (parsed && (parsed.type === 'pong' || parsed.type === 'ping')) {
            if (VERBOSE) console.log('WS control:', parsed.type, parsed.ts || parsed);
          } 
          
          // --- BLOQUE MODIFICADO ---
          else {
            // Fallback: Si es un JSON pero no lo conocemos, lo ignoramos.
            // Si no es JSON (error de abajo), se mostrará.
            if (parsed && parsed.type) {
                console.warn('Tipo de mensaje WS no manejado:', parsed.type);
            } else {
                // Si es un JSON sin tipo o un texto plano, lo muestra
                handleServerText(ev.data);
            }
          }
          // --- FIN BLOQUE MODIFICADO ---

        } catch (e) {
          // If JSON parsing fails, treat as plain text
          handleServerText(ev.data);
        }
      });

      // Handle WebSocket connection closed
      ws.addEventListener('close', (ev) => {
        console.log('🔌 WebSocket cerrado', ev.code, ev.reason);
        if (keepaliveInterval) clearInterval(keepaliveInterval);
        // Attempt reconnection after delay
        setTimeout(connectWebSocket, 1500);
      });

      // Handle WebSocket errors
      ws.addEventListener('error', (err) => {
        console.error('⚠️ WebSocket error:', err);
      });
    }

    // Process and display text from server
    function handleServerText(text) {
      console.log('📝 Mensaje del servidor:', text);
      appendConversation('Compa', text);
      // Speak text only if user is not talking and TTS is enabled
      if (!userIsTalking && speakEnabled) {
        speakTextSoft(text);
      } else {
        console.log('Usuario hablando — no reproducir TTS ahora.');
      }
    }

    // Update device information display on UI
    function updateDeviceInfo(deviceCode, connectedChat) {
      const deviceInfoElement = document.getElementById('deviceInfo');
      if (!deviceInfoElement) return;
      
      // Update stored device code if changed
      const localData = storageManager.loadData();
      if (localData.device_code !== deviceCode) {
          localData.device_code = deviceCode;
          storageManager.saveData(localData);
      }
      
      // Show different UI based on connection status
      if (connectedChat) {
          deviceInfoElement.innerHTML = `
              <div class="device-connected">
                  <strong>📱 Tu Código Personal: <span style="font-size:24px; color:#4CAF50;">${deviceCode}</span></strong>
                  <br>
                  <small>✅ Conectado a Telegram</small>
                  <br>
                  <small>Este es tu código único permanente</small>
              </div>
          `;
      } else {
          deviceInfoElement.innerHTML = `
              <div class="device-waiting">
                  <strong>📱 Tu Código Personal: <span style="font-size:24px; color:#2196F3;">${deviceCode}</span></strong>
                  <br>
                  <small>⏳ Esperando conexión...</small>
                  <br>
                  <small>Dile a tu familiar que use en Telegram:</small>
                  <br>
                  <code style="font-size:16px; background:#f0f0f0; padding:5px;">/connect ${deviceCode}</code>
                  <br>
                  <small style="color:#666;">💡 Este código se mantendrá siempre igual</small>
              </div>
          `;
      }
  }

    // Send message to server via WebSocket
    function sendMessageToServer(text) {
      try {
        // Ignore keep-alive control messages
        const maybe = JSON.parse(text);
        if (maybe && maybe.type === 'keepalive') return;
      } catch (e) { /* no-json */ }

      // Ensure WebSocket is connected before sending
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
        setTimeout(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(text); }, 600);
        return;
      }
      try {
        ws.send(text);
      } catch (e) {
        console.error('Error enviando por WS:', e);
      }
    }


    // ============================================
    // TEXT-TO-SPEECH (TTS) - Voice output functionality
    // ============================================
    // Load available voices and cache the best one
    function loadVoices() {
      return new Promise((resolve) => {
        const synth = window.speechSynthesis;
        let voices = synth.getVoices();
        // If voices already loaded, use them immediately
        if (voices.length) {
          selectedVoice = chooseBestVoice(voices);
          resolve(voices);
        } else {
          // Wait for voices to be loaded
          synth.onvoiceschanged = () => {
            voices = synth.getVoices();
            selectedVoice = chooseBestVoice(voices);
            resolve(voices);
          };
          // Fallback timeout if voices never load
          setTimeout(() => {
            voices = synth.getVoices();
            selectedVoice = chooseBestVoice(voices);
            resolve(voices);
          }, 1200);
        }
      });
    }

    // Select the best Spanish voice from available options
    function chooseBestVoice(voices) {
      // Prioritize Spanish neural voices (most natural sounding)
      let candidates = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith('es-') && v.name && /neural|google|wave|wavenet|tts|premium/i.test(v.name));
      if (candidates.length) return candidates[0];
      // Fallback: any Spanish voice
      candidates = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith('es-'));
      if (candidates.length) return candidates[0];
      // Fallback: any high-quality voice
      candidates = voices.filter(v => v.name && /neural|google|wave|wavenet|tts|premium/i.test(v.name));
      if (candidates.length) return candidates[0];
      // Last resort: use first available voice
      return voices[0] || null;
    }

    // Speak text with natural pauses and segment management
    function speakTextSoft(text, options = {}) {
      // Exit early if conditions not met for speech
      if (!text || !('speechSynthesis' in window) || !speakEnabled) return;
      if (text === lastSpokenMessage) return; // Prevent duplicate speech
      lastSpokenMessage = text;

      // Create unique session ID to track this speech session
      assistantSpeechSessionId += 1;
      const mySession = assistantSpeechSessionId;

      // Prepare for speech
      isSpeaking = true;
      window.speechSynthesis.cancel(); // Cancel any ongoing speech
      stopRecognition();                // Stop listening during speech

      // Split text into manageable segments (max 120 chars each)
      const rawSegments = text.split(/(?<=[.!?])\s+/).filter(Boolean);
      const segments = [];
      rawSegments.forEach(seg => {
        if (seg.length <= 120) segments.push(seg.trim());
        else {
          // Further split long segments by commas
          const parts = seg.split(',').map(s => s.trim()).filter(Boolean);
          parts.forEach(p => {
            if (p.length <= 120) segments.push(p.trim());
            else {
              // Split very long parts into 110-char chunks
              for (let i = 0; i < p.length; i += 110) segments.push(p.slice(i, i + 110).trim());
            }
          });
        }
      });

      const synth = window.speechSynthesis;
      let i = 0;

      // Recursively speak each segment
      function speakNext() {
        // Check if this session was cancelled
        if (mySession !== assistantSpeechSessionId) {
          isSpeaking = false;
          lastSpokenMessage = '';
          return;
        }

        // When all segments spoken, clean up
        if (i >= segments.length) {
          isSpeaking = false;
          setTimeout(async () => {
            lastSpokenMessage = '';
            
            // Execute optional callback when speech complete
            try {
              if (options && typeof options.onComplete === 'function') {
                await options.onComplete();
              }
            } catch (err) {
              console.error('onComplete callback error:', err);
            }
            // Resume listening if user stopped talking
            if (!userIsTalking) startRecognition();
            else console.log('Usuario sigue hablando; reconocimiento se reanudará cuando pare.');
          }, 200);
          return;
        }

        // Create speech utterance for current segment
        const s = segments[i];
        const utter = new SpeechSynthesisUtterance(s);
        if (selectedVoice) utter.voice = selectedVoice;
        utter.volume = voiceParams.volume;
        // Vary speech rate slightly for more natural rhythm
        const baseRate = voiceParams.rate;
        const variation = (i % 2 === 0) ? 0.98 : 1.02;
        utter.rate = Math.max(0.5, Math.min(2.0, baseRate * variation));
        utter.pitch = voiceParams.pitch;

        // Move to next segment when current finishes
        utter.onend = () => {
          // Add random pause between segments for naturalness
          const pause = 360 + Math.floor(Math.random() * 120);
          setTimeout(() => {
            i += 1;
            speakNext();
          }, pause);
        };

        // Handle TTS errors gracefully
        utter.onerror = (e) => {
          console.warn('TTS error', e.error || e);
          i += 1;
          speakNext();
        };

        // Attempt to speak segment
        try {
          synth.speak(utter);
        } catch (e) {
          console.error('TTS fallo en speak:', e);
          i += 1;
          speakNext();
        }
      }

      speakNext();
    }

    // Stop assistant speech when user starts talking
    function interruptAssistantSpeechForUser() {
      if (!isSpeaking && assistantSpeechSessionId === 0) {
        userIsTalking = true;
        return;
      }
      // Increment session ID to invalidate ongoing speech
      assistantSpeechSessionId += 1;
      try { window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
      isSpeaking = false;
      userIsTalking = true;
      console.log('Asistente interrumpido por usuario — TTS cancelado.');
    }

    // Mark user as stopped talking and resume listening
    function userStoppedTalking() {
      userIsTalking = false;
      if (!isSpeaking) startRecognition();
      console.log('Usuario dejó de hablar — userIsTalking=false');
    }

    // ============================================
    // AUDIO DETECTION - RMS-based voice activity detection
    // ============================================
    // Initialize audio stream and RMS monitoring
    async function initAudioDetection(onLevel) {
      try {
        // Check browser support for microphone access
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('getUserMedia no soportado');
        }
        // Request microphone access
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Create Web Audio context for analysis
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioCtx.createMediaStreamSource(audioStream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 2048; // FFT size affects frequency resolution
        source.connect(analyser);
        const bufferLength = analyser.fftSize;
        const data = new Float32Array(bufferLength);

        // State tracking for voice detection
        let wasAbove = false;
        let lastAboveTs = 0;
        const MIN_SPEAK_MS = 250;         // Minimum duration to register as speech
        const MIN_SILENCE_MS = 2000;      // Duration of silence needed to end speech

        // Continuously measure audio levels
        function measure() {
          analyser.getFloatTimeDomainData(data);
          // Calculate RMS (Root Mean Square) for amplitude
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) sum += data[i] * data[i];
          const rms = Math.sqrt(sum / bufferLength);
          onLevel(rms); // Report level to caller

          const now = Date.now();
          // Detect when audio crosses above threshold
          if (rms > rmsThreshold) {
            if (!wasAbove) {
              lastAboveTs = now;
              wasAbove = true;
            } else {
              // Confirm speech after minimum duration
              if (!userIsTalking && (now - lastAboveTs) >= MIN_SPEAK_MS) {
                userIsTalking = true;
                interruptAssistantSpeechForUser();
                startRecognition();
              }
            }
          } else {
            // Handle audio dropping below threshold
            if (wasAbove) {
              const silenceStart = now;
              // Wait for sustained silence to confirm speech ended
              (function waitSilence() {
                analyser.getFloatTimeDomainData(data);
                let ssum = 0;
                for (let i = 0; i < bufferLength; i++) ssum += data[i] * data[i];
                const currentRms = Math.sqrt(ssum / bufferLength);
                if (currentRms <= rmsThreshold) {
                  // Double-check silence after minimum duration
                  setTimeout(() => {
                    analyser.getFloatTimeDomainData(data);
                    let ssum2 = 0;
                    for (let i = 0; i < bufferLength; i++) ssum2 += data[i] * data[i];
                    const currentRms2 = Math.sqrt(ssum2 / bufferLength);
                    if (currentRms2 <= rmsThreshold) {
                      // Confirm speech has ended
                      if (userIsTalking) {
                        userStoppedTalking();
                      }
                      wasAbove = false;
                    } else {
                      // False alarm: sound detected again, keep waiting
                      setTimeout(waitSilence, MIN_SILENCE_MS);
                    }
                  }, MIN_SILENCE_MS);
                } else {
                  // still sound detected, keep monitoring
                }
              })();
            }
          }

          // Schedule next measurement
          requestAnimationFrame(measure);
        }
        requestAnimationFrame(measure);
        console.log('✅ Detección de audio inicializada (RMS) con prioridad al usuario');
        return audioStream;
      } catch (err) {
        console.error('✖ Error inicializando micrófono:', err);
        throw err;
      }
    }

    // ============================================
    // SPEECH RECOGNITION - User voice-to-text conversion
    // ============================================
    // Initialize Web Speech API recognition engine
    function initRecognition() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        console.warn('SpeechRecognition no soportado');
        return null;
      }
      const rec = new SpeechRecognition();
      rec.continuous = true;           // Keep listening continuously
      rec.interimResults = true;       // Provide interim results while speaking
      rec.lang = 'es-ES';              // Set language to Spanish

      let finalBufferLocal = '';

      // Recognition started successfully
      rec.onstart = () => {
        recognitionActive = true;
        recognitionStarting = false;
      };

      // Process speech recognition results
      rec.onresult = (event) => {
        // Ignore recognition results while assistant is speaking
        if (isSpeaking) {
          if (VERBOSE) console.log('Ignorando resultado por TTS activo');
          return;
        }
        let interim = '';
        // Process all results since last event
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            // Final result: buffer for sending
            finalBufferLocal += transcript + ' ';
          } else {
            // Interim result: display in real-time
            interim += transcript;
          }
        }

        // Send buffered final transcripts after silence
        if (finalBufferLocal.trim()) {
          pendingFinal = finalBufferLocal.trim();
          finalBufferLocal = '';
          // Reset silence timer for new final result
          if (sendSilenceTimer) clearTimeout(sendSilenceTimer);
          sendSilenceTimer = setTimeout(() => {
            if (pendingFinal) {
              appendConversation('Tú', pendingFinal);
              try {
                const maybe = JSON.parse(pendingFinal);
                if (!(maybe && maybe.type === 'keepalive')) sendMessageToServer(pendingFinal);
              } catch (e) {
                sendMessageToServer(pendingFinal);
              }
              pendingFinal = '';
            }
          }, SILENCE_TO_SEND_MS);
        }
      };

      // Handle recognition errors
      rec.onerror = (e) => {
        console.warn('Error reconocimiento:', e.error);
        // Stop if permission denied
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          stopRecognition();
        }
      };

      // Recognition ended (either by user or error)
      rec.onend = () => {
        recognitionActive = false;
        recognitionStarting = false;
        // Restart recognition if still in focus
        setTimeout(() => {
          if (document.visibilityState === 'visible' && !isSpeaking && !userIsTalking) startRecognition();
        }, RESTART_RECOGNITION_DELAY_MS);
      };

      return rec;
    }
      

    // Start listening for user speech
    async function startRecognition() {
      // Prevent duplicate start attempts
      if (recognitionActive || recognitionStarting) return;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) return;
      // Initialize recognition engine if not already created
      if (!recognition) recognition = initRecognition();
      if (!recognition) return;
      recognitionStarting = true;
      try {
        recognition.start();
      } catch (e) {
        recognitionStarting = false;
        console.warn('recognition.start() error:', e);
      }
    }

    // Stop listening for user speech
    function stopRecognition() {
      if (recognition && recognitionActive) {
        try {
          recognition.stop();
        } catch (e) {
          console.warn('Error al detener recognition:', e);
        }
      }
    }


    // ============================================
    // MEMORIES - User memory management and display
    // ============================================
    // Fetch and display user memories from server
    async function showMyMemoriesUI() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      try {
        // Disable button and show loading state
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Cargando recuerdos...';
        }
        
        // Get device ID needed to fetch memories
        const deviceId = storageManager.getDeviceId();
        if (!deviceId) {
          appendConversation('Compa', 'No he podido identificar tu dispositivo. Intenta recargar la página.');
          if (btn) { btn.disabled = false; btn.textContent = 'Ver mis recuerdos'; }
          return;
        }
        
        // Fetch memories from server
        const resp = await fetch(`/memory/cofre?device_id=${encodeURIComponent(deviceId)}`);
        if (!resp.ok) throw new Error('Error fetching memories: ' + resp.status);
        const data = await resp.json();
        const memories = data.important_memories || [];
        
        // Clear previous list display
        if (list) list.innerHTML = '';
        if (!memories.length) {
          appendConversation('Compa', 'No tienes recuerdos guardados todavía.');
          if (btn) { btn.disabled = false; btn.textContent = 'Ver mis recuerdos'; }
          return;
        }
        
        // Display memories (max 100) in the list
        const maxShow = 100;
        const toShow = memories.slice(0, maxShow);
        toShow.forEach((m, idx) => {
          const el = document.createElement('div');
          el.className = 'memory-item';
          el.innerText = `${idx+1}. ${m.content}`;
          if (list) list.appendChild(el);
        });
        appendConversation('Compa', `He mostrado ${toShow.length} recuerdos en tu cofre.`);
      } catch (e) {
        console.error('showMyMemoriesUI error', e);
        appendConversation('Compa', 'No he podido recuperar tus recuerdos ahora.');
        speakTextSoft('Lo siento, no he podido recuperar tus recuerdos ahora.');
      } finally {
        // Re-enable button
        const btn2 = document.getElementById(btnId);
        if (btn2) { btn2.disabled = false; btn2.textContent = 'Ver mis recuerdos'; }
      }
    }

    // ============================================
    // FAMILY MESSAGES - Family communication feature
    // ============================================
    // Fetch and display family messages from server
    
    async function loadFamilyMessages() {
      const deviceId = storageManager.getDeviceId();
      console.log('🔍 loadFamilyMessages - Device ID:', deviceId);
      
      if (!deviceId) {
        console.error('❌ No device_id available for loadFamilyMessages');
        appendConversation('Compa', 'No se pudo identificar tu dispositivo. Intenta recargar la página.');
        return;
      }
      
      const btn = document.getElementById('showFamilyMessages');
      const list = document.getElementById('familyMessagesList');
      const countBadge = document.getElementById('unreadCount');

      try {
        // Show loading state with badge for unread count
        if (btn) {
          btn.disabled = true;
          btn.innerHTML = 'Cargando mensajes... <span id="unreadCount" class="badge"></span>';
        }
        console.log('📨 Enviando solicitud a /family/messages con device_id:', deviceId);
        const resp = await fetch(`/family/messages?device_id=${encodeURIComponent(deviceId)}`);
        
        if (!resp.ok) {
          if (resp.status === 503) {
            appendConversation('Compa', 'El sistema de mensajes familiares no está configurado todavía.');
            return;
          }
          throw new Error('Error fetching family messages: ' + resp.status);
        }

        const data = await resp.json();
        const messages = data.all_messages || [];
        // Calculate unread messages count
        unreadMessagesCount = data.total_unread || messages.filter(m => !m.read).length;

        // Update unread badge display
        if (countBadge) {
          countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
          countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
        }

        // Clear previous messages display
        if (list) list.innerHTML = '';

        if (!messages.length) {
          appendConversation('Compa', 'No tienes mensajes guardados de tus familiares.');
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Ver mensajes <span id="unreadCount" class="badge"></span>';
          }
          return;
        }

        // Sort messages by newest first
        messages.sort((a,b) => (new Date(b.timestamp || 0)) - (new Date(a.timestamp || 0)));
        // Display up to 50 most recent messages
        messages.slice(0, 50).forEach((msg) => {
          const el = document.createElement('div');
          // Add 'unread' class if message not yet read
          el.className = 'family-item' + (msg.read ? '' : ' unread');

          // Extract date and time from message
          const date = msg.date || (msg.timestamp ? new Date(msg.timestamp).toLocaleDateString('es-ES') : '—');
          const time = msg.time || (msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'}) : '');

          // Build HTML for message display with sender info, date, and action buttons
          el.innerHTML = `
            <div class="family-item-header">
              <span class="family-item-sender">👤 ${msg.sender_name || 'Desconocido'}</span>
              <span class="family-item-date">📅 ${date} 🕐 ${time}</span>
            </div>
            <div class="family-item-message">${msg.message || ''}</div>
            <div class="family-item-actions">
              <button class="btn-read" data-id="${msg.id}">Leer</button>
              ${!msg.read ? `<button class="btn-mark-read" data-id="${msg.id}">Marcar leído</button>` : ''}
              ${!msg.read ? '<span class="unread-dot" title="No leído"></span>' : ''}
            </div>
          `;

          // "Read" button: speak message aloud and mark as read
          const readBtn = el.querySelector('.btn-read');
          if (readBtn) {
            readBtn.addEventListener('click', (e) => {
              e.preventDefault();
              const messageId = msg.id;
              const readText = `Mensaje de ${msg.sender_name || 'un familiar'} del ${date} a las ${time}: ${msg.message}`;
              appendConversation('Compa', readText);

              // Speak message, then mark as read when done
              speakTextSoft(readText, {
                onComplete: async () => {
                  try {
                    await markMessageAsRead(messageId);
                    el.classList.remove('unread');
                    const markBtn = el.querySelector('.btn-mark-read');
                    if (markBtn) markBtn.remove();
                    const dot = el.querySelector('.unread-dot');
                    if (dot) dot.remove();
                  } catch (err) {
                    console.error('No se pudo marcar mensaje como leído tras TTS:', err);
                  }
                }
              });
            });
          }

          // "Mark as read" button: mark message as read without speaking
          const markBtn = el.querySelector('.btn-mark-read');
          if (markBtn) {
            markBtn.addEventListener('click', async (ev) => {
              ev.preventDefault();
              const id = parseInt(markBtn.getAttribute('data-id'));
              try {
                await markMessageAsRead(id);
                el.classList.remove('unread');
                markBtn.remove();
                const dot = el.querySelector('.unread-dot');
                if (dot) dot.remove();
                appendConversation('Compa', 'He marcado el mensaje como leído.');
              } catch (err) {
                console.error('Error marcando manualmente como leído', err);
                appendConversation('Compa', 'No he podido marcar el mensaje como leído.');
              }
            });
          }

          if (list) list.appendChild(el);
        });

        // Notify user about unread messages
        const unreadOnly = messages.filter(m => !m.read);
        if (unreadOnly.length > 0 && speakEnabled && !isSpeaking) {
          const summary = unreadOnly.length === 1 
            ? `Tienes un mensaje nuevo de ${unreadOnly[0].sender_name}` 
            : `Tienes ${unreadOnly.length} mensajes nuevos de tus familiares`;
          appendConversation('Compa', summary);
          speakTextSoft(summary);
        }

      } catch (e) {
        console.error('loadFamilyMessages error', e);
        appendConversation('Compa', 'No he podido cargar los mensajes ahora.');
      } finally {
        // Re-enable button
        const btn2 = document.getElementById('showFamilyMessages');
        if (btn2) {
          btn2.disabled = false;
          btn2.innerHTML = `Ver mensajes <span id="unreadCount" class="badge">${unreadMessagesCount > 0 ? unreadMessagesCount : ''}</span>`;
        }
      }
    }

    // Mark a specific message as read on the server
    async function markMessageAsRead(messageId) {
      try {
        const deviceId = storageManager.getDeviceId();
        if (!deviceId) {
          console.error('❌ No device_id available for markAsRead');
          return false;
        }
        
        console.log(`🔄 Enviando petición para marcar mensaje ${messageId} como leído`);
        
        const resp = await fetch(`/family/messages/${messageId}/read?device_id=${encodeURIComponent(deviceId)}`, { 
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        
        if (!resp.ok) {
          const errorText = await resp.text();
          throw new Error(`HTTP ${resp.status}: ${errorText}`);
        }
        
        const result = await resp.json();
        console.log(`✅ Mensaje ${messageId} marcado como leído en el servidor:`, result);
        return true;
        
      } catch (e) {
        console.error(`❌ Error marcando mensaje ${messageId} como leído:`, e);
        return false;
      }
    }

    // Read multiple family messages aloud in sequence
    async function readFamilyMessagesSequence(messages) {
      if (!messages || messages.length === 0) {
        console.log('❌ No hay mensajes para leer');
        return;
      }

      console.log(`🔊 Iniciando lectura de ${messages.length} mensajes`);

      // Process each message in order
      for (const [index, msg] of messages.entries()) {
        try {
          const messageText = `De ${msg.sender_name || 'un familiar'}: ${msg.message}`;
          
          appendConversation('Compa', `📨 ${msg.sender_name}: ${msg.message}`);
          
          // Speak message if TTS enabled
          if (speakEnabled) {
            await new Promise(resolve => {
              speakTextSoft(messageText, { onComplete: resolve });
            });
          }

          console.log(`📝 Marcando mensaje ${msg.id} como leído`);
          try {
            const deviceId = storageManager.getDeviceId();
            const response = await fetch(`/family/messages/${msg.id}/read?device_id=${encodeURIComponent(deviceId)}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              }
            });
            
            if (response.ok) {
              console.log(`✅ Mensaje ${msg.id} marcado como leído`);
              updateMessageInUI(msg.id);
            } else {
              console.log(`❌ Falló el marcado del mensaje ${msg.id}`);
            }
          } catch (err) {
            console.error(`Error marcando mensaje ${msg.id}:`, err);
          }

          // Add pause between messages for readability
          if (index < messages.length - 1) {
            await new Promise(r => setTimeout(r, 800));
          }
          
        } catch (err) {
          console.error(`Error procesando mensaje ${msg.id}:`, err);
        }
      }

      // Conclude message reading session
      const finalText = "Esos son todos los mensajes. ¿En qué más puedo ayudarte?";
      appendConversation('Compa', finalText);
      if (speakEnabled && !isSpeaking) {
        speakTextSoft(finalText);
      }
    }

    // Update message status in UI after it's marked as read
    function updateMessageInUI(messageId) {
      const messageElements = document.querySelectorAll('.family-item');
      messageElements.forEach(element => {
        const btn = element.querySelector('.btn-mark-read');
        if (btn && parseInt(btn.getAttribute('data-id')) === messageId) {
          // Remove unread styling and buttons
          element.classList.remove('unread');
          
          if (btn) btn.remove();
          
          const dot = element.querySelector('.unread-dot');
          if (dot) dot.remove();
          
          console.log(`✅ UI actualizada para mensaje ${messageId}`);
        }
      });

      // Update unread count badge
      unreadMessagesCount = Math.max(0, unreadMessagesCount - 1);
      const countBadge = document.getElementById('unreadCount');
      if (countBadge) {
        countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
        countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
      }
    }

    // Periodically check for new messages from family
    async function checkForNewMessages() {
        try {
          const deviceId = storageManager.getDeviceId();
          if (!deviceId) {
            console.log('⏭️ checkForNewMessages: No device_id, saltando...');
            return;
          }
          
          const resp = await fetch(`/family/messages?device_id=${encodeURIComponent(deviceId)}`);
            if (resp.ok) {
          const data = await resp.json();
          const newCount = data.total_unread || 0;
          
          // Notify user if new messages arrived
          if (newCount > unreadMessagesCount) {
            const countBadge = document.getElementById('unreadCount');
            if (countBadge) {
              countBadge.textContent = newCount;
              countBadge.style.display = 'inline-block';
            }
            unreadMessagesCount = newCount;
            
            appendConversation('Compa', '¡Tienes mensajes nuevos de tus familiares!');
            if (speakEnabled && !isSpeaking) {
              speakTextSoft('Tienes mensajes nuevos de tus familiares. ¿Quieres que te los lea?');
            }
          }
          // --- AÑADIDO ---
          // Asegura que el contador se actualice incluso si los mensajes disminuyen (se leen en otro lado)
          else if (newCount < unreadMessagesCount) {
             const countBadge = document.getElementById('unreadCount');
             if (countBadge) {
                countBadge.textContent = newCount > 0 ? newCount : '';
                countBadge.style.display = newCount > 0 ? 'inline-block' : 'none';
             }
             unreadMessagesCount = newCount;
          }
          // --- FIN AÑADIDO ---

        }
      } catch (e) {
        console.error('Error checking for new messages:', e);
      }
    }

    // ============================================
    // CONNECTION MODAL - Family member connection requests
    // ============================================
    // Global variable to track pending connection request
    let currentRequestId = null;

    // Display modal requesting user approval for family member connection
    function showConnectionRequestModal(requestId, userInfo) {
        currentRequestId = requestId;
        
        const modal = document.getElementById('connectionRequestModal');
        const info = document.getElementById('connectionRequestInfo');
        
        // Extract user information from request
        const userName = userInfo.user_full_name || userInfo.user_name;
        const username = userInfo.username || 'sin usuario';
        
        // Populate modal with connection request details
        info.innerHTML = `
            <p><strong>👤 Usuario:</strong> ${userName}</p>
            <p><strong>📱 Telegram:</strong> @${username}</p>
            <p><strong>🆔 Chat ID:</strong> ${userInfo.chat_id}</p>
            <hr style="margin: 15px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #666;">¿Deseas permitir que esta persona envíe mensajes a este dispositivo?</p>
        `;
        
        // Show modal to user
        modal.style.display = 'flex';
        
        // Notify user via voice
        if (speakEnabled && !isSpeaking) {
            speakTextSoft(`${userName} quiere conectarse. ¿Lo permites?`);
        }
        
        console.log(`🔔 Solicitud de conexión de ${userName} (@${username})`);
    }

    // Hide connection request modal
    function hideConnectionRequestModal() {
        const modal = document.getElementById('connectionRequestModal');
        modal.style.display = 'none';
        currentRequestId = null;
    }

    // Send connection approval or rejection response to server
    function sendConnectionResponse(approved) {
        if (!currentRequestId) {
            console.warn('⚠️ No hay solicitud pendiente');
            return;
        }
        
        // Build response message
        const response = {
            type: "connection_response",
            request_id: currentRequestId,
            approved: approved
        };
        
        sendMessageToServer(JSON.stringify(response));
        
        // Notify user of response
        const message = approved 
            ? "✅ Conexión aprobada correctamente" 
            : "❌ Conexión rechazada";
        
        appendConversation('Sistema', message);
        if (speakEnabled && !isSpeaking) {
            speakTextSoft(message);
        }
        
        console.log(`${approved ? '✅' : '❌'} Respuesta enviada: ${approved ? 'APROBADA' : 'RECHAZADA'}`);
        hideConnectionRequestModal();
    }


    // ============================================
    // AUTHENTICATION MIDDLEWARE
    // ============================================

    class AuthManager {
        constructor() {
            this.sessionToken = null;
            this.phoneNumber = null;
        }
        getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
        }
        // Cargar sesión desde localStorage
        loadSession() {
            this.sessionToken = this.getCookie('session_token');
            this.phoneNumber = this.getCookie('phone_number');
            return this.sessionToken !== null;
          }
        
        // Validar sesión con el servidor
        async validateSession() {
            if (!this.sessionToken) {
                return false;
            }
            
            try {
                const response = await fetch('/auth/validate-session', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        session_token: this.sessionToken
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    console.log('✅ Sesión válida:', data);
                    return true;
                } else {
                    // Sesión inválida o expirada
                    this.clearSession();
                    return false;
                }
            } catch (error) {
                console.error('❌ Error validando sesión:', error);
                return false;
            }
        }
        
        // Limpiar sesión y redirigir a login
        clearSession() {
            localStorage.removeItem('session_token'); // Limpia localStorage por si acaso
            localStorage.removeItem('phone_number');
            
            // Lo más importante: Borra las cookies
            document.cookie = 'session_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            document.cookie = 'phone_number=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';

            this.sessionToken = null;
            this.phoneNumber = null;
        }
        
        // Cerrar sesión
        async logout() {
            if (!this.sessionToken) return;
            
            try {
                await fetch('/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        session_token: this.sessionToken
                    })
                });
            } catch (error) {
                console.error('Error cerrando sesión:', error);
            }
            
            this.clearSession();
            window.location.href = '/login';
        }
        
        // Obtener información de sesión
        getSessionInfo() {
            return {
                token: this.sessionToken,
                phone: this.phoneNumber
            };
        }
    }

    // Instancia global
    const authManager = new AuthManager();

    // Verificar autenticación antes de iniciar la app
    async function checkAuthBeforeBoot() {
        // Si estamos en la página de login, no validar
        if (window.location.pathname === '/login' || window.location.pathname === '/login.html') {
            return true;
        }
        
        // Cargar sesión de localStorage
        const hasSession = authManager.loadSession();
        
        if (!hasSession) {
            console.log('⚠️ No hay sesión activa, redirigiendo a login');
            window.location.href = '/login';
            return false;
        }
        
        // Validar sesión con el servidor
        const isValid = await authManager.validateSession();
        
        if (!isValid) {
            console.log('⚠️ Sesión expirada, redirigiendo a login');
            window.location.href = '/login';
            return false;
        }
        
        console.log('✅ Sesión válida, iniciando app');
        return true;
    }


    // ============================================
    // APPLICATION BOOT - Initialization and startup
    // ============================================
    // Main application initialization function
    async function boot() {
      try {
        const deviceId = storageManager.getDeviceId();
        console.log('🚀 Initializing application - Device ID:', deviceId);

        if (!deviceId) {
          console.error('❌ CRITICAL: Could not obtain device_id');
        }

        // Establish WebSocket connection to the server
        connectWebSocket();
        // Load available voices for text-to-speech
        await loadVoices();
        // Ensure the conversation element exists in the UI
        ensureConversation();

        // ---- Memories Button Setup ----
        const btn = document.getElementById(btnId);
        if (btn) {
          btn.addEventListener('click', (e) => {
            e.preventDefault();
            showMyMemoriesUI();
          });
        } else {
          console.warn(`#${btnId} not found in DOM; add the button in index.html`);
        }

        // ---- Family Messages Button Setup ----
        const familyBtn = document.getElementById('showFamilyMessages');
        if (familyBtn) {
          familyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            loadFamilyMessages();
          });
        } else {
          console.warn('#showFamilyMessages not found in DOM');
        }

        // ---- Connection Modal Buttons Setup ----
        const approveBtn = document.getElementById('approveConnectionBtn');
        const rejectBtn = document.getElementById('rejectConnectionBtn');

        if (approveBtn) {
          approveBtn.addEventListener('click', () => {
            console.log('🟢 User approved the connection');
            sendConnectionResponse(true);
          });
        } else {
          console.warn('#approveConnectionBtn not found in DOM');
        }

        if (rejectBtn) {
          rejectBtn.addEventListener('click', () => {
            console.log('🔴 User rejected the connection');
            sendConnectionResponse(false);
          });
        } else {
          console.warn('#rejectConnectionBtn not found in DOM');
        }

        // Close modal when clicking outside (defaults to reject)
        const modal = document.getElementById('connectionRequestModal');
        if (modal) {
          modal.addEventListener('click', (e) => {
            if (e.target === modal) {
              console.log('⚠️ Modal closed without responding - assuming reject');
              sendConnectionResponse(false);
            }
          });
        }

        // ---- Periodic Message Check ----
        // Check for new family messages every 2 minutes (120000ms)
        setInterval(checkForNewMessages, 120000);
        // --- AÑADIDO ---
        // Comprueba al arrancar por si hay mensajes pendientes
        setTimeout(checkForNewMessages, 2000); // Espera 2 seg a que todo cargue

        // ---- Audio Detection Initialization ----
        // Start monitoring the microphone for user speech
        await initAudioDetection((rms) => {
          if (VERBOSE) console.log(`🎚️ RMS: ${rms.toFixed(4)} / Threshold: ${rmsThreshold}`);
        });

        // ============================================
        // GLOBAL API - Expose functions for debugging and external control
        // ============================================
        window.__Acompania = {
          // Audio detection control
          setThreshold: (v) => { rmsThreshold = v; console.log('RMS threshold changed to', v); },
          getThreshold: () => rmsThreshold,

          // Storage management
          storageManager: storageManager,
          saveData: (data) => storageManager.saveData(data),
          loadData: () => storageManager.loadData(),
          clearData: () => storageManager.clearData(),

          // Voice synthesis control
          setVoiceParams: (p) => { Object.assign(voiceParams, p); console.log('voiceParams updated', voiceParams); },
          getVoiceParams: () => ({ ...voiceParams }),

          // Speech recognition control
          startRecognition: () => startRecognition(),
          stopRecognition: () => stopRecognition(),

          // WebSocket control
          reconnectWS: () => connectWebSocket(),

          // Message sending
          sendMessage: (t) => { appendConversation('You', t); sendMessageToServer(t); },

          // TTS control
          enableSpeech: (b) => { speakEnabled = !!b; console.log('TTS enabled =', speakEnabled); },
          getVoices: () => window.speechSynthesis.getVoices(),

          // Feature functions
          showMemoriesUI: () => showMyMemoriesUI(),
          loadFamilyMessages: () => loadFamilyMessages(),
          markMessageAsRead: (id) => markMessageAsRead(id),

          // Connection modal debugging
          showConnectionModal: (userInfo) => showConnectionRequestModal('test_123', userInfo),
          approveConnection: () => sendConnectionResponse(true),
          rejectConnection: () => sendConnectionResponse(false),

          // Device information
          getDeviceInfo: () => ({
            device_id: storageManager.getDeviceId(),
            device_code: storageManager.getDeviceCode()
          })
        };

        // Startup information
        console.log('🚀 Compa initialized successfully (user priority)');
        console.log('📱 Device ID:', storageManager.getDeviceId());
        console.log('🔢 Device Code:', storageManager.getDeviceCode());
        console.log('💡 Use window.__Acompania to access debug functions');

      } catch (err) {
        console.error('App startup error:', err);

        // Show on-screen error notification
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
          position: fixed;
          top: 20px;
          left: 50%;
          transform: translateX(-50%);
          background: #f44336;
          color: white;
          padding: 15px 30px;
          border-radius: 10px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          z-index: 9999;
          font-size: 16px;
        `;
        errorDiv.innerHTML = `
          <strong>⚠️ Initialization Error</strong><br>
          <small>${err.message || 'Unknown error'}</small><br>
          <small style="opacity:0.8;">Try reloading the page</small>
        `;
        document.body.appendChild(errorDiv);

        // Auto-hide the error notification after 10 seconds
        setTimeout(() => {
          errorDiv.style.opacity = '0';
          errorDiv.style.transition = 'opacity 1s';
          setTimeout(() => errorDiv.remove(), 1000);
        }, 10000);
      }
    }
    // ============================================
    // STARTUP - Execute boot function when the DOM is ready
    // ============================================
    if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        const authenticated = await checkAuthBeforeBoot();
        if (authenticated) boot();
    });
} else {
    (async () => {
        const authenticated = await checkAuthBeforeBoot();
        if (authenticated) boot();
    })();
}

// Exponer en API global
window.__Acompania = window.__Acompania || {};
window.__Acompania.authManager = authManager;
  })(); 
}