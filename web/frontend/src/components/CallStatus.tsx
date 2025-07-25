import React, { useEffect, useState } from 'react';
import { Box, Typography, Chip, Stack, Divider } from '@mui/material';
import {
  Phone as PhoneIcon,
  Timer as TimerIcon,
  SmartToy as AIIcon,
  Mic as MicIcon,
} from '@mui/icons-material';
import { useCall } from '../contexts/CallContext';

const CallStatus: React.FC = () => {
  const { currentCall } = useCall();
  const [duration, setDuration] = useState('00:00');

  useEffect(() => {
    if (!currentCall?.start_time) return;

    const interval = setInterval(() => {
      const start = new Date(currentCall.start_time!).getTime();
      const now = Date.now();
      const diff = Math.floor((now - start) / 1000);
      
      const minutes = Math.floor(diff / 60);
      const seconds = diff % 60;
      
      setDuration(
        `${minutes.toString().padStart(2, '0')}:${seconds
          .toString()
          .padStart(2, '0')}`
      );
    }, 1000);

    return () => clearInterval(interval);
  }, [currentCall]);

  if (!currentCall) return null;

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'initiated':
        return 'info';
      case 'ringing':
        return 'warning';
      case 'connected':
        return 'success';
      case 'ended':
        return 'default';
      default:
        return 'default';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'initiated':
        return 'Connecting...';
      case 'ringing':
        return 'Ringing...';
      case 'connected':
        return 'Connected';
      case 'ended':
        return 'Call Ended';
      default:
        return status;
    }
  };

  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Chip
          label={getStatusLabel(currentCall.status)}
          color={getStatusColor(currentCall.status)}
          size="small"
        />
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <TimerIcon sx={{ mr: 0.5, fontSize: '1rem' }} />
          <Typography variant="body2">{duration}</Typography>
        </Box>
      </Box>

      <Divider />

      <Stack spacing={1}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <PhoneIcon sx={{ mr: 1, fontSize: '1rem', color: 'text.secondary' }} />
          <Typography variant="body2" color="text.secondary">
            Number:
          </Typography>
          <Typography variant="body2" sx={{ ml: 1 }}>
            {currentCall.number}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {currentCall.use_ai ? (
            <AIIcon sx={{ mr: 1, fontSize: '1rem', color: 'text.secondary' }} />
          ) : (
            <MicIcon sx={{ mr: 1, fontSize: '1rem', color: 'text.secondary' }} />
          )}
          <Typography variant="body2" color="text.secondary">
            Mode:
          </Typography>
          <Typography variant="body2" sx={{ ml: 1 }}>
            {currentCall.use_ai ? 'AI Assistant' : 'Direct Call'}
          </Typography>
        </Box>

        {currentCall.use_ai && currentCall.ai_model && (
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Box sx={{ width: '1rem', mr: 1 }} />
            <Typography variant="body2" color="text.secondary">
              Model:
            </Typography>
            <Typography variant="body2" sx={{ ml: 1 }}>
              {currentCall.ai_model}
            </Typography>
          </Box>
        )}
      </Stack>
    </Stack>
  );
};

export default CallStatus; 