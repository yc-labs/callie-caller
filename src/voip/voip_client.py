# callie_caller/voip/voip_client.py
import os
import time
import wave
import math
import tempfile
import threading
import queue
import urllib.request
import json
import audioop
import pjsua2 as pj
import logging

# ---------- Small helpers ----------

logger = logging.getLogger(__name__)

def get_public_ip(timeout=3.0):
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=timeout) as resp:
            return json.loads(resp.read().decode())["ip"]
    except Exception as e:
        logger.warning(f"Public IP discovery failed ({e}); continuing without explicit publicAddress")
        return None

def synth_sine_wav(out_path, seconds=5, freq=440.0, rate=8000, amp=0.6):
    frames = int(seconds * rate)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(rate)
        for n in range(frames):
            sample = int(max(-1.0, min(1.0, amp * math.sin(2.0 * math.pi * freq * n / rate))) * 32767)
            wf.writeframesraw(sample.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(b"")

def write_wav_from_pcm16(out_path, pcm_bytes, rate_hz):
    """Write 16-bit little-endian mono PCM to WAV."""
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate_hz)
        wf.writeframes(pcm_bytes)

def resample_pcm16(pcm_bytes, src_rate, dst_rate):
    """Resample mono 16-bit PCM using stdlib audioop."""
    if not pcm_bytes or src_rate == dst_rate:
        return pcm_bytes
    converted, _ = audioop.ratecv(pcm_bytes, 2, 1, src_rate, dst_rate, None)
    return converted

# ---------- pjsua2 wrappers ----------

class MyAccount(pj.Account):
    def __init__(self, on_reg):
        super().__init__()
        self._on_reg = on_reg

    def onRegState(self, prm):
        info = self.getInfo()
        logger.info(f"Reg state: code={prm.code} reason={prm.reason} uri={info.uri}")
        self._on_reg(prm.code == 200)

class MyCall(pj.Call):
    def __init__(self, client, acc):
        super().__init__(acc)
        self.client = client
        self._player = None
        self._playlist_q = client._playlist_q
        self._playlist_thread_started = False
        self._playlist_lock = threading.Lock()
        self._rx_recorder = None
        self._mode = client.test_mode

    def onCallState(self, prm):
        ci = self.getInfo()
        code = getattr(ci, "lastStatusCode", None)
        reason = getattr(ci, "lastReason", "")
        logger.info(f"Call State={ci.stateText}, status={code}({reason})")
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.client._call_connected = True
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            logger.info("Call disconnected - setting _call_done to True")
            self.client._call_done = True

    def _ensure_playlist_worker(self, call_media):
        self.client._register_current_thread()
        # Store the call_media reference in both call and client for audio playback
        self._call_media = call_media
        self.client._call_media = call_media
        
        with self._playlist_lock:
            if self._playlist_thread_started:
                return
            self._playlist_thread_started = True
            
            def runner():
                logger.debug("Playlist worker thread started")
                # Buffer multiple audio chunks before playing to reduce choppiness
                audio_buffer = []
                buffer_duration = 0.0
                MIN_BUFFER_DURATION = 2.0  # Buffer at least 2 seconds before playing
                
                while not self.client._call_done:
                    try:
                        # Collect audio chunks
                        while buffer_duration < MIN_BUFFER_DURATION:
                            try:
                                wav_path = self._playlist_q.get(timeout=0.1)
                                audio_buffer.append(wav_path)
                                # Estimate duration (0.4s per chunk based on logs)
                                buffer_duration += 0.4
                            except queue.Empty:
                                if audio_buffer:
                                    break  # Play what we have if queue is empty
                                continue
                        
                        if audio_buffer and buffer_duration > 0:
                            # Combine all WAV files into one
                            combined_wav = self.client._combine_wav_files(audio_buffer)
                            if combined_wav:
                                # Store the combined audio for the main thread to play
                                self.client._pending_audio = combined_wav
                                logger.debug(f"Buffered {len(audio_buffer)} chunks into {combined_wav}, duration={buffer_duration:.1f}s")
                                # Wait for it to be played
                                while self.client._pending_audio and not self.client._call_done:
                                    time.sleep(0.05)
                            
                            # Cleanup original files
                            for wav in audio_buffer:
                                try:
                                    if os.path.exists(wav):
                                        os.remove(wav)
                                except OSError:
                                    pass
                            
                            audio_buffer = []
                            buffer_duration = 0.0
                            
                    except Exception as e:
                        logger.error(f"Playlist worker error: {e}")
                        
                logger.debug("Playlist worker thread exiting")
            
            t = threading.Thread(target=runner, name="sip-playlist", daemon=True)
            t.start()

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        
        try:
            # Log selected codec safely
            for mi in ci.media:
                if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                    codec = "<unknown>"
                    try:
                        si = self.getStreamInfo(0)  # MediaStreamInfo (self is the call object)
                        codec = getattr(si, "codecName", getattr(si, "codec_name", codec))
                    except Exception as e:
                        logger.warning(f"Could not get codec name: {e}")
                    logger.info(f"Active audio codec: {codec}")

            # Activate media
            for mi in ci.media:
                if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                    call_media = self.getAudioMedia(-1)

                    # Detect actual call clock rate
                    try:
                        pi = call_media.getPortInfo()
                        rate = int(getattr(pi.format, "clockRate", 0) or 0)
                        if rate > 0:
                            self.client._call_rate_hz = rate
                            logger.info(f"Call clock rate detected: {rate} Hz")
                    except Exception as e:
                        logger.warning(f"Could not read port info: {e}")

                    # Start RX recording
                    if self.client._rx_fifo_path and not self._rx_recorder:
                        try:
                            self._rx_recorder = pj.AudioMediaRecorder()
                            self._rx_recorder.createRecorder(self.client._rx_fifo_path)
                            call_media.startTransmit(self._rx_recorder)
                            logger.info(f"Recording call RX to FIFO: {self.client._rx_fifo_path}")
                        except pj.Error as e:
                            logger.error(f"Failed to start recorder: {e.info()}")

                    # TX worker
                    self._ensure_playlist_worker(call_media)

                    # Optional connect tone
                    if self._mode == "tone" and self.client.tone_seconds > 0:
                        try:
                            fd, wav_path = tempfile.mkstemp(prefix=self.client._tmp_dir_prefix, suffix=".wav")
                            os.close(fd)
                            synth_sine_wav(
                                wav_path,
                                seconds=self.client.tone_seconds,
                                freq=self.client.tone_freq,
                                rate=self.client._call_rate_hz,
                                amp=0.6,
                            )
                            self._playlist_q.put(wav_path)
                            logger.info(f"Queued connect-tone at {self.client._call_rate_hz} Hz")
                        except Exception as e:
                            logger.error(f"Tone queue error: {e}")
        except Exception as e:
            logger.error(f"Critical error in onCallMediaState: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def safe_stop(self):
        try:
            if self._rx_recorder:
                self._rx_recorder = None
        except Exception:
            pass
        try:
            if self._player:
                self._player = None
        except Exception:
            pass

class VoipClient:
    """
    Public methods used by the adapter:
      - enable_rx_fifo(path): record call RX to a named pipe (WAV header + PCM @ call-rate)
      - enqueue_pcm(pcm_bytes, src_rate_hz): enqueue AI PCM; auto-resamples to call-rate and plays to far end
    """
    def __init__(self, config, test_mode="tone", wav_path=None, tone_seconds=0, tone_freq=440.0):
        self.cfg = config
        self.test_mode = test_mode
        self.wav_path = wav_path
        self.tone_seconds = tone_seconds
        self.tone_freq = tone_freq
        self.pj_lock = threading.Lock()
        self._pj_thread = None
        self._ready_event = threading.Event()
        # Event used to signal the background PJSUA2 thread to stop
        self._stop_event = threading.Event()

        self.ep = None  # Will be created in _init_lib()
        self.acc = None
        self.active_call = None

        self._registered = False
        self._call_connected = False
        self._call_done = False

        self._rx_fifo_path = None
        self._playlist_q = queue.Queue()
        self._tmp_dir_prefix = "sip_tmp_"

        self._call_rate_hz = 8000  # updated on media-active
        self._call_media = None  # Will be set when call media becomes active
        self._pending_audio = None  # Audio file waiting to be played

    # ----- Public API -----

    def enable_rx_fifo(self, fifo_path: str):
        """Record far-end PCM into this named pipe (WAV header + 16-bit LE mono @ call-rate)."""
        self._rx_fifo_path = fifo_path
        
    def _register_current_thread(self):
        """Register the current thread with pjsua2 if not already registered."""
        if self.ep and not self.ep.libIsThreadRegistered():
            self.ep.libRegisterThread(threading.current_thread().name)

    def enqueue_pcm(self, pcm_bytes: bytes, src_rate_hz: int):
        """
        Enqueue arbitrary mono 16-bit PCM for playback to the far end.
        Automatically resamples to the *current call's* clock rate and wraps to WAV.
        Safe to call from any thread.
        """
        if not pcm_bytes:
            return
        try:
            dst_rate = int(self._call_rate_hz or 8000)
            pcm_dst = resample_pcm16(pcm_bytes, src_rate_hz, dst_rate)
            fd, wav_path = tempfile.mkstemp(prefix=self._tmp_dir_prefix, suffix=".wav")
            os.close(fd)
            write_wav_from_pcm16(wav_path, pcm_dst, dst_rate)
            self._playlist_q.put(wav_path)
            logger.debug(f"Queued audio for playback: {len(pcm_dst)} bytes at {dst_rate}Hz")
        except Exception as e:
            logger.error(f"enqueue_pcm error: {e}")

    def _combine_wav_files(self, wav_files):
        """Combine multiple WAV files into one"""
        try:
            if not wav_files:
                return None
                
            # Read all WAV files
            data = []
            rate = None
            for wav_path in wav_files:
                try:
                    with wave.open(wav_path, 'rb') as wf:
                        if rate is None:
                            rate = wf.getframerate()
                        frames = wf.readframes(wf.getnframes())
                        data.append(frames)
                except Exception as e:
                    logger.error(f"Error reading {wav_path}: {e}")
                    
            if not data or rate is None:
                return None
                
            # Combine all audio data
            combined_data = b''.join(data)
            
            # Write combined WAV
            fd, combined_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            
            with wave.open(combined_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(combined_data)
                
            logger.debug(f"Combined {len(wav_files)} chunks into {combined_path}, duration={len(combined_data)/(rate*2):.2f}s")
            return combined_path
            
        except Exception as e:
            logger.error(f"Error combining WAV files: {e}")
            return None

    # ----- PJSUA2 lifecycle -----

    def _init_lib(self):
        self._ready_event = threading.Event()
        self._stop_event.clear()
        self._pj_thread = threading.Thread(target=self._run_pjsua)
        self._pj_thread.daemon = True
        self._pj_thread.start()

    def _run_pjsua(self):
        self.ep = pj.Endpoint()
        self.ep.libCreate()
        # Ensure this worker thread is registered with pjlib before any other calls
        if not self.ep.libIsThreadRegistered():
            self.ep.libRegisterThread("pjsua-worker")

        ep_cfg = pj.EpConfig()
        ep_cfg.uaConfig.userAgent = self.cfg.get("user_agent", "pjsua2-py-client")
        ep_cfg.uaConfig.maxCalls = 1
        ep_cfg.medConfig.noVad = True

        ep_cfg.uaConfig.stunServer = pj.StringVector()
        ep_cfg.uaConfig.stunServer.append("stun.l.google.com:19302")

        self.ep.libInit(ep_cfg)

        tcfg = pj.TransportConfig()
        tcfg.port = int(os.getenv("SIP_PORT", 5060))
        pub = get_public_ip()
        if pub:
            tcfg.publicAddress = pub

        self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tcfg)

        try:
            self.ep.codecSetPriority("opus/48000", 255)
            self.ep.codecSetPriority("G722/8000", 254)
            self.ep.codecSetPriority("PCMU/8000", 200)
            self.ep.codecSetPriority("PCMA/8000", 180)
        except pj.Error as e:
            logger.warning(f"Codec priority set error: {e.info()}")

        self.ep.audDevManager().setNullDev()

        self.ep.libStart()
        logger.info("PJSUA2 started")
        
        # Signal that the library is ready
        self._ready_event.set()
        
        # Now register the account
        if self._register():
            logger.info("Registration successful")
        else:
            logger.error("Registration failed")

        # Main event loop. Runs until stop is signaled.
        while not self._stop_event.is_set():
            self.ep.libHandleEvents(20)

        logger.info("Event loop exiting")
        try:
            if self.ep and self.ep.libGetState() < pj.PJSUA_STATE_CLOSING:
                self.ep.libDestroy()
        finally:
            self.ep = None
            logger.info("PJSUA2 stopped")

    def _register(self):
        doms = [self.cfg["primary_domain"]]
        if self.cfg.get("fallback_domain"):
            doms.append(self.cfg["fallback_domain"])

        for domain in doms:
            logger.info(f"Registering to {domain} ...")
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = f"sip:{self.cfg['sip_user']}@{domain}"
            acc_cfg.regConfig.registrarUri = f"sip:{domain}"

            acc_cfg.sipConfig.proxies = pj.StringVector()
            acc_cfg.sipConfig.proxies.append(f"sip:{domain};lr")

            cred = pj.AuthCredInfo("digest", "*", self.cfg["sip_user"], 0, self.cfg["sip_password"])
            acc_cfg.sipConfig.authCreds.append(cred)

            self._registered = False
            acc = MyAccount(on_reg=lambda ok: setattr(self, "_registered", ok))
            acc.create(acc_cfg)

            for _ in range(20):
                if self._registered:
                    self.acc = acc
                    logger.info(f"Registration to {domain} OK")
                    return True
                time.sleep(0.2)

            logger.warning(f"Registration to {domain} failed")
            try:
                acc.delete()
            except Exception:
                pass

        return False

    def wait_for_call_connected(self, timeout=10):
        """Wait for the call to be connected."""
        start_time = time.time()
        while not self._call_connected and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return self._call_connected

    def hangup_call(self):
        """Hang up the active call."""
        if self.active_call:
            try:
                logger.info("Hanging up call via tool")
                self.active_call.hangup(pj.CallOpParam(True))
            except pj.Error as e:
                logger.error(f"Failed to hang up call: {e.info()}")

    def initialize(self):
        """Initialize the PJSUA2 library and register the account."""
        self._init_lib()
        # Wait for the library to be ready and registration to complete
        if not self._ready_event.wait(timeout=10):
            raise RuntimeError("PJSUA2 library failed to initialize")
        
        # Wait for registration to complete
        for _ in range(50):  # 5 seconds timeout
            if self._registered:
                logger.info("Account registered successfully")
                return
            time.sleep(0.1)
        
        raise RuntimeError("Registration failed on all servers")

    def dial(self, target_number: str, max_duration_sec: int = 3600):
        """Place a call and keep it up while the bridge runs."""
        # Initialize the call with lock
        with self.pj_lock:
            try:
                self._register_current_thread()
                acc_uri = self.acc.getInfo().uri
                domain = acc_uri.split("@", 1)[1].split(";", 1)[0]
                target_uri = f"sip:{target_number}@{domain}"
                logger.info(f"Dialing {target_uri}")

                self.active_call = MyCall(self, self.acc)
                prm = pj.CallOpParam(True)
                self.active_call.makeCall(target_uri, prm)
            except pj.Error as e:
                logger.error(f"Failed to make call: {e.info()}")
                raise

        # Wait for call to complete without holding the lock
        try:
            started = time.time()
            last_stats_time = time.time()
            while not self._call_done and (time.time() - started) < max_duration_sec:
                    # Debug logging every 5 seconds
                    if time.time() - last_stats_time > 5:
                        logger.debug(f"Call status: _call_done={self._call_done}, elapsed={(time.time() - started):.1f}s")
                    
                    # Process any pending audio playback
                    if self._pending_audio:
                        logger.debug(f"Pending audio: {self._pending_audio}, call_media: {self._call_media}")
                        if not self._call_media:
                            logger.warning("No call media available yet, cannot play audio")
                        else:
                            try:
                                wav_path = self._pending_audio
                                
                                # Amplify audio before playing if it's too quiet
                                with open(wav_path, 'rb') as f:
                                    header = f.read(44)  # Read WAV header
                                    audio_data = f.read()  # Read all audio data
                                    
                                if audio_data and len(audio_data) > 100:
                                    import struct
                                    samples = list(struct.unpack(f'{len(audio_data)//2}h', audio_data))
                                    max_sample = max(abs(s) for s in samples)
                                    
                                    # Always amplify to ensure clear audio
                                    if max_sample < 20000 and max_sample > 0:  # If not already loud
                                        # Calculate amplification factor (aim for peaks around 25000)
                                        amp_factor = min(25000 / max_sample, 5.0)  # Cap at 5x to avoid distortion
                                        logger.info(f"PRE-AMPLIFYING audio by {amp_factor:.1f}x (max_sample={max_sample})")
                                        
                                        # Amplify samples
                                        amplified = []
                                        for s in samples:
                                            new_s = int(s * amp_factor)
                                            # Clip to int16 range
                                            new_s = max(-32768, min(32767, new_s))
                                            amplified.append(new_s)
                                        
                                        # Write amplified audio back
                                        amplified_data = struct.pack(f'{len(amplified)}h', *amplified)
                                        with open(wav_path, 'wb') as f:
                                            f.write(header)
                                            f.write(amplified_data)
                                
                                player = pj.AudioMediaPlayer()
                                player.createPlayer(wav_path, 1)  # 1=no loop
                                
                                # Connect to conference bridge first
                                player_slot = player.getPortId()
                                logger.debug(f"Created player with slot {player_slot}")
                                
                                # Start transmitting to the call
                                player.startTransmit(self._call_media)
                                logger.debug("Started transmitting to call media")
                                
                                # Verify the player is connected
                                try:
                                    port_info = player.getPortInfo()
                                    logger.debug(f"Player port info: name={port_info.name}, format={port_info.format.clockRate}Hz")
                                    
                                    # Check if we're actually connected to the call
                                    call_port_info = self._call_media.getPortInfo()
                                    logger.debug(f"Call media port: name={call_port_info.name}, format={call_port_info.format.clockRate}Hz")
                                except Exception as e:
                                    logger.warning(f"Could not get port info: {e}")
                                
                                # Estimate duration
                                with wave.open(wav_path, "rb") as wf:
                                    frames = wf.getnframes()
                                    rate = wf.getframerate()
                                    duration = frames / float(rate)
                                
                                logger.info(f"Playing audio, duration={duration:.2f}s, size={os.path.getsize(wav_path)} bytes")
                                
                                # Wait for playback to complete to avoid overlapping audio
                                if duration > 0:
                                    logger.debug(f"Waiting {duration:.2f}s for playback to complete...")
                                    time.sleep(duration)
                                    logger.debug("Playback should be complete")
                                    
                                # Stop transmission and destroy player properly
                                player.stopTransmit(self._call_media)
                                pj.AudioMedia.typecastFromMedia(None)  # Force cleanup
                                
                                # Debug: Check if audio is silent and amplify if needed
                                with open(wav_path, 'rb') as f:
                                    header = f.read(44)  # Read WAV header
                                    audio_data = f.read()  # Read all audio data
                                    
                                if audio_data:
                                    # Check if all samples are near zero (silent)
                                    import struct
                                    samples = list(struct.unpack(f'{len(audio_data)//2}h', audio_data))
                                    max_sample = max(abs(s) for s in samples)
                                    avg_sample = sum(abs(s) for s in samples) / len(samples)
                                    logger.info(f"Audio analysis: max_sample={max_sample}, avg_sample={avg_sample:.1f}, samples={len(samples)}")
                                    
                                    # Amplify if too quiet
                                    if max_sample < 5000 and max_sample > 0:  # If max is less than ~15% of full scale
                                        # Calculate amplification factor (aim for peaks around 20000)
                                        amp_factor = min(20000 / max_sample, 10.0)  # Cap at 10x to avoid clipping
                                        logger.info(f"Amplifying audio by {amp_factor:.1f}x")
                                        
                                        # Amplify samples
                                        amplified = []
                                        for s in samples:
                                            new_s = int(s * amp_factor)
                                            # Clip to int16 range
                                            new_s = max(-32768, min(32767, new_s))
                                            amplified.append(new_s)
                                        
                                        # Write amplified audio back
                                        amplified_data = struct.pack(f'{len(amplified)}h', *amplified)
                                        with open(wav_path, 'wb') as f:
                                            f.write(header)
                                            f.write(amplified_data)
                                        
                                        logger.debug(f"Amplified audio written back to {wav_path}")
                                
                                self._pending_audio = None
                            except Exception as e:
                                logger.error(f"Audio playback error: {e}")
                                self._pending_audio = None
                    
                    # Log call statistics every 5 seconds
                    if time.time() - last_stats_time > 5:
                        try:
                            ci = self.active_call.getInfo()
                            if ci.media:
                                for i, mi in enumerate(ci.media):
                                    if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                                        # Get stream statistics
                                        try:
                                            si = self.active_call.getStreamStat(i)
                                            logger.debug(f"RTP TX: packets={si.rtcp.tx.pkt}, bytes={si.rtcp.tx.bytes}, loss={si.rtcp.tx.loss}")
                                            logger.debug(f"RTP RX: packets={si.rtcp.rx.pkt}, bytes={si.rtcp.rx.bytes}, loss={si.rtcp.rx.loss}")
                                            
                                            # Get detailed stream info
                                            try:
                                                tx_stats = self.active_call.getStreamStat(i).rtcp.tx
                                                rx_stats = self.active_call.getStreamStat(i).rtcp.rx
                                                logger.debug(f"TX rate: {tx_stats.bytes * 8 / 5000:.1f} kbps")
                                                logger.debug(f"RX rate: {rx_stats.bytes * 8 / 5000:.1f} kbps")
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                            last_stats_time = time.time()
                        except Exception:
                            pass
                    
                    time.sleep(0.05)

            try:
                ci = self.active_call.getInfo()
                if ci.state != pj.PJSIP_INV_STATE_DISCONNECTED:
                    logger.info("Hanging up")
                    self.active_call.hangup(pj.CallOpParam(True))
            except Exception:
                pass

            return 0

        except pj.Error as e:
            logger.error(f"PJSUA2 Exception: {e.info()}")
            return 2
        finally:
            self._cleanup()

    def _cleanup(self):
        # Ensure the thread performing cleanup is registered with pjlib
        self._register_current_thread()
        with self.pj_lock:
            try:
                if self.active_call:
                    self.active_call.safe_stop()
                    self.active_call = None
            except Exception:
                pass
            try:
                if self.acc:
                    self.acc = None
            except Exception:
                pass

        # Signal the background thread to stop and wait for it to finish
        self._stop_event.set()
        if self._pj_thread:
            self._pj_thread.join()
            self._pj_thread = None
        logger.info("Stopped")
