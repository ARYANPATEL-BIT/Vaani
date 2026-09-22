/**
 * useAudioCapture — React hook managing microphone capture and WebSocket streaming.
 *
 * Coordinates:
 * 1. Requesting user microphone permissions via getUserMedia.
 * 2. Creating an AudioContext at 16 kHz mono.
 * 3. Loading and mounting the AudioWorkletProcessor (audio-processor.js).
 * 4. Connecting the microphone stream into the AudioWorklet pipeline.
 * 5. Managing the WebSocket lifecycle (session.start, session.ready, streaming binary frames, session.end).
 * 6. Live telemetry: frames sent count, instantaneous FPS calculation, status indicators.
 * 7. Clean teardown and resource deallocation on stop or unmount.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { AUDIO_SAMPLE_RATE, WS_URL } from '../config.js';

export function useAudioCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [micStatus, setMicStatus] = useState('idle'); // 'idle' | 'requesting' | 'active' | 'denied' | 'error'
  const [wsStatus, setWsStatus] = useState('disconnected'); // 'disconnected' | 'connecting' | 'connected' | 'ready' | 'error'
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
    setFps(0);
  }, []);

  /**
   * Start microphone capture and WebSocket streaming.
   */
  const startCapture = useCallback(async () => {
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
      setWsStatus('connecting');
      const socket = new WebSocket(WS_URL);
      socket.binaryType = 'arraybuffer';
      socketRef.current = socket;

      socket.onopen = () => {
        setWsStatus('connected');
        // Initiate handshake per docs/contracts.md
        socket.send(JSON.stringify({ type: 'session.start' }));
      };

      socket.onmessage = (event) => {
        try {
          if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'session.ready') {
              isSessionReadyRef.current = true;
              setWsStatus('ready');
            }
          }
        } catch (parseErr) {
          console.warn('[useAudioCapture] Non-JSON message from server:', parseErr);
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
    framesSent,
    fps,
    errorMessage,
    startCapture,
    stopCapture,
  };
}
