import React, { useEffect, useRef } from 'react';
import { Box, Typography, LinearProgress, Stack } from '@mui/material';
import { Mic as MicIcon, SmartToy as AIIcon } from '@mui/icons-material';
import { useCall } from '../contexts/CallContext';

const AudioVisualizer: React.FC = () => {
  const { audioLevels, currentCall } = useCall();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const historyRef = useRef<number[][]>([[], []]);

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    canvas.width = canvas.offsetWidth;
    canvas.height = 100;

    const history = historyRef.current;
    const maxHistory = 50;

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Update history
      history[0].push(audioLevels.caller);
      history[1].push(audioLevels.ai);

      if (history[0].length > maxHistory) history[0].shift();
      if (history[1].length > maxHistory) history[1].shift();

      const drawWaveform = (data: number[], color: string, yOffset: number) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();

        const step = canvas.width / maxHistory;
        data.forEach((level, i) => {
          const x = i * step;
          const y = yOffset - (level * 30); // Scale the amplitude
          
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });

        ctx.stroke();
      };

      // Draw caller waveform
      drawWaveform(history[0], '#90caf9', canvas.height * 0.3);
      
      // Draw AI waveform
      drawWaveform(history[1], '#f48fb1', canvas.height * 0.7);

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [audioLevels]);

  const getVolumeColor = (level: number) => {
    if (level > 0.7) return 'error';
    if (level > 0.4) return 'warning';
    return 'success';
  };

  return (
    <Box>
      <Stack spacing={2}>
        {/* Caller Audio */}
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <MicIcon sx={{ mr: 1, color: '#90caf9' }} />
            <Typography variant="body2" sx={{ flexGrow: 1 }}>
              Caller
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {Math.round(audioLevels.caller * 100)}%
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={audioLevels.caller * 100}
            color={getVolumeColor(audioLevels.caller)}
            sx={{ height: 8, borderRadius: 1 }}
          />
        </Box>

        {/* AI Audio */}
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <AIIcon sx={{ mr: 1, color: '#f48fb1' }} />
            <Typography variant="body2" sx={{ flexGrow: 1 }}>
              AI Assistant
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {Math.round(audioLevels.ai * 100)}%
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={audioLevels.ai * 100}
            color={getVolumeColor(audioLevels.ai)}
            sx={{ height: 8, borderRadius: 1 }}
          />
        </Box>

        {/* Waveform Canvas */}
        {currentCall && (
          <Box sx={{ mt: 2 }}>
            <canvas
              ref={canvasRef}
              style={{
                width: '100%',
                height: '100px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderRadius: '8px',
              }}
            />
          </Box>
        )}
      </Stack>
    </Box>
  );
};

export default AudioVisualizer; 