import React, { useState } from 'react';
import {
  Box,
  TextField,
  Button,
  FormControlLabel,
  Switch,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Collapse,
  Alert,
  Stack,
} from '@mui/material';
import { Call as CallIcon, CallEnd as CallEndIcon } from '@mui/icons-material';
import { useCall } from '../contexts/CallContext';

const CallControl: React.FC = () => {
  const { currentCall, makeCall, endCall } = useCall();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [useAI, setUseAI] = useState(true);
  const [aiModel, setAiModel] = useState('gemini-2.0-flash-live-001');
  const [contextMessage, setContextMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleMakeCall = async () => {
    setError(null);
    setLoading(true);

    try {
      await makeCall(phoneNumber, {
        use_ai: useAI,
        ai_model: aiModel,
        message: contextMessage,
      });
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to make call');
    } finally {
      setLoading(false);
    }
  };

  const handleEndCall = async () => {
    if (currentCall) {
      try {
        await endCall(currentCall.call_id);
      } catch (err: any) {
        setError(err.response?.data?.error || 'Failed to end call');
      }
    }
  };

  const formatPhoneNumber = (value: string) => {
    // Remove all non-digits
    const digits = value.replace(/\D/g, '');
    
    // Format as US phone number
    if (digits.length <= 3) {
      return digits;
    } else if (digits.length <= 6) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    } else if (digits.length <= 10) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    } else {
      return `+${digits.slice(0, 1)} (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7, 11)}`;
    }
  };

  return (
    <Box>
      <Stack spacing={3}>
        {error && (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <TextField
          fullWidth
          label="Phone Number"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(formatPhoneNumber(e.target.value))}
          placeholder="(555) 123-4567"
          disabled={!!currentCall}
        />

        <FormControlLabel
          control={
            <Switch
              checked={useAI}
              onChange={(e) => setUseAI(e.target.checked)}
              disabled={!!currentCall}
            />
          }
          label="Use AI Assistant"
        />

        <Collapse in={useAI}>
          <Stack spacing={2}>
            <FormControl fullWidth>
              <InputLabel>AI Model</InputLabel>
              <Select
                value={aiModel}
                onChange={(e) => setAiModel(e.target.value)}
                label="AI Model"
                disabled={!!currentCall}
              >
                <MenuItem value="gemini-2.0-flash-live-001">Gemini 2.0 Flash Live</MenuItem>
                <MenuItem value="gemini-2.5-flash-live-preview">Gemini 2.5 Flash Live Preview</MenuItem>
                <MenuItem value="gemini-2.5-flash-preview-native-audio-dialog">Gemini 2.5 Flash Native Audio Dialog</MenuItem>
                <MenuItem value="gemini-2.5-flash-exp-native-audio-thinking-dialog">Gemini 2.5 Flash Native Audio Thinking</MenuItem>
              </Select>
            </FormControl>

            <TextField
              fullWidth
              multiline
              rows={3}
              label="Context Message"
              value={contextMessage}
              onChange={(e) => setContextMessage(e.target.value)}
              placeholder="Give the AI context about this call..."
              disabled={!!currentCall}
            />
          </Stack>
        </Collapse>

        {!currentCall ? (
          <Button
            fullWidth
            variant="contained"
            color="primary"
            size="large"
            startIcon={<CallIcon />}
            onClick={handleMakeCall}
            disabled={!phoneNumber || loading}
          >
            {loading ? 'Connecting...' : 'Start Call'}
          </Button>
        ) : (
          <Button
            fullWidth
            variant="contained"
            color="error"
            size="large"
            startIcon={<CallEndIcon />}
            onClick={handleEndCall}
          >
            End Call
          </Button>
        )}
      </Stack>
    </Box>
  );
};

export default CallControl; 