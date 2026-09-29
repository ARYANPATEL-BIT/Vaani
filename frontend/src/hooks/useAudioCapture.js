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
 * 7. Routing binary server messages (future playback audio) to an optional callback.
 * 8. Clean teardown and resource deallocation on stop or unmount.
 *
 * Week 2, Day 1: accepts a `persona` argument in startCapture, exposes sessionId
 * from the session.started acknowledgement.
 *
 * Protocol note: flush acknowledgement uses type "flush.ack" with fields
 * `turn_id` and `client_ts`, per backend/vaani/protocol.py FlushAck model.
 * The contracts.md changelog entry for Day 4 used "audio.flush.ack" and
 * "timestamp_ms" — those were wrong; the backend never accepted them. Fixed here.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { AUDIO_SAMPLE_RATE, AUDIO_FRAME_MS, WS_SESSION_URL } from '../config.js';

export function useAudioCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [micStatus, setMicStatus] = useState('idle'); // 'idle' | 'requesting' | 'active' | 'denied' | 'error'
  const [wsStatus, setWsStatus] = useState('disconnected'); // 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error'
  const [sessionId, setSessionId] = useState(null); // session_id from session.started, null when not active
  const [framesSent, setFramesSent] = useState(0);
  const [fps, setFps] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);

  // References to active hardware / network resources for reliable teardown
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const workletNodeRef = useRef(null);
  const muteNodeRef = useRef(null);
  const socketRef = useRef(null);
  const isSessionReadyRef = useRef(false);

  // Metrics tracking
  const frameCountRef = useRef(0);
  const lastFpsTimeRef = useRef(0);
  const framesSinceLastFpsRef = useRef(0);
  const fpsIntervalRef = useRef(null);

  /**
   * Stop active capture pipeline and release all resources cleanly.
   */
  const stopCapture = useCallback(() => {
    // 1. Clear FPS interval
    if (fpsIntervalRef.current) {
      clearInterval(fpsIntervalRef.current);
      fpsIntervalRef.current = null;
    }

    // 2. Disconnect and stop media stream tracks (turns off browser mic indicator)
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
    setIsCapturing(false);
    setMicStatus('idle');
    setWsStatus('disconnected');
    setSessionId(null);
    setFps(0);
  }, []);

  /**
   * Start microphone capture and WebSocket streaming.
   *
   * @param {function(ArrayBuffer): void} [onBinaryMessage] - optional callback
   *   invoked for every binary WebSocket message received from the server.
   *   Day 3 passes the playback queue's enqueue() here so audio sent back by
   *   the server is played automatically.
   * @param {function(): void} [onFlushCommand] - optional callback
   *   invoked when the server sends an audio.flush control message.
   * @param {string} [persona='default'] - persona name sent in session.start.
   *   The backend accepts any string; only 'default' is currently meaningful.
   *   (Week 2, Day 1 addition.)
   * @param {function(object): void} [onServerMessage] - optional callback
   *   invoked for parsed JSON control messages received over the WebSocket.
   */
  const startCapture = useCallback(async (onBinaryMessage, onFlushCommand, persona = 'default', onServerMessage) => {
    // Guard against multiple concurrent capture pipelines
    if (isCapturing) {
      return;
    }

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

      // Resume context if suspended by browser autoplay policy
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      // Step C: Load AudioWorklet module
      // Uses the static module placed in frontend/public/audio-processor.js
      await audioCtx.audioWorklet.addModule('/audio-processor.js');

      // Step D: Build Web Audio processing graph
      const sourceNode = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, 'vaani-audio-processor');
      workletNodeRef.current = workletNode;

      // Connect worklet to a muted gain node, then to destination.
      // This keeps the Web Audio clock rendering frames without playing the mic back to speakers.
      const muteNode = audioCtx.createGain();
      muteNode.gain.value = 0;
      muteNodeRef.current = muteNode;

      sourceNode.connect(workletNode);
      workletNode.connect(muteNode);
      muteNode.connect(audioCtx.destination);

      // Step E: Connect WebSocket
      // Endpoint is /ws/session per backend/vaani/gateway.py and docs/contracts.md.
      setWsStatus('connecting');
      const socket = new WebSocket(WS_SESSION_URL);
      socket.binaryType = 'arraybuffer';
      socketRef.current = socket;

      socket.onopen = () => {
        setWsStatus('connected');
        // session.start requires the audio params so the backend can validate
        // our frame format before accepting any binary data (protocol.py §SessionStart).
        // The persona field is passed through from the caller; the backend stores
        // it on the Session object for future routing (Week 2+).
        socket.send(
          JSON.stringify({
            type: 'session.start',
            persona,
            audio: {
              sample_rate: AUDIO_SAMPLE_RATE,
              channels: 1,
              frame_ms: AUDIO_FRAME_MS,
            },
          }),
        );
      };

      socket.onmessage = (event) => {
        // Binary messages are audio chunks sent back by the server (playback).
        // Route them to the caller's callback (e.g. the playback queue's enqueue).
        if (event.data instanceof ArrayBuffer) {
          if (typeof onBinaryMessage === 'function') {
            onBinaryMessage(event.data);
          }
          return;
        }
        // Text messages are JSON control messages.
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'session.started') {
            // Backend sends 'session.started' (with session_id) per protocol.py.
            isSessionReadyRef.current = true;
            setSessionId(msg.session_id ?? null);
            setWsStatus('ready');
          } else if (msg.type === 'audio.flush') {
            const flushTurnId = msg.turn_id;
            if (typeof onFlushCommand === 'function') {
              onFlushCommand();
            }
            // Send flush.ack immediately after flushing.
            // Type is "flush.ack" and fields are turn_id + client_ts per
            // backend/vaani/protocol.py FlushAck model. (contracts.md Day 4
            // entry had the wrong type and field names — those are now fixed.)
            if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
              try {
                socketRef.current.send(
                  JSON.stringify({
                    type: 'flush.ack',
                    turn_id: flushTurnId,
                    client_ts: performance.now(),
                  })
                );
              } catch (ackErr) {
                console.warn('[useAudioCapture] Failed to send flush.ack:', ackErr);
              }
            }
          } else if (msg.type === 'error') {
            console.warn('[useAudioCapture] Server error:', msg.code, msg.message);
          }

          // Forward parsed control / server messages to optional subscriber
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
        setErrorMessage('WebSocket connection failed. Ensure Aryan\'s backend is running.');
      };

      socket.onclose = () => {
        setWsStatus('disconnected');
        isSessionReadyRef.current = false;
      };

      // Step F: Listen for frames from AudioWorklet and stream over WebSocket
      workletNode.port.onmessage = (event) => {
        const frameBuffer = event.data; // ArrayBuffer (640 bytes)

        // Only stream if WebSocket is open and session is ready
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

      // Step G: Start rolling FPS counter (updated once per second)
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
        setMicStatus('denied');
        setErrorMessage('Microphone access was denied. Please allow microphone permissions in your browser.');
      } else {
        setMicStatus('error');
        setErrorMessage(err.message || 'Failed to initialize audio capture pipeline.');
      }
      stopCapture();
    }
  }, [isCapturing, stopCapture]);

  // Clean up on component unmount
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
    startCapture,
    stopCapture,
  };
}
