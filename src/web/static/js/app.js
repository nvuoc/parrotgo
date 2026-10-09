/**
 * ParrotGo Voice AI - Phone Call Voice Assistant
 * Hands-free, Continuous Voice Conversation (STT -> LangGraph LLM -> Neural TTS)
 */

(function () {
  'use strict';

  // Application State
  const state = {
    sessionId: null,
    customerName: 'Anh Nam',
    customerPhone: '0912345678',
    customerCity: 'Hồ Chí Minh',
    callActive: false,
    micMuted: false,
    speakerMuted: false,
    currentBotText: '', // Câu văn bot đang phát ra loa để lọc dội âm
    lastBotText: '',    // Lưu lại câu bot vừa nói để lọc âm dội sót lại trong vài giây
    botFinishTimestamp: 0, // Thời điểm bot kết thúc nói
    mediaStream: null,   // Stream có phần cứng Acoustic Echo Cancellation
    callDurationSeconds: 0,
    timerInterval: null,
    recognition: null,
    isBotSpeaking: false,
    isUserSpeaking: false,
    isProcessing: false,
  };

  // DOM Elements Cache
  const els = {
    screenSetup: document.getElementById('screen-setup'),
    screenActiveCall: document.getElementById('screen-active-call'),
    inputName: document.getElementById('input-name'),
    inputPhone: document.getElementById('input-phone'),
    selectCity: document.getElementById('select-city'),
    btnCallStart: document.getElementById('btn-call-start'),

    callerDisplayId: document.getElementById('caller-display-id'),
    callDuration: document.getElementById('call-duration'),
    callStatusBadge: document.getElementById('call-status-badge'),
    subtitleSpeaker: document.getElementById('subtitle-speaker'),
    subtitleText: document.getElementById('subtitle-text'),

    btnMicToggle: document.getElementById('btn-mic-toggle'),
    micLabel: document.getElementById('mic-label'),
    btnSpeakerToggle: document.getElementById('btn-speaker-toggle'),
    speakerLabel: document.getElementById('speaker-label'),
    btnEndCall: document.getElementById('btn-end-call'),

    ttsAudioPlayer: document.getElementById('tts-audio-player'),
  };

  /* ==========================================================================
     1. CALL LIFECYCLE & TIMER
     ========================================================================== */
  function startCallTimer() {
    stopCallTimer();
    state.callDurationSeconds = 0;
    els.callDuration.textContent = '00:00';
    state.timerInterval = setInterval(() => {
      state.callDurationSeconds += 1;
      const mins = String(Math.floor(state.callDurationSeconds / 60)).padStart(2, '0');
      const secs = String(state.callDurationSeconds % 60).padStart(2, '0');
      els.callDuration.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  function stopCallTimer() {
    if (state.timerInterval) {
      clearInterval(state.timerInterval);
      state.timerInterval = null;
    }
  }

  function setCallVisualState(mode, text) {
    els.screenActiveCall.classList.remove('speaking', 'listening', 'thinking');
    if (mode) {
      els.screenActiveCall.classList.add(mode);
    }
    if (text) {
      els.callStatusBadge.textContent = text;
    }
  }

  /* ==========================================================================
     2. START CALL
     ========================================================================== */
  async function startCall() {
    const name = els.inputName.value.trim() || 'Quý khách';
    const phone = els.inputPhone.value.trim() || '0988888888';
    const city = els.selectCity.value;

    state.customerName = name;
    state.customerPhone = phone;
    state.customerCity = city;
    state.callActive = true;
    state.micMuted = false;
    state.speakerMuted = false;

    // Switch screen to Active Call
    els.screenSetup.style.display = 'none';
    els.screenActiveCall.style.display = 'flex';

    els.callerDisplayId.textContent = `${name} (${phone}) • ${city}`;
    els.subtitleSpeaker.textContent = 'ParrotGo:';
    els.subtitleText.textContent = 'Đang kết nối đến tổng đài...';
    setCallVisualState('thinking', 'Đang kết nối...');

    startCallTimer();

    // Khởi tạo phần cứng khử tiếng vang (Acoustic Echo Cancellation) của trình duyệt
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        state.mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
      }
    } catch (e) {
      console.warn("Lưu ý về AEC:", e);
    }

    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, phone, city }),
      });

      if (!res.ok) {
        throw new Error('Không thể kết nối máy chủ tổng đài.');
      }

      const data = await res.json();
      state.sessionId = data.session_id;

      // Bot speaks initial greeting
      updateSubtitle('ParrotGo', data.greeting);
      speakBotResponse(data.greeting);

    } catch (err) {
      updateSubtitle('Hệ thống', 'Lỗi kết nối cuộc gọi: ' + err.message);
      setCallVisualState('', 'Lỗi kết nối');
    }
  }

  /* ==========================================================================
     3. END CALL
     ========================================================================== */
  function endCall() {
    state.callActive = false;
    stopCallTimer();
    stopBotSpeaking();
    stopListening();

    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((track) => track.stop());
      state.mediaStream = null;
    }

    if (state.sessionId) {
      fetch(`/api/sessions/${state.sessionId}`, { method: 'DELETE' }).catch(() => {});
      state.sessionId = null;
    }

    setCallVisualState('', 'Đã kết thúc');

    setTimeout(() => {
      els.screenActiveCall.style.display = 'none';
      els.screenSetup.style.display = 'flex';
    }, 400);
  }

  /* ==========================================================================
     4. BOT SPEECH (TTS) & TURN-BASED HANDOFF TO MIC
     ========================================================================== */
  async function speakBotResponse(text) {
    if (!state.callActive) return;

    // TẮT MICRO HOÀN TOÀN TRONG LÚC BOT NÓI (Chống tự thu âm và chống ngắt lời)
    stopListening();
    state.isBotSpeaking = true;
    setCallVisualState('speaking', 'ParrotGo đang nói...');

    if (state.speakerMuted) {
      setTimeout(() => {
        onBotFinishSpeaking();
      }, 1500);
      return;
    }

    // Try Azure Neural TTS API
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: 'vi-VN-HoaiMyNeural' }),
      });

      if (res.ok) {
        const blob = await res.blob();
        const audioUrl = URL.createObjectURL(blob);
        els.ttsAudioPlayer.src = audioUrl;

        els.ttsAudioPlayer.onended = () => {
          onBotFinishSpeaking();
          URL.revokeObjectURL(audioUrl);
        };

        els.ttsAudioPlayer.onerror = () => {
          speakWithBrowser(text);
        };

        await els.ttsAudioPlayer.play();
        return;
      }
    } catch (e) {
      // Fallback to browser Web Speech API
    }

    speakWithBrowser(text);
  }

  function speakWithBrowser(text) {
    if (!('speechSynthesis' in window)) {
      onBotFinishSpeaking();
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'vi-VN';
    utterance.rate = 1.05;

    const voices = window.speechSynthesis.getVoices();
    const viVoice = voices.find(v => v.lang.includes('vi') || v.lang.includes('VI'));
    if (viVoice) {
      utterance.voice = viVoice;
    }

    utterance.onend = () => {
      onBotFinishSpeaking();
    };

    utterance.onerror = () => {
      onBotFinishSpeaking();
    };

    window.speechSynthesis.speak(utterance);
  }

  function onBotFinishSpeaking() {
    state.isBotSpeaking = false;
    if (!state.callActive) return;

    // Đợi 300ms sau khi loa tắt hẳn để tiêu tán hết âm vọng trong phòng, rồi mới mở Micro
    setTimeout(() => {
      if (!state.callActive || state.isBotSpeaking || state.isProcessing) return;

      if (!state.micMuted) {
        startListening();
        setCallVisualState('listening', 'Đang nghe bạn nói...');
      } else {
        setCallVisualState('', 'Micro đang tắt');
      }
    }, 300);
  }

  function stopBotSpeaking() {
    state.isBotSpeaking = false;
    if (els.ttsAudioPlayer) {
      els.ttsAudioPlayer.pause();
      els.ttsAudioPlayer.currentTime = 0;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }

  /* ==========================================================================
     5. SPEECH RECOGNITION (STT) - TURN-BASED CONVERSATION
     ========================================================================== */
  function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;

    const recognition = new SpeechRecognition();
    recognition.lang = 'vi-VN';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      state.isUserSpeaking = true;
      if (!state.isBotSpeaking && !state.isProcessing) {
        setCallVisualState('listening', 'Đang nghe bạn nói...');
      }
    };

    recognition.onresult = (event) => {
      // Tuyệt đối không nhận diện khi bot đang nói hoặc đang xử lý
      if (state.isBotSpeaking || state.isProcessing) return;

      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          final += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }

      const text = (final || interim).trim();
      if (!text) return;

      updateSubtitle('Bạn', text);

      if (final && final.trim()) {
        recognition.stop();
        sendUtteranceToBot(final.trim());
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== 'no-speech') {
        console.warn('Speech error:', event.error);
      }
    };

    recognition.onend = () => {
      state.isUserSpeaking = false;
      // Chỉ duy trì lắng nghe khi ở lượt của người dùng (bot không nói, không xử lý)
      if (state.callActive && !state.isBotSpeaking && !state.isProcessing && !state.micMuted) {
        setTimeout(() => {
          if (state.callActive && !state.isBotSpeaking && !state.isProcessing && !state.micMuted) {
            try { recognition.start(); } catch (e) {}
          }
        }, 150);
      }
    };

    return recognition;
  }

  function startListening() {
    if (!state.callActive || state.micMuted || state.isProcessing || state.isBotSpeaking) return;

    if (!state.recognition) {
      state.recognition = initSpeechRecognition();
    }

    if (!state.recognition) {
      updateSubtitle('Lưu ý', 'Trình duyệt không hỗ trợ Web Speech API. Vui lòng mở bằng Google Chrome hoặc Microsoft Edge.');
      return;
    }

    try {
      state.recognition.start();
    } catch (e) {
      // Already running or starting
    }
  }

  function stopListening() {
    if (state.recognition) {
      try {
        state.recognition.stop();
      } catch (e) {}
    }
  }

  /* ==========================================================================
     6. SEND UTTERANCE TO PARROTGO LLM
     ========================================================================== */
  async function sendUtteranceToBot(message) {
    if (!state.callActive || !state.sessionId) return;

    state.isProcessing = true;
    stopListening();
    setCallVisualState('thinking', 'ParrotGo đang xử lý...');

    try {
      const res = await fetch(`/api/sessions/${state.sessionId}/turns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) {
        throw new Error('Lỗi phản hồi từ tổng đài');
      }

      const data = await res.json();
      state.isProcessing = false;

      updateSubtitle('ParrotGo', data.bot_response);
      speakBotResponse(data.bot_response);

    } catch (err) {
      state.isProcessing = false;
      const errorMsg = 'Dạ em chưa nghe rõ, mình nói lại giúp em nhé ạ.';
      updateSubtitle('ParrotGo', errorMsg);
      speakBotResponse(errorMsg);
    }
  }

  /* ==========================================================================
     7. UI HELPERS
     ========================================================================== */
  function updateSubtitle(speaker, text) {
    els.subtitleSpeaker.textContent = speaker + ':';
    els.subtitleText.textContent = text;
  }

  /* ==========================================================================
     8. EVENT LISTENERS SETUP
     ========================================================================== */
  function setupListeners() {
    // Start Call Button
    els.btnCallStart.addEventListener('click', startCall);

    // End Call Button
    els.btnEndCall.addEventListener('click', endCall);

    // Mic Toggle Button
    els.btnMicToggle.addEventListener('click', () => {
      state.micMuted = !state.micMuted;
      if (state.micMuted) {
        els.btnMicToggle.classList.remove('active');
        els.micLabel.textContent = 'Micro Tắt';
        stopListening();
        setCallVisualState('', 'Micro đã tắt');
      } else {
        els.btnMicToggle.classList.add('active');
        els.micLabel.textContent = 'Micro Bật';
        if (!state.isBotSpeaking && !state.isProcessing) {
          startListening();
        }
      }
    });

    // Speaker Toggle Button
    els.btnSpeakerToggle.addEventListener('click', () => {
      state.speakerMuted = !state.speakerMuted;
      if (state.speakerMuted) {
        els.btnSpeakerToggle.classList.remove('active');
        els.speakerLabel.textContent = 'Loa Tắt';
        stopBotSpeaking();
      } else {
        els.btnSpeakerToggle.classList.add('active');
        els.speakerLabel.textContent = 'Loa Ngoài';
      }
    });
  }

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    state.recognition = initSpeechRecognition();
    setupListeners();
  });

})();
