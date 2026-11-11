/**
 * useAudioCapture — React hook managing microphone capture and WebSocket streaming.
 *
 * Coordinates:
 * 1. Requesting user microphone permissions via getUserMedia.
 * 2. Creating an AudioContext at 16 kHz mono.
 * 3. Loading and mounting the AudioWorkletProcessor (audio-processor.js).
 * 4. Connecting the microphone stream into the AudioWorklet pipeline.
 * 5. Managing the WebSocket lifecycle (session.start, session.started, streaming binary frames, session.end).
 * 6. Live telemetry: frames sent count, instantaneous FPS calculation, status indicators.
 * 7. Routing binary server messages to playback queue.
 * 8. Error handling: microphone denied, connection dropped, provider errors (nothing fails silently).
 * 9. Clean teardown and resource deallocation on stop or unmount.
 * 10. Flushed turns (turnFilter.js): frames and reply messages that still
 *     arrive for a flushed turn are dropped here, before the page sees them.
 * 11. Push-to-talk (docs/contracts.md §2.8): in a "ptt" session the mic stays
 *     open, but frames are sent only during a press (pttPress.js).
 *     pttStart() also stops local playback at once when the agent is busy,
 *     without waiting for the server's audio.flush round trip.
 * 12. Reply language (docs/contracts.md §2.3, v0.10): sent in session.start;
 *     the language the server confirms in session.started is kept, as the mode is.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import {
  AUDIO_SAMPLE_RATE,
  AUDIO_FRAME_MS,
  WS_SESSION_URL,
  PTT_END_FALLBACK_MS,
} from '../config.js';
import {
  buildSessionStart,
  confirmedReplyLanguage,
  formatServerError,
} from '../turnState/turnContracts.js';
import { createTurnFilter } from '../turnState/turnFilter.js';
import { createPttPress, PRESS_STATES } from '../ptt/pttPress.js';

export function useAudioCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [micStatus, setMicStatus] = useState('idle'); // 'idle' | 'requesting' | 'active' | 'denied' | 'error'
  const [wsStatus, setWsStatus] = useState('disconnected'); // 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error'
  const [sessionId, setSessionId] = useState(null); // session_id from session.started, null when not active
  const [framesSent, setFramesSent] = useState(0);
  const [fps, setFps] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);
  // The session's input mode as the SERVER confirmed it in session.started.
  const [sessionMode, setSessionMode] = useState('vad'); // 'vad' | 'ptt'
  // The reply language the SERVER confirmed in session.started (v0.10).
  const [sessionReplyLanguage, setSessionReplyLanguage] = useState('any'); // 'any' | 'en' | 'hi'
  const [pressState, setPressState] = useState(PRESS_STATES.IDLE);

  // References to active hardware / network resources for reliable teardown
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const workletNodeRef = useRef(null);
  const muteNodeRef = useRef(null);
  const socketRef = useRef(null);
  const isSessionReadyRef = useRef(false);
  const isIntentionalStopRef = useRef(false);

  // Metrics & barge-in tracking
  const frameCountRef = useRef(0);
  const lastFpsTimeRef = useRef(0);
  const framesSinceLastFpsRef = useRef(0);
  const fpsIntervalRef = useRef(null);
  // Flushed turns, so their late frames are dropped (one per session).
  const turnFilterRef = useRef(null);

  // Push-to-talk. Refs, not state: the worklet and socket handlers read them
  // on every frame, and must see the latest value without a re-render.
  const sessionModeRef = useRef('vad');
  const pressRef = useRef(null); // createPttPress(...) for this session
  // The agent's turn while it is thinking or speaking (from turn.state),
  // so a press can flush it locally. null when the agent is not busy.
  const busyTurnIdRef = useRef(null);
  const flushPlaybackRef = useRef(null); // the page's flushPlayback
  // { turnId, at }: a local stop, waiting for the server's audio.flush.
  const localStopRef = useRef(null);

  /**
   * Stop active capture pipeline and release all resources cleanly.
   *
   * @param {object} [options]
   * @param {boolean} [options.preserveMicDenied=false] - If true, do not overwrite 'denied' mic status.
   */
  const stopCapture = useCallback((options = {}) => {
    isIntentionalStopRef.current = true;

    // 1. Clear FPS interval
    if (fpsIntervalRef.current) {
      clearInterval(fpsIntervalRef.current);
      fpsIntervalRef.current = null;
    }

    // 2. Disconnect and stop media stream tracks
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    // 3. Disconnect AudioWorklet and mute node
    if (workletNodeRef.current) {
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (muteNodeRef.current) {
      muteNodeRef.current.disconnect();
      muteNodeRef.current = null;
    }

    // 4. Close AudioContext
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    // 5. Send session.end and close WebSocket
    if (socketRef.current) {
      if (
        socketRef.current.readyState === WebSocket.OPEN &&
        isSessionReadyRef.current
      ) {
        try {
          socketRef.current.send(JSON.stringify({ type: 'session.end' }));
        } catch {
          // Socket may already be closing
        }
      }
      socketRef.current.close();
      socketRef.current = null;
    }

    isSessionReadyRef.current = false;
    // An open press dies with the socket; the server discards its audio.
    if (pressRef.current) pressRef.current.reset();
    pressRef.current = null;
    turnFilterRef.current = null;
    sessionModeRef.current = 'vad';
    busyTurnIdRef.current = null;
    localStopRef.current = null;
    setSessionMode('vad');
    setSessionReplyLanguage('any');
    setIsCapturing(false);

    if (!options.preserveMicDenied) {
      setMicStatus('idle');
    }

    setWsStatus('disconnected');
    setSessionId(null);
    setFps(0);
  }, []);

  /**
   * Clear active error message.
   */
  const clearError = useCallback(() => {
    setErrorMessage(null);
    if (micStatus === 'denied' || micStatus === 'error') {
      setMicStatus('idle');
    }
  }, [micStatus]);

  /**
   * Start microphone capture and WebSocket streaming.
   *
   * @param {function(ArrayBuffer): void} [onBinaryMessage] - callback for playback PCM.
   * @param {function(): void} [onFlushCommand] - callback for audio.flush.
   * @param {string} [persona='default'] - persona name for session.start.
   * @param {function(object): void} [onServerMessage] - callback for JSON messages.
   * @param {'vad'|'ptt'} [mode='vad'] - input mode for session.start (v0.9).
   * @param {'any'|'en'|'hi'} [replyLanguage='any'] - reply language for session.start (v0.10).
   */
  const startCapture = useCallback(async (onBinaryMessage, onFlushCommand, persona = 'default', onServerMessage, mode = 'vad', replyLanguage = 'any') => {
    if (isCapturing) {
      return;
    }

    isIntentionalStopRef.current = false;
    // Local consts as well as refs: this session's handlers keep using THEIR
    // filter even if a later session has replaced the ref.
    const filter = createTurnFilter();
    turnFilterRef.current = filter;
    flushPlaybackRef.current = onFlushCommand;
    setErrorMessage(null);
    setFramesSent(0);
    setFps(0);
    frameCountRef.current = 0;
    framesSinceLastFpsRef.current = 0;
    lastFpsTimeRef.current = performance.now();

    // Verify browser support
    if (
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== 'function'
    ) {
      const err = 'Browser does not support microphone audio capture (getUserMedia).';
      setErrorMessage(err);
      setMicStatus('error');
      return;
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      const err = 'Browser does not support Web Audio API (AudioContext).';
      setErrorMessage(err);
      setMicStatus('error');
      return;
    }

    try {
      // Step A: Request microphone access
      setMicStatus('requesting');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: AUDIO_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      mediaStreamRef.current = stream;
      setMicStatus('active');

      // Step B: Initialize AudioContext at target sample rate (16 kHz)
      const audioCtx = new AudioContextClass({
        sampleRate: AUDIO_SAMPLE_RATE,
        latencyHint: 'interactive',
      });
      audioContextRef.current = audioCtx;

      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      // Step C: Load AudioWorklet module
      await audioCtx.audioWorklet.addModule('/audio-processor.js');

      // Step D: Build Web Audio processing graph
      const sourceNode = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, 'vaani-audio-processor');
      workletNodeRef.current = workletNode;

      const muteNode = audioCtx.createGain();
      muteNode.gain.value = 0;
      muteNodeRef.current = muteNode;

      sourceNode.connect(workletNode);
      workletNode.connect(muteNode);
      muteNode.connect(audioCtx.destination);

      // Step E: Connect WebSocket
      setWsStatus('connecting');
      const socket = new WebSocket(WS_SESSION_URL);
      socket.binaryType = 'arraybuffer';
      socketRef.current = socket;

      // One push-to-talk press at a time; used only if the server confirms
      // a "ptt" session.
      const press = createPttPress({
        send: (message) => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(message));
          }
        },
        // The worklet answers with its last frame, then { type: 'last-frame' }.
        requestLastFrame: () => workletNode.port.postMessage('flush'),
        fallbackMs: PTT_END_FALLBACK_MS,
        onChange: setPressState,
      });
      pressRef.current = press;

      socket.onopen = () => {
        setWsStatus('connected');
        socket.send(
          JSON.stringify(
            buildSessionStart({
              persona,
              mode,
              replyLanguage,
              audio: { sample_rate: AUDIO_SAMPLE_RATE, channels: 1, frame_ms: AUDIO_FRAME_MS },
            }),
          ),
        );
      };

      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          // A frame of a flushed turn (by audio.flush, or by a local
          // push-to-talk stop) is stale: discard it.
          if (filter.dropFrame()) {
            return;
          }
          if (typeof onBinaryMessage === 'function') {
            onBinaryMessage(event.data);
          }
          return;
        }

        try {
          const msg = JSON.parse(event.data);
          // audio.start/end and agent.text/done of a flushed turn never
          // reach the page (turnFilter.js says which messages).
          if (filter.dropMessage(msg)) {
            return;
          }
          if (msg.type === 'session.started') {
            isSessionReadyRef.current = true;
            setSessionId(msg.session_id ?? null);
            // The server's mode wins: an older server answers without one,
            // and then the session is hands-free whatever we asked for.
            const confirmedMode = msg.mode === 'ptt' ? 'ptt' : 'vad';
            sessionModeRef.current = confirmedMode;
            setSessionMode(confirmedMode);
            // Same rule for the reply language: the server's answer is shown.
            setSessionReplyLanguage(confirmedReplyLanguage(msg));
            setWsStatus('ready');
          } else if (msg.type === 'audio.flush') {
            const flushTurnId = msg.turn_id;
            filter.flush(flushTurnId);
            const localStop = localStopRef.current;
            if (localStop && localStop.turnId === flushTurnId) {
              // How much sooner the speaker went quiet than it would have
              // waiting for the server: local stop -> this audio.flush.
              console.info(
                `[useAudioCapture] ptt local stop -> audio.flush: ${Math.round(performance.now() - localStop.at)} ms`,
              );
              localStopRef.current = null;
            }
            // Stops playback even if a local stop already did (harmless).
            if (typeof onFlushCommand === 'function') {
              onFlushCommand();
            }
            if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
              try {
                socketRef.current.send(
                  JSON.stringify({
                    type: 'flush.ack',
                    turn_id: typeof flushTurnId === 'string' ? flushTurnId : (flushTurnId ?? ''),
                    client_ts: performance.now(),
                  })
                );
              } catch (ackErr) {
                console.warn('[useAudioCapture] Failed to send flush.ack:', ackErr);
              }
            }
          } else if (msg.type === 'error') {
            // The code leads the banner text so the failing stage (ASR, LLM,
            // TTS, guardrail) is visible at a glance, not only in the console.
            const formatted = formatServerError(msg.code, msg.message);
            setErrorMessage(msg.code ? `${msg.code}: ${formatted}` : formatted);
            console.warn('[useAudioCapture] Server error:', msg.code, msg.message);
          } else if (msg.type === 'turn.state') {
            // Remember the agent's turn while it is busy: a speak press
            // flushes exactly that turn locally (pttStart).
            busyTurnIdRef.current =
              msg.state === 'thinking' || msg.state === 'speaking' ? msg.turn_id : null;
            if (msg.state === 'listening') {
              // Every error code is non-fatal (contracts.md 2.3). Once the user
              // starts a new turn, the previous turn's error is stale: clear it.
              // Connection and mic errors cannot arrive here (the socket is open
              // and audio is flowing), so this never hides one of those.
              setErrorMessage(null);
            }
          }

          if (typeof onServerMessage === 'function') {
            onServerMessage(msg);
          }
        } catch (parseErr) {
          console.warn('[useAudioCapture] Unparseable server message:', parseErr);
        }
      };

      socket.onerror = (evt) => {
        console.error('[useAudioCapture] WebSocket error:', evt);
        setWsStatus('error');
        setErrorMessage('WebSocket connection failed. Ensure the Vaani backend server is running on port 8000.');
      };

      socket.onclose = (evt) => {
        const wasSessionActive = isSessionReadyRef.current;
        setWsStatus('disconnected');
        isSessionReadyRef.current = false;
        press.reset(); // nothing more can be sent on this socket
        setIsCapturing(false);

        // If closed unexpectedly while active, report connection dropped
        if (wasSessionActive && !isIntentionalStopRef.current && !evt.wasClean) {
          setErrorMessage('Connection dropped: The voice session connection to the backend server was closed unexpectedly.');
        }
      };

      // Step F: Listen for frames from AudioWorklet and stream over WebSocket
      workletNode.port.onmessage = (event) => {
        const frameBuffer = event.data;

        // Not a frame: the worklet's answer to a push-to-talk stop. Every
        // frame of the press was handled before this message (port order),
        // so ptt.end can go now.
        if (!(frameBuffer instanceof ArrayBuffer)) {
          if (frameBuffer && frameBuffer.type === 'last-frame') {
            press.lastFrameSent();
          }
          return;
        }

        // Push-to-talk: frames only while a press is open (contracts.md 2.8).
        // The mic stays open between presses; those frames are just not sent.
        if (sessionModeRef.current === 'ptt' && !press.sendsFrames()) {
          return;
        }

        if (
          socketRef.current &&
          socketRef.current.readyState === WebSocket.OPEN &&
          isSessionReadyRef.current
        ) {
          socketRef.current.send(frameBuffer);
          frameCountRef.current += 1;
          framesSinceLastFpsRef.current += 1;
          setFramesSent(frameCountRef.current);
        }
      };

      // Step G: Start rolling FPS counter
      fpsIntervalRef.current = setInterval(() => {
        const now = performance.now();
        const elapsedSec = (now - lastFpsTimeRef.current) / 1000;
        if (elapsedSec > 0) {
          const currentFps = Math.round(framesSinceLastFpsRef.current / elapsedSec);
          setFps(currentFps);
        }
        framesSinceLastFpsRef.current = 0;
        lastFpsTimeRef.current = now;
      }, 1000);

      setIsCapturing(true);
    } catch (err) {
      console.error('[useAudioCapture] Failed to start audio capture:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        stopCapture({ preserveMicDenied: true });
        setMicStatus('denied');
        setErrorMessage('Microphone access was denied. Please allow microphone permissions in your browser.');
      } else {
        stopCapture();
        setMicStatus('error');
        setErrorMessage(err.message || 'Failed to initialize audio capture pipeline.');
      }
    }
  }, [isCapturing, stopCapture]);

  /**
   * Speak pressed (push-to-talk sessions only).
   *
   * If the agent is thinking or speaking, its turn is flushed HERE, before
   * ptt.start goes out: playback stops now, not one server round trip later,
   * and frames of that turn still on the wire are dropped by the filter. The
   * server then barges in on the press and sends audio.flush as usual.
   *
   * @returns {string|null} the agent turn cut locally, or null if none was.
   */
  const pttStart = useCallback(() => {
    const press = pressRef.current;
    if (sessionModeRef.current !== 'ptt' || !press || press.state !== PRESS_STATES.IDLE) {
      return null;
    }
    const cutTurnId = busyTurnIdRef.current;
    if (cutTurnId) {
      turnFilterRef.current.flush(cutTurnId);
      localStopRef.current = { turnId: cutTurnId, at: performance.now() };
    }
    // Always: even after the server says idle, the browser may still be
    // playing the end of a reply, and the user wants to talk now.
    if (typeof flushPlaybackRef.current === 'function') {
      flushPlaybackRef.current();
    }
    press.start();
    return cutTurnId;
  }, []);

  /** Stop pressed: ptt.end follows once the worklet's last frame is sent. */
  const pttStop = useCallback(() => {
    if (pressRef.current) {
      pressRef.current.stop();
    }
  }, []);

  useEffect(() => {
    return () => {
      stopCapture();
    };
  }, [stopCapture]);

  return {
    isCapturing,
    micStatus,
    wsStatus,
    sessionId,
    framesSent,
    fps,
    errorMessage,
    clearError,
    startCapture,
    stopCapture,
    sessionMode,
    sessionReplyLanguage,
    pressState,
    pttStart,
    pttStop,
  };
}
