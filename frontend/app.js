if (window.__ACOMPANIA_APPJS_LOADED) {
  console.warn('app.js ya inicializado — evitando ejecución duplicada');
} else {
  window.__ACOMPANIA_APPJS_LOADED = true;

  (function () {
    // CONFIG
    const WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    let rmsThreshold = 0.17; 
    const SILENCE_TO_SEND_MS = 1000;
    const KEEPALIVE_MS = 60000;
    const RESTART_RECOGNITION_DELAY_MS = 300;
    const VERBOSE = false;

    // Local Storage Manager
    class LocalStorageManager {
      constructor() {
          this.storageKey = 'alzheimer_app_data';
      }

      generateDeviceCode() {
          // Genera código de 6 dígitos único
          let code;
          do {
              code = Math.floor(100000 + Math.random() * 900000).toString();
          } while (code.length !== 6);
          return code;
      }

      generateUniqueDeviceId() {
          // Formato: device_XXXXXX (6 dígitos únicos)
          const code = this.generateDeviceCode();
          return `device_${code}`;
      }

      saveData(data) {
          try {
              const currentData = this.loadData() || {};
              
              // IMPORTANTE: Preservar device_id y device_code originales
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

      loadData() {
          try {
              const saved = localStorage.getItem(this.storageKey);
              if (saved) {
                  const data = JSON.parse(saved);
                  
                  // Validar que tenga los campos necesarios
                  if (!data.device_id || !data.device_code) {
                      console.warn('⚠️ Datos corruptos, regenerando...');
                      const newData = this.createInitialData();
                      this.saveData(newData);
                      return newData;
                  }
                  
                  console.log(`📂 Datos locales cargados - Device: ${data.device_id} - Código: ${data.device_code}`);
                  return data;
              } else {
                  // Primera vez: crear datos iniciales
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

      createInitialData() {
          const device_id = this.generateUniqueDeviceId();
          const device_code = device_id.split('_')[1]; // Extraer los 6 dígitos del device_id
          
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

      getDeviceId() {
          const data = this.loadData();
          return data ? data.device_id : null;
      }

      getDeviceCode() {
          const data = this.loadData();
          return data ? data.device_code : null;
      }

      clearData() {
          try {
              localStorage.removeItem(this.storageKey);
              console.log('🗑️ Datos locales eliminados');
          } catch (error) {
              console.error('Error eliminando datos:', error);
          }
      }

      // Método para regenerar código (solo en caso de conflicto)
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

    const storageManager = new LocalStorageManager();

    // state
    let ws = null;
    let keepaliveInterval = null;
    let audioStream = null;
    let audioCtx = null;
    let analyser = null;
    let recognition = null;
    let recognitionActive = false;
    let recognitionStarting = false;
    let isSpeaking = false;            
    let lastSpokenMessage = '';
    let selectedVoice = null;
    let speakEnabled = true;
    let sendSilenceTimer = null;
    let pendingFinal = '';
    let uiConversation = document.querySelector('#conversation');
    const btnId = 'showMemories';
    const memoryListId = 'memoryList';

    // VOICE params
    let voiceParams = { volume: 0.95, rate: 0.90, pitch: 0.92 };

    let assistantSpeechSessionId = 0;
    let userIsTalking = false;

    let unreadMessagesCount = 0;

    // DOM helper
    function ensureConversation() {
      if (!uiConversation) {
        uiConversation = document.querySelector('.conversation') || document.createElement('div');
        uiConversation.id = 'conversation';
        uiConversation.className = 'conversation';
        document.body.appendChild(uiConversation);
      }
    }

    function appendConversation(author, text) {
      ensureConversation();
      const div = document.createElement('div');
      div.className = (author === 'Compa' || author === 'Compa' ? 'message assistant-message' : 'message user-message');
      div.innerHTML = `<strong>${author}:</strong> ${text}`;
      uiConversation.appendChild(div);
      uiConversation.scrollTop = uiConversation.scrollHeight;
    }

    function getMemoryElements() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      return { btn, list };
    }

    // WebSocket

    function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    
    const localData = storageManager.loadData();
    
    ws = new WebSocket(WS_URL);

    ws.addEventListener('open', () => {
        console.log('✅ WebSocket abierto', WS_URL);
        
        const initialData = {
            type: "initial_data",
            data: localData
        };
        ws.send(JSON.stringify(initialData));
        console.log('📤 Datos iniciales enviados al servidor');
    });

    ws.addEventListener('message', (ev) => {
        try {
            const parsed = JSON.parse(ev.data);
            if (parsed && parsed.type === 'connection_request') {
            showConnectionRequestModal(parsed.request_id, parsed.user_info);
            return;
        }
        
          // ⬇️ NUEVO: Manejar aprobación confirmada
          if (parsed && parsed.type === 'connection_approved') {
              appendConversation('Sistema', `✅ ${parsed.user_name} se ha conectado correctamente`);
              updateDeviceInfo(storageManager.getDeviceCode(), parsed.chat_id);
              return;
          }
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
            
            if (parsed && parsed.type === 'data_update') {
                console.log('📥 Recibida actualización de datos del servidor');
                storageManager.saveData({
                    user_memory: parsed.user_memory,
                    conversation_history: parsed.conversation_history
                });
                return;
            }
          
          
          if (parsed && parsed.type === 'message' && parsed.text) {
            handleServerText(parsed.text);
            
            if (parsed.has_family_messages && Array.isArray(parsed.messages)) {
              console.log('📨 Mensajes familiares recibidos para lectura:', parsed.messages.length);
              
              setTimeout(() => {
                readFamilyMessagesSequence(parsed.messages);
              }, 1000);
            }
            
          } 
          else if (parsed && parsed.type === 'family_messages_to_read' && Array.isArray(parsed.messages)) {
            console.log('⚠️ Usando formato antiguo de mensajes familiares');
            handleServerText(`Tengo ${parsed.messages.length} mensajes para leerte.`);
            readFamilyMessagesSequence(parsed.messages);
          }
          else if (parsed && (parsed.type === 'pong' || parsed.type === 'ping')) {
            if (VERBOSE) console.log('WS control:', parsed.type, parsed.ts || parsed);
          } else {
            handleServerText(ev.data);
          }
        } catch (e) {
          handleServerText(ev.data);
        }
      });

      ws.addEventListener('close', (ev) => {
        console.log('🔌 WebSocket cerrado', ev.code, ev.reason);
        if (keepaliveInterval) clearInterval(keepaliveInterval);
        setTimeout(connectWebSocket, 1500);
      });

      ws.addEventListener('error', (err) => {
        console.error('⚠️ WebSocket error:', err);
      });
    }

    function handleServerText(text) {
      console.log('📝 Mensaje del servidor:', text);
      appendConversation('Compa', text);
      if (!userIsTalking && speakEnabled) {
        speakTextSoft(text);
      } else {
        console.log('Usuario hablando — no reproducir TTS ahora.');
      }
    }

    function updateDeviceInfo(deviceCode, connectedChat) {
      const deviceInfoElement = document.getElementById('deviceInfo');
      if (!deviceInfoElement) return;
      
      // Guardar el código en localStorage por si acaso
      const localData = storageManager.loadData();
      if (localData.device_code !== deviceCode) {
          localData.device_code = deviceCode;
          storageManager.saveData(localData);
      }
      
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

    function sendMessageToServer(text) {
      try {
        const maybe = JSON.parse(text);
        if (maybe && maybe.type === 'keepalive') return;
      } catch (e) { /* no-json */ }

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


    // TTS more "natural" with session id and onComplete callback

    function loadVoices() {
      return new Promise((resolve) => {
        const synth = window.speechSynthesis;
        let voices = synth.getVoices();
        if (voices.length) {
          selectedVoice = chooseBestVoice(voices);
          resolve(voices);
        } else {
          synth.onvoiceschanged = () => {
            voices = synth.getVoices();
            selectedVoice = chooseBestVoice(voices);
            resolve(voices);
          };
          setTimeout(() => {
            voices = synth.getVoices();
            selectedVoice = chooseBestVoice(voices);
            resolve(voices);
          }, 1200);
        }
      });
    }

    function chooseBestVoice(voices) {
      let candidates = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith('es-') && v.name && /neural|google|wave|wavenet|tts|premium/i.test(v.name));
      if (candidates.length) return candidates[0];
      candidates = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith('es-'));
      if (candidates.length) return candidates[0];
      candidates = voices.filter(v => v.name && /neural|google|wave|wavenet|tts|premium/i.test(v.name));
      if (candidates.length) return candidates[0];
      return voices[0] || null;
    }

    function speakTextSoft(text, options = {}) {
      if (!text || !('speechSynthesis' in window) || !speakEnabled) return;
      if (text === lastSpokenMessage) return;
      lastSpokenMessage = text;

      assistantSpeechSessionId += 1;
      const mySession = assistantSpeechSessionId;

      isSpeaking = true;
      window.speechSynthesis.cancel();
      stopRecognition();

      const rawSegments = text.split(/(?<=[.!?])\s+/).filter(Boolean);
      const segments = [];
      rawSegments.forEach(seg => {
        if (seg.length <= 120) segments.push(seg.trim());
        else {
          const parts = seg.split(',').map(s => s.trim()).filter(Boolean);
          parts.forEach(p => {
            if (p.length <= 120) segments.push(p.trim());
            else {
              for (let i = 0; i < p.length; i += 110) segments.push(p.slice(i, i + 110).trim());
            }
          });
        }
      });

      const synth = window.speechSynthesis;
      let i = 0;

      function speakNext() {
        if (mySession !== assistantSpeechSessionId) {
          isSpeaking = false;
          lastSpokenMessage = '';
          return;
        }

        if (i >= segments.length) {
          isSpeaking = false;
          setTimeout(async () => {
            lastSpokenMessage = '';
            
            try {
              if (options && typeof options.onComplete === 'function') {
                await options.onComplete();
              }
            } catch (err) {
              console.error('onComplete callback error:', err);
            }
            if (!userIsTalking) startRecognition();
            else console.log('Usuario sigue hablando; reconocimiento se reanudará cuando pare.');
          }, 200);
          return;
        }

        const s = segments[i];
        const utter = new SpeechSynthesisUtterance(s);
        if (selectedVoice) utter.voice = selectedVoice;
        utter.volume = voiceParams.volume;
        const baseRate = voiceParams.rate;
        const variation = (i % 2 === 0) ? 0.98 : 1.02;
        utter.rate = Math.max(0.5, Math.min(2.0, baseRate * variation));
        utter.pitch = voiceParams.pitch;

        utter.onend = () => {
          const pause = 360 + Math.floor(Math.random() * 120);
          setTimeout(() => {
            i += 1;
            speakNext();
          }, pause);
        };

        utter.onerror = (e) => {
          console.warn('TTS error', e.error || e);
          i += 1;
          speakNext();
        };

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

    function interruptAssistantSpeechForUser() {
      if (!isSpeaking && assistantSpeechSessionId === 0) {
        userIsTalking = true;
        return;
      }
      assistantSpeechSessionId += 1;
      try { window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
      isSpeaking = false;
      userIsTalking = true;
      console.log('Asistente interrumpido por usuario — TTS cancelado.');
    }

    function userStoppedTalking() {
      userIsTalking = false;
      if (!isSpeaking) startRecognition();
      console.log('Usuario dejó de hablar — userIsTalking=false');
    }

    // Audio detection (RMS)
    async function initAudioDetection(onLevel) {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('getUserMedia no soportado');
        }
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioCtx.createMediaStreamSource(audioStream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 2048;
        source.connect(analyser);
        const bufferLength = analyser.fftSize;
        const data = new Float32Array(bufferLength);

        let wasAbove = false;
        let lastAboveTs = 0;
        const MIN_SPEAK_MS = 250;
        const MIN_SILENCE_MS = 2000;

        function measure() {
          analyser.getFloatTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) sum += data[i] * data[i];
          const rms = Math.sqrt(sum / bufferLength);
          onLevel(rms);

          const now = Date.now();
          if (rms > rmsThreshold) {
            if (!wasAbove) {
              lastAboveTs = now;
              wasAbove = true;
            } else {
              if (!userIsTalking && (now - lastAboveTs) >= MIN_SPEAK_MS) {
                userIsTalking = true;
                interruptAssistantSpeechForUser();
                startRecognition();
              }
            }
          } else {
            if (wasAbove) {
              const silenceStart = now;
              (function waitSilence() {
                analyser.getFloatTimeDomainData(data);
                let ssum = 0;
                for (let i = 0; i < bufferLength; i++) ssum += data[i] * data[i];
                const currentRms = Math.sqrt(ssum / bufferLength);
                if (currentRms <= rmsThreshold) {
                  setTimeout(() => {
                    analyser.getFloatTimeDomainData(data);
                    let ssum2 = 0;
                    for (let i = 0; i < bufferLength; i++) ssum2 += data[i] * data[i];
                    const currentRms2 = Math.sqrt(ssum2 / bufferLength);
                    if (currentRms2 <= rmsThreshold) {
                      if (userIsTalking) {
                        userStoppedTalking();
                      }
                      wasAbove = false;
                    } else {
                      setTimeout(waitSilence, MIN_SILENCE_MS);
                    }
                  }, MIN_SILENCE_MS);
                } else {
                  // still sound
                }
              })();
            }
          }

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

    // SpeechRecognition

    function initRecognition() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        console.warn('SpeechRecognition no soportado');
        return null;
      }
      const rec = new SpeechRecognition();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = 'es-ES';

      let finalBufferLocal = '';

      rec.onstart = () => {
        recognitionActive = true;
        recognitionStarting = false;
      };

      rec.onresult = (event) => {
        if (isSpeaking) {
          if (VERBOSE) console.log('Ignorando resultado por TTS activo');
          return;
        }
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalBufferLocal += transcript + ' ';
          } else {
            interim += transcript;
          }
        }

        if (finalBufferLocal.trim()) {
          pendingFinal = finalBufferLocal.trim();
          finalBufferLocal = '';
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

      rec.onerror = (e) => {
        console.warn('Error reconocimiento:', e.error);
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          stopRecognition();
        }
      };

      rec.onend = () => {
        recognitionActive = false;
        recognitionStarting = false;
        setTimeout(() => {
          if (document.visibilityState === 'visible' && !isSpeaking && !userIsTalking) startRecognition();
        }, RESTART_RECOGNITION_DELAY_MS);
      };

      return rec;
    }

    async function startRecognition() {
      if (recognitionActive || recognitionStarting) return;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) return;
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

    function stopRecognition() {
      if (recognition && recognitionActive) {
        try {
          recognition.stop();
        } catch (e) {
          console.warn('Error al detener recognition:', e);
        }
      }
    }


    async function showMyMemoriesUI() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      try {
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Cargando recuerdos...';
        }
        
        const deviceId = storageManager.getDeviceId();
        if (!deviceId) {
          appendConversation('Compa', 'No he podido identificar tu dispositivo. Intenta recargar la página.');
          if (btn) { btn.disabled = false; btn.textContent = 'Ver mis recuerdos'; }
          return;
        }
        
        const resp = await fetch(`/memory/cofre?device_id=${encodeURIComponent(deviceId)}`);
        if (!resp.ok) throw new Error('Error fetching memories: ' + resp.status);
        const data = await resp.json();
        const memories = data.important_memories || [];
        
        if (list) list.innerHTML = '';
        if (!memories.length) {
          appendConversation('Compa', 'No tienes recuerdos guardados todavía.');
          if (btn) { btn.disabled = false; btn.textContent = 'Ver mis recuerdos'; }
          return;
        }
        
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
        const btn2 = document.getElementById(btnId);
        if (btn2) { btn2.disabled = false; btn2.textContent = 'Ver mis recuerdos'; }
      }
    }

    // Family messages

    async function loadFamilyMessages() {
      const deviceId = storageManager.getDeviceId();
      const resp = await fetch(`/family/messages?device_id=${encodeURIComponent(deviceId)}`);
      const btn = document.getElementById('showFamilyMessages');
      const list = document.getElementById('familyMessagesList');
      const countBadge = document.getElementById('unreadCount');

      try {
        if (btn) {
          btn.disabled = true;
          btn.innerHTML = 'Cargando mensajes... <span id="unreadCount" class="badge"></span>';
        }

        const resp = await fetch('/family/messages');
        if (!resp.ok) {
          if (resp.status === 503) {
            appendConversation('Compa', 'El sistema de mensajes familiares no está configurado todavía.');
            return;
          }
          throw new Error('Error fetching family messages: ' + resp.status);
        }

        const data = await resp.json();
        const messages = data.all_messages || [];
        unreadMessagesCount = data.total_unread || messages.filter(m => !m.read).length;

        if (countBadge) {
          countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
          countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
        }

        if (list) list.innerHTML = '';

        if (!messages.length) {
          appendConversation('Compa', 'No tienes mensajes guardados de tus familiares.');
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Ver mensajes <span id="unreadCount" class="badge"></span>';
          }
          return;
        }

        messages.sort((a,b) => (new Date(b.timestamp || 0)) - (new Date(a.timestamp || 0)));
        messages.slice(0, 50).forEach((msg) => {
          const el = document.createElement('div');
          el.className = 'family-item' + (msg.read ? '' : ' unread');

          const date = msg.date || (msg.timestamp ? new Date(msg.timestamp).toLocaleDateString('es-ES') : '—');
          const time = msg.time || (msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit'}) : '');

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

          const readBtn = el.querySelector('.btn-read');
          if (readBtn) {
            readBtn.addEventListener('click', (e) => {
              e.preventDefault();
              const messageId = msg.id;
              const readText = `Mensaje de ${msg.sender_name || 'un familiar'} del ${date} a las ${time}: ${msg.message}`;
              appendConversation('Compa', readText);

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
        const btn2 = document.getElementById('showFamilyMessages');
        if (btn2) {
          btn2.disabled = false;
          btn2.innerHTML = `Ver mensajes <span id="unreadCount" class="badge">${unreadMessagesCount > 0 ? unreadMessagesCount : ''}</span>`;
        }
      }
    }

    async function markMessageAsRead(messageId) {
      try {
        console.log(`🔄 Enviando petición para marcar mensaje ${messageId} como leído`);
        
        const resp = await fetch(`/family/messages/${messageId}/read`, { 
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

    async function readFamilyMessagesSequence(messages) {
      if (!messages || messages.length === 0) {
        console.log('❌ No hay mensajes para leer');
        return;
      }

      console.log(`🔊 Iniciando lectura de ${messages.length} mensajes`);

      for (const [index, msg] of messages.entries()) {
        try {
          const messageText = `De ${msg.sender_name || 'un familiar'}: ${msg.message}`;
          
          appendConversation('Compa', `📨 ${msg.sender_name}: ${msg.message}`);
          
          if (speakEnabled) {
            await new Promise(resolve => {
              speakTextSoft(messageText, { onComplete: resolve });
            });
          }

          console.log(`📝 Marcando mensaje ${msg.id} como leído`);
          try {
            const response = await fetch(`/family/messages/${msg.id}/read`, {
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

          if (index < messages.length - 1) {
            await new Promise(r => setTimeout(r, 800));
          }
          
        } catch (err) {
          console.error(`Error procesando mensaje ${msg.id}:`, err);
        }
      }

      const finalText = "Esos son todos los mensajes. ¿En qué más puedo ayudarte?";
      appendConversation('Compa', finalText);
      if (speakEnabled && !isSpeaking) {
        speakTextSoft(finalText);
      }
    }

    function updateMessageInUI(messageId) {
      const messageElements = document.querySelectorAll('.family-item');
      messageElements.forEach(element => {
        const btn = element.querySelector('.btn-mark-read');
        if (btn && parseInt(btn.getAttribute('data-id')) === messageId) {
          element.classList.remove('unread');
          
          if (btn) btn.remove();
          
          const dot = element.querySelector('.unread-dot');
          if (dot) dot.remove();
          
          console.log(`✅ UI actualizada para mensaje ${messageId}`);
        }
      });

      unreadMessagesCount = Math.max(0, unreadMessagesCount - 1);
      const countBadge = document.getElementById('unreadCount');
      if (countBadge) {
        countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
        countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
      }
    }


    async function checkForNewMessages() {
      try {
        const resp = await fetch('/family/messages');
        if (resp.ok) {
          const data = await resp.json();
          const newCount = data.total_unread || 0;
          
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
        }
      } catch (e) {
        console.error('Error checking for new messages:', e);
      }
    }

    // BOOT

// Variables globales para el modal de conexión
    let currentRequestId = null;

    function showConnectionRequestModal(requestId, userInfo) {
        currentRequestId = requestId;
        
        const modal = document.getElementById('connectionRequestModal');
        const info = document.getElementById('connectionRequestInfo');
        
        const userName = userInfo.user_full_name || userInfo.user_name;
        const username = userInfo.username || 'sin usuario';
        
        info.innerHTML = `
            <p><strong>👤 Usuario:</strong> ${userName}</p>
            <p><strong>📱 Telegram:</strong> @${username}</p>
            <p><strong>🆔 Chat ID:</strong> ${userInfo.chat_id}</p>
            <hr style="margin: 15px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #666;">¿Deseas permitir que esta persona envíe mensajes a este dispositivo?</p>
        `;
        
        modal.style.display = 'flex';
        
        // Reproducir sonido de notificación
        if (speakEnabled && !isSpeaking) {
            speakTextSoft(`${userName} quiere conectarse. ¿Lo permites?`);
        }
        
        console.log(`🔔 Solicitud de conexión de ${userName} (@${username})`);
    }

    function hideConnectionRequestModal() {
        const modal = document.getElementById('connectionRequestModal');
        modal.style.display = 'none';
        currentRequestId = null;
    }

    function sendConnectionResponse(approved) {
        if (!currentRequestId) {
            console.warn('⚠️ No hay solicitud pendiente');
            return;
        }
        
        const response = {
            type: "connection_response",
            request_id: currentRequestId,
            approved: approved
        };
        
        sendMessageToServer(JSON.stringify(response));
        
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

    // BOOT

    async function boot() {
      try {
        connectWebSocket();
        await loadVoices();
        ensureConversation();

        // Botón de ver recuerdos
        const btn = document.getElementById(btnId);
        if (btn) {
          btn.addEventListener('click', (e) => {
            e.preventDefault();
            showMyMemoriesUI();
          });
        } else {
          console.warn(`#${btnId} no encontrado en el DOM; añade el botón en index.html`);
        }

        // Botón de mensajes familiares
        const familyBtn = document.getElementById('showFamilyMessages');
        if (familyBtn) {
          familyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            loadFamilyMessages();
          });
        } else {
          console.warn('#showFamilyMessages no encontrado en el DOM');
        }

        // Botones del modal de conexión
        const approveBtn = document.getElementById('approveConnectionBtn');
        const rejectBtn = document.getElementById('rejectConnectionBtn');
        
        if (approveBtn) {
          approveBtn.addEventListener('click', () => {
            console.log('🟢 Usuario aprobó la conexión');
            sendConnectionResponse(true);
          });
        } else {
          console.warn('#approveConnectionBtn no encontrado en el DOM');
        }
        
        if (rejectBtn) {
          rejectBtn.addEventListener('click', () => {
            console.log('🔴 Usuario rechazó la conexión');
            sendConnectionResponse(false);
          });
        } else {
          console.warn('#rejectConnectionBtn no encontrado en el DOM');
        }

        // Cerrar modal si se hace clic fuera
        const modal = document.getElementById('connectionRequestModal');
        if (modal) {
          modal.addEventListener('click', (e) => {
            if (e.target === modal) {
              console.log('⚠️ Modal cerrado sin responder - asumiendo rechazo');
              sendConnectionResponse(false);
            }
          });
        }

        // Verificar nuevos mensajes periódicamente
        setInterval(checkForNewMessages, 120000);

        // Inicializar detección de audio
        await initAudioDetection((rms) => {
          if (VERBOSE) console.log(`🎚️ RMS: ${rms.toFixed(4)} / Umbral: ${rmsThreshold}`);
        });

        // Exponer API global
        window.__Acompania = {
          setThreshold: (v) => { rmsThreshold = v; console.log('Umbral RMS cambiado a', v); },
          getThreshold: () => rmsThreshold,
          storageManager: storageManager,
          saveData: (data) => storageManager.saveData(data),
          loadData: () => storageManager.loadData(),
          clearData: () => storageManager.clearData(),
          setVoiceParams: (p) => { Object.assign(voiceParams, p); console.log('voiceParams actualizados', voiceParams); },
          getVoiceParams: () => ({...voiceParams}),
          startRecognition: () => startRecognition(),
          stopRecognition: () => stopRecognition(),
          reconnectWS: () => connectWebSocket(),
          sendMessage: (t) => { appendConversation('Tú', t); sendMessageToServer(t); },
          enableSpeech: (b) => { speakEnabled = !!b; console.log('TTS enabled =', speakEnabled); },
          getVoices: () => window.speechSynthesis.getVoices(),
          showMemoriesUI: () => showMyMemoriesUI(),
          loadFamilyMessages: () => loadFamilyMessages(),
          markMessageAsRead: (id) => markMessageAsRead(id),
          // Nuevas funciones para debug
          showConnectionModal: (userInfo) => showConnectionRequestModal('test_123', userInfo),
          approveConnection: () => sendConnectionResponse(true),
          rejectConnection: () => sendConnectionResponse(false),
          getDeviceInfo: () => ({
            device_id: storageManager.getDeviceId(),
            device_code: storageManager.getDeviceCode()
          })
        };

        console.log('🚀 Compa inicializado correctamente (prioridad al usuario)');
        console.log('📱 Device ID:', storageManager.getDeviceId());
        console.log('🔢 Device Code:', storageManager.getDeviceCode());
        console.log('💡 Usa window.__Acompania para acceder a funciones de debug');
        
      } catch (err) {
        console.error('Error arranque app:', err);
        
        // Mostrar error en la UI
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
          <strong>⚠️ Error de inicialización</strong><br>
          <small>${err.message || 'Error desconocido'}</small><br>
          <small style="opacity:0.8;">Intenta recargar la página</small>
        `;
        document.body.appendChild(errorDiv);
        
        // Auto-ocultar después de 10 segundos
        setTimeout(() => {
          errorDiv.style.opacity = '0';
          errorDiv.style.transition = 'opacity 1s';
          setTimeout(() => errorDiv.remove(), 1000);
        }, 10000);
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }

  })();
}