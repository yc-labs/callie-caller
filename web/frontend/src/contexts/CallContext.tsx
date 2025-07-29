import React, { createContext, useContext, useState, useEffect } from 'react';
import { useSocket } from './SocketContext';
import axios from 'axios';

export interface Call {
  call_id: string;
  number: string;
  status: string;
  use_ai: boolean;
  ai_model?: string;
  start_time?: string;
  end_time?: string;
}

export interface AudioLevels {
  caller: number;
  ai: number;
}

export interface LogEntry {
  call_id: string;
  type: string;
  level: string;
  message: string;
  timestamp: string;
}

export interface Transcription {
  call_id: string;
  speaker: 'caller' | 'ai';
  text: string;
  is_final: boolean;
  timestamp: string;
}

interface CallContextType {
  activeCalls: Call[];
  currentCall: Call | null;
  audioLevels: AudioLevels;
  logs: LogEntry[];
  transcriptions: Transcription[];
  makeCall: (number: string, options: any) => Promise<void>;
  endCall: (callId: string) => Promise<void>;
  selectCall: (callId: string) => void;
}

const CallContext = createContext<CallContextType>({
  activeCalls: [],
  currentCall: null,
  audioLevels: { caller: 0, ai: 0 },
  logs: [],
  transcriptions: [],
  makeCall: async () => {},
  endCall: async () => {},
  selectCall: () => {},
});

export const useCall = () => useContext(CallContext);

export const CallProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { socket } = useSocket();
  const [activeCalls, setActiveCalls] = useState<Call[]>([]);
  const [currentCall, setCurrentCall] = useState<Call | null>(null);
  const [audioLevels, setAudioLevels] = useState<AudioLevels>({ caller: 0, ai: 0 });
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([]);

  useEffect(() => {
    if (!socket) return;

    // Listen for call state updates
    socket.on('call_state', (data: any) => {
      setActiveCalls(prev => {
        const index = prev.findIndex(c => c.call_id === data.call_id);
        if (index >= 0) {
          const updated = [...prev];
          updated[index] = { ...updated[index], ...data };
          return updated;
        }
        return [...prev, data];
      });
    });

    // Listen for audio levels
    socket.on('audio_levels', (data: any) => {
      console.log('Received audio levels:', data);
      if (currentCall && data.call_id === currentCall.call_id) {
        setAudioLevels({ caller: data.caller, ai: data.ai });
      }
    });

    // Listen for logs
    socket.on('log_entry', (data: LogEntry) => {
      console.log('Received log entry:', data);
      if (currentCall && data.call_id === currentCall.call_id) {
        setLogs(prev => [...prev, data]);
      }
    });

    // Listen for transcriptions
    socket.on('transcription', (data: Transcription) => {
      console.log('Received transcription:', data);
      if (currentCall && data.call_id === currentCall.call_id) {
        setTranscriptions(prev => {
          if (data.is_final) {
            return [...prev, data];
          } else {
            // Update last transcription if it's from the same speaker
            const last = prev[prev.length - 1];
            if (last && last.speaker === data.speaker && !last.is_final) {
              return [...prev.slice(0, -1), data];
            }
            return [...prev, data];
          }
        });
      }
    });

    return () => {
      socket.off('call_state');
      socket.off('audio_levels');
      socket.off('log_entry');
      socket.off('transcription');
    };
  }, [socket, currentCall]);

  const makeCall = async (number: string, options: any) => {
    try {
      const response = await axios.post('/api/call', {
        number,
        ...options,
      });
      
      const call = response.data;
      setActiveCalls(prev => [...prev, call]);
      setCurrentCall(call);
      
      // Join WebSocket room for this call
      if (socket) {
        socket.emit('join_call', { call_id: call.call_id });
      }
    } catch (error) {
      console.error('Failed to make call:', error);
      throw error;
    }
  };

  const endCall = async (callId: string) => {
    try {
      await axios.post(`/api/call/${callId}/end`);
      
      // Leave WebSocket room
      if (socket) {
        socket.emit('leave_call', { call_id: callId });
      }
      
      setActiveCalls(prev => prev.filter(c => c.call_id !== callId));
      if (currentCall?.call_id === callId) {
        setCurrentCall(null);
        setLogs([]);
        setTranscriptions([]);
      }
    } catch (error) {
      console.error('Failed to end call:', error);
      throw error;
    }
  };

  const selectCall = (callId: string) => {
    const call = activeCalls.find(c => c.call_id === callId);
    if (call) {
      setCurrentCall(call);
      setLogs([]);
      setTranscriptions([]);
      
      // Join WebSocket room for this call
      if (socket) {
        socket.emit('join_call', { call_id: callId });
      }
    }
  };

  return (
    <CallContext.Provider
      value={{
        activeCalls,
        currentCall,
        audioLevels,
        logs,
        transcriptions,
        makeCall,
        endCall,
        selectCall,
      }}
    >
      {children}
    </CallContext.Provider>
  );
}; 