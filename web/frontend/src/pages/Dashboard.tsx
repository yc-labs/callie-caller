import React, { useState } from 'react';
import {
  Box,
  Container,
  Grid,
  Paper,
  Typography,
  AppBar,
  Toolbar,
  Chip,
} from '@mui/material';
import { Phone as PhoneIcon, WifiCalling3 as WifiIcon } from '@mui/icons-material';
import CallControl from '../components/CallControl';
import CallStatus from '../components/CallStatus';
import AudioVisualizer from '../components/AudioVisualizer';
import LogViewer from '../components/LogViewer';
import TranscriptionPanel from '../components/TranscriptionPanel';
import { useSocket } from '../contexts/SocketContext';
import { useCall } from '../contexts/CallContext';

const Dashboard: React.FC = () => {
  const { connected } = useSocket();
  const { currentCall } = useCall();

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppBar position="static" sx={{ backgroundColor: '#1e1e2e' }}>
        <Toolbar>
          <PhoneIcon sx={{ mr: 2 }} />
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Callie Caller Control Center
          </Typography>
          <Chip
            icon={<WifiIcon />}
            label={connected ? 'Connected' : 'Disconnected'}
            color={connected ? 'success' : 'error'}
            size="small"
          />
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ mt: 3, mb: 3, flexGrow: 1, overflow: 'hidden' }}>
        <Grid container spacing={3} sx={{ height: '100%' }}>
          {/* Left Column - Call Control & Status */}
          <Grid item xs={12} md={4}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>
                    Call Control
                  </Typography>
                  <CallControl />
                </Paper>
              </Grid>
              
              {currentCall && (
                <Grid item xs={12}>
                  <Paper sx={{ p: 3 }}>
                    <Typography variant="h6" gutterBottom>
                      Call Status
                    </Typography>
                    <CallStatus />
                  </Paper>
                </Grid>
              )}

              <Grid item xs={12}>
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" gutterBottom>
                    Audio Levels
                  </Typography>
                  <AudioVisualizer />
                </Paper>
              </Grid>
            </Grid>
          </Grid>

          {/* Middle Column - Transcription */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, height: '100%', overflow: 'hidden' }}>
              <Typography variant="h6" gutterBottom>
                Live Transcription
              </Typography>
              <TranscriptionPanel />
            </Paper>
          </Grid>

          {/* Right Column - Logs */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, height: '100%', overflow: 'hidden' }}>
              <Typography variant="h6" gutterBottom>
                System Logs
              </Typography>
              <LogViewer />
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default Dashboard; 