import React, { useRef, useEffect } from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Avatar,
  Divider,
  Chip,
} from '@mui/material';
import { Person as PersonIcon, SmartToy as AIIcon } from '@mui/icons-material';
import { useCall } from '../contexts/CallContext';

const TranscriptionPanel: React.FC = () => {
  const { transcriptions, currentCall } = useCall();
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new transcriptions arrive
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [transcriptions]);

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  if (!currentCall) {
    return (
      <Box
        sx={{
          height: 'calc(100% - 32px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No active call
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      ref={listRef}
      sx={{
        height: 'calc(100% - 32px)',
        overflowY: 'auto',
        bgcolor: 'rgba(0, 0, 0, 0.2)',
        borderRadius: 1,
      }}
    >
      {transcriptions.length === 0 ? (
        <Box
          sx={{
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography variant="body2" color="text.secondary">
            Waiting for conversation...
          </Typography>
        </Box>
      ) : (
        <List>
          {transcriptions.map((transcription, index) => (
            <React.Fragment key={index}>
              <ListItem alignItems="flex-start">
                <ListItemAvatar>
                  <Avatar
                    sx={{
                      bgcolor:
                        transcription.speaker === 'caller'
                          ? 'primary.main'
                          : 'secondary.main',
                      width: 32,
                      height: 32,
                    }}
                  >
                    {transcription.speaker === 'caller' ? (
                      <PersonIcon sx={{ fontSize: 20 }} />
                    ) : (
                      <AIIcon sx={{ fontSize: 20 }} />
                    )}
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="subtitle2">
                        {transcription.speaker === 'caller' ? 'Caller' : 'AI Assistant'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatTimestamp(transcription.timestamp)}
                      </Typography>
                      {!transcription.is_final && (
                        <Chip
                          label="Speaking..."
                          size="small"
                          color="warning"
                          sx={{ height: 16, fontSize: '0.7rem' }}
                        />
                      )}
                    </Box>
                  }
                  secondary={
                    <Typography
                      component="span"
                      variant="body2"
                      sx={{
                        display: 'inline',
                        color: transcription.is_final
                          ? 'text.primary'
                          : 'text.secondary',
                        fontStyle: transcription.is_final ? 'normal' : 'italic',
                      }}
                    >
                      {transcription.text}
                    </Typography>
                  }
                />
              </ListItem>
              {index < transcriptions.length - 1 && (
                <Divider variant="inset" component="li" />
              )}
            </React.Fragment>
          ))}
        </List>
      )}
    </Box>
  );
};

export default TranscriptionPanel; 