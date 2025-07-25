import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Typography,
  List,
  ListItem,
  ListItemText,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import { Clear as ClearIcon } from '@mui/icons-material';
import { useCall } from '../contexts/CallContext';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`log-tabpanel-${index}`}
      aria-labelledby={`log-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ height: '100%' }}>{children}</Box>}
    </div>
  );
}

const LogViewer: React.FC = () => {
  const { logs } = useCall();
  const [tabValue, setTabValue] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [logs]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // Filter logs by type
  const filterLogs = (type: string) => {
    if (type === 'all') return logs;
    return logs.filter((log) => log.type === type);
  };

  const logTypes = [
    { label: 'All', type: 'all' },
    { label: 'SIP', type: 'sip' },
    { label: 'RTP/Audio', type: 'rtp' },
    { label: 'AI', type: 'ai' },
    { label: 'System', type: 'system' },
  ];

  const getLogColor = (level: string) => {
    switch (level) {
      case 'error':
        return 'error';
      case 'warning':
        return 'warning';
      case 'info':
        return 'info';
      case 'debug':
        return 'default';
      default:
        return 'default';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
    });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 32px)' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          aria-label="log tabs"
        >
          {logTypes.map((type, index) => (
            <Tab
              key={type.type}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {type.label}
                  <Chip
                    label={filterLogs(type.type).length}
                    size="small"
                    sx={{ height: 20, fontSize: '0.75rem' }}
                  />
                </Box>
              }
              id={`log-tab-${index}`}
              aria-controls={`log-tabpanel-${index}`}
            />
          ))}
        </Tabs>
      </Box>

      {logTypes.map((type, index) => (
        <TabPanel key={type.type} value={tabValue} index={index}>
          <Box
            ref={listRef}
            sx={{
              height: 'calc(100vh - 400px)',
              overflowY: 'auto',
              bgcolor: 'rgba(0, 0, 0, 0.2)',
              borderRadius: 1,
              p: 1,
            }}
          >
            <List dense>
              {filterLogs(type.type).map((log, idx) => (
                <ListItem
                  key={idx}
                  sx={{
                    py: 0.5,
                    borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography
                          variant="caption"
                          sx={{
                            fontFamily: 'monospace',
                            color: 'text.secondary',
                          }}
                        >
                          {formatTimestamp(log.timestamp)}
                        </Typography>
                        <Chip
                          label={log.level.toUpperCase()}
                          size="small"
                          color={getLogColor(log.level)}
                          sx={{ height: 16, fontSize: '0.7rem' }}
                        />
                      </Box>
                    }
                    secondary={
                      <Typography
                        component="span"
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                        }}
                      >
                        {log.message}
                      </Typography>
                    }
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        </TabPanel>
      ))}
    </Box>
  );
};

export default LogViewer; 