# main.py
import os
from voip.voip_client import VoipClient
from voip.gemini_voip_adapter import GeminiVoipAdapter
import logging

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

if __name__ == "__main__":
    cfg = {
        'primary_domain': os.getenv("ZOHO_PRIMARY_DOMAIN"),
        'fallback_domain': os.getenv("ZOHO_FALLBACK_DOMAIN"),
        'sip_user': os.getenv("ZOHO_SIP_USER"),
        'sip_password': os.getenv("ZOHO_SIP_PASSWORD"),
        'user_agent': "Python PJSUA2"
    }

    target = os.getenv("TARGET_NUMBER")
    if not (cfg["sip_user"] and cfg["sip_password"] and target):
        raise SystemExit("Set ZOHO_PRIMARY_DOMAIN, ZOHO_FALLBACK_DOMAIN, ZOHO_SIP_USER, ZOHO_SIP_PASSWORD, and TARGET_NUMBER in environment.")

    rx_fifo = os.getenv("RX_FIFO", "/tmp/sip_rx.wav")
    initial_message = os.getenv("GEM_INITIAL_MSG", None)
    gem_out_rate = int(os.getenv("GEM_OUT_RATE", "24000"))  # Gemini -> SIP
    gem_in_rate  = int(os.getenv("GEM_IN_RATE",  "16000"))  # SIP -> Gemini
    call_context = "This is a test call to verify the new logging and audio quality improvements."

    # Start VoIP client (no startup tone; pure bridge)
    client = VoipClient(
        cfg,
        test_mode="tone",
        tone_seconds=0,     # 0 disables the connect-tone
        tone_freq=440.0
    )

    # Bridge Gemini Live <-> SIP
    bridge = GeminiVoipAdapter(
        voip_client=client,
        target_number=target,
        rx_fifo_path=rx_fifo,
        gem_out_rate=gem_out_rate,
        gem_in_rate=gem_in_rate,
        initial_message=initial_message,
        max_session_minutes=int(os.getenv("GEM_SESSION_MINUTES", "14")),
        call_context=call_context,
    )

    bridge.start()
