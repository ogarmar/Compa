// app.js — Prioridad al usuario: si empiezas a hablar, interrumpe la TTS inmediatamente.
// Basado en la versión previa (muestra recuerdos en pantalla, TTS suave).
if (window.__ACOMPANIA_APPJS_LOADED) {
  console.warn('app.js ya inicializado — evitando ejecución duplicada');
} else {
  window.__ACOMPANIA_APPJS_LOADED = true;

  (function () {
    // CONFIG
    const WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
    let rmsThreshold = 0.07; // umbral
    const SILENCE_TO_SEND_MS = 1000;
    const KEEPALIVE_MS = 60000;
    const RESTART_RECOGNITION_DELAY_MS = 300;
    const VERBOSE = false;

    // ESTADO
    let ws = null;
    let keepaliveInterval = null;
    let audioStream = null;
    let audioCtx = null;
    let analyser = null;
    let recognition = null;
    let recognitionActive = false;
    let recognitionStarting = false;
    let isSpeaking = false;             // indica que TTS está reproduciendo (cliente)
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

    // --- Variables para control de interrupciones ---
    let assistantSpeechSessionId = 0;
    let userIsTalking = false;

    // --- Variables para mensajes familiares ---
    let unreadMessagesCount = 0;

    // ----------------------------
    // DOM helpers
    // ----------------------------
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
      div.className = (author === 'Acompaña' || author === 'Compa' ? 'message assistant-message' : 'message user-message');
      div.innerHTML = `<strong>${author}:</strong> ${text}`;
      uiConversation.appendChild(div);
      uiConversation.scrollTop = uiConversation.scrollHeight;
    }

    function getMemoryElements() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      return { btn, list };
    }

    // ----------------------------
    // WebSocket
    // ----------------------------
    function connectWebSocket() {
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
      ws = new WebSocket(WS_URL);

      ws.addEventListener('open', () => {
        console.log('✅ WebSocket abierto', WS_URL);
        if (keepaliveInterval) clearInterval(keepaliveInterval);
        keepaliveInterval = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'keepalive', ts: Date.now() }));
            if (VERBOSE) console.log('→ keepalive enviado');
          }
        }, KEEPALIVE_MS);
      });

      ws.addEventListener('message', (ev) => {
        try {
          const parsed = JSON.parse(ev.data);
          if (parsed && parsed.type === 'message' && parsed.text) {
            handleServerText(parsed.text);
          } else if (parsed && (parsed.type === 'pong' || parsed.type === 'ping')) {
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
      appendConversation('Acompaña', text);
      if (!userIsTalking && speakEnabled) {
        speakTextSoft(text);
      } else {
        console.log('Usuario hablando — no reproducir TTS ahora.');
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

    // ----------------------------
    // TTS suave con session id
    // ----------------------------
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

    function speakTextSoft(text) {
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
            if (p.length <= 120) segments.push(p);
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
          setTimeout(() => {
            lastSpokenMessage = '';
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
          // Si el error es 'interrupted' o 'canceled', simplemente continuar
          if (e.error === 'interrupted' || e.error === 'canceled') {
            return;
          }
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

    // ----------------------------
    // Audio detection (RMS)
    // ----------------------------
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
        const MIN_SPEAK_MS = 700;
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

    // ----------------------------
    // SpeechRecognition
    // ----------------------------
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

    // ----------------------------
    // Mostrar recuerdos en pantalla
    // ----------------------------
    async function showMyMemoriesUI() {
      const btn = document.getElementById(btnId);
      const list = document.getElementById(memoryListId);
      try {
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Cargando recuerdos...';
        }
        const resp = await fetch('/memory/cofre');
        if (!resp.ok) throw new Error('Error fetching memories: ' + resp.status);
        const data = await resp.json();
        const memories = data.important_memories || [];
        if (list) list.innerHTML = '';
        if (!memories.length) {
          appendConversation('Acompaña', 'No tienes recuerdos guardados todavía.');
          if (btn) { btn.disabled = false; btn.textContent = 'Ver mis recuerdos'; }
          return;
        }
        const maxShow = 10;
        const toShow = memories.slice(0, maxShow);
        toShow.forEach((m, idx) => {
          const el = document.createElement('div');
          el.className = 'memory-item';
          el.innerText = `${idx+1}. ${m.content}`;
          if (list) list.appendChild(el);
        });
        appendConversation('Acompaña', `He mostrado ${toShow.length} recuerdos en tu cofre.`);
      } catch (e) {
        console.error('showMyMemoriesUI error', e);
        appendConversation('Acompaña', 'No he podido recuperar tus recuerdos ahora.');
        speakTextSoft('Lo siento, no he podido recuperar tus recuerdos ahora.');
      } finally {
        const btn2 = document.getElementById(btnId);
        if (btn2) { btn2.disabled = false; btn2.textContent = 'Ver mis recuerdos'; }
      }
    }

    // ----------------------------
    // Mensajes familiares
    // ----------------------------
    async function loadFamilyMessages() {
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
            appendConversation('Acompaña', 'El sistema de mensajes familiares no está configurado todavía.');
            return;
          }
          throw new Error('Error fetching family messages: ' + resp.status);
        }

        const data = await resp.json();
        const messages = data.messages || [];
        unreadMessagesCount = data.total_unread || 0;

        if (countBadge) {
          countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
          countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
        }

        if (list) list.innerHTML = '';

        if (!messages.length) {
          appendConversation('Acompaña', 'No tienes mensajes nuevos de tus familiares.');
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Ver mensajes <span id="unreadCount" class="badge"></span>';
          }
          return;
        }

        messages.slice(0, 10).forEach((msg) => {
          const el = document.createElement('div');
          el.className = 'family-item' + (msg.read ? '' : ' unread');
          
          const date = msg.date || new Date(msg.timestamp).toLocaleDateString('es-ES', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
          });
          
          const time = msg.time || new Date(msg.timestamp).toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit'
          });

          el.innerHTML = `
            <div class="family-item-header">
              <span class="family-item-sender">👤 ${msg.sender_name}</span>
              <span class="family-item-date">📅 ${date} 🕐 ${time}</span>
            </div>
            <div class="family-item-message">${msg.message}</div>
            ${!msg.read ? '<div class="family-item-status">📨 Nuevo</div>' : ''}
          `;

          if (list) list.appendChild(el);
        });

        // Leer mensajes en voz alta solo si hay NO LEÍDOS
        const unreadOnly = messages.filter(m => !m.read);
        
        if (unreadOnly.length > 0 && speakEnabled) {
          const summary = unreadOnly.length === 1 
            ? `Tienes un mensaje nuevo de ${unreadOnly[0].sender_name}` 
            : `Tienes ${unreadOnly.length} mensajes nuevos de tus familiares`;
          
          appendConversation('Acompaña', summary);
          speakTextSoft(summary);

          setTimeout(() => {
            const firstMsg = unreadOnly[0];
            const date = firstMsg.date || 'hoy';
            const time = firstMsg.time || '';
            const msgText = `Mensaje de ${firstMsg.sender_name} del día ${date} a las ${time}: ${firstMsg.message}`;
            appendConversation('Acompaña', msgText);
            speakTextSoft(msgText);

            markMessageAsRead(firstMsg.id);
          }, 2000);
        } else if (messagesToShow.length > 0) {
          const totalMsg = `Tienes ${messagesToShow.length} mensaje${messagesToShow.length > 1 ? 's' : ''} guardado${messagesToShow.length > 1 ? 's' : ''} de tus familiares.`;
          appendConversation('Acompaña', totalMsg);
        }

      } catch (e) {
        console.error('loadFamilyMessages error', e);
        appendConversation('Acompaña', 'No he podido cargar los mensajes ahora.');
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
        await fetch(`/family/messages/${messageId}/read`, { method: 'POST' });
        console.log(`Mensaje ${messageId} marcado como leído`);
        
        unreadMessagesCount = Math.max(0, unreadMessagesCount - 1);
        const countBadge = document.getElementById('unreadCount');
        if (countBadge) {
          countBadge.textContent = unreadMessagesCount > 0 ? unreadMessagesCount : '';
          countBadge.style.display = unreadMessagesCount > 0 ? 'inline-block' : 'none';
        }
      } catch (e) {
        console.error('Error marking message as read:', e);
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
            
            appendConversation('Acompaña', '¡Tienes mensajes nuevos de tus familiares!');
            if (speakEnabled && !isSpeaking) {
              speakTextSoft('Tienes mensajes nuevos de tus familiares. ¿Quieres que te los lea?');
            }
          }
        }
      } catch (e) {
        console.error('Error checking for new messages:', e);
      }
    }

    // ----------------------------
    // BOOT
    // ----------------------------
    async function boot() {
      try {
        connectWebSocket();
        await loadVoices();
        ensureConversation();

        const btn = document.getElementById(btnId);
        if (btn) {
          btn.addEventListener('click', (e) => {
            e.preventDefault();
            showMyMemoriesUI();
          });
        } else {
          console.warn(`#${btnId} no encontrado en el DOM; añade el botón en index.html`);
        }

        const familyBtn = document.getElementById('showFamilyMessages');
        if (familyBtn) {
          familyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            loadFamilyMessages();
          });
        } else {
          console.warn('#showFamilyMessages no encontrado en el DOM');
        }

        setInterval(checkForNewMessages, 120000);

        await initAudioDetection((rms) => {
          if (VERBOSE) console.log(`🎚️ RMS: ${rms.toFixed(4)} / Umbral: ${rmsThreshold}`);
        });

        window.__Acompania = {
          setThreshold: (v) => { rmsThreshold = v; console.log('Umbral RMS cambiado a', v); },
          getThreshold: () => rmsThreshold,
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
          markMessageAsRead: (id) => markMessageAsRead(id)
        };

        console.log('🚀 Acompaña inicializado correctamente (prioridad al usuario)');
      } catch (err) {
        console.error('Error arranque app:', err);
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }

  })();
}