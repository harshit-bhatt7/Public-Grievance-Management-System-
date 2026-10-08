import { useRef, useState } from "react";

export default function VoiceComplaintButton({ onTranscript }) {
  const recognitionRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState("");

  function start() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setMessage("Browser speech recognition is not available. You can type the complaint normally.");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const text = event.results?.[0]?.[0]?.transcript || "";
      if (text) onTranscript(text);
      setMessage("Please review the transcription before submitting.");
      setRecording(false);
    };
    recognition.onerror = () => { setRecording(false); setMessage("Speech recognition failed. Please type the complaint instead."); };
    recognition.onend = () => setRecording(false);
    recognitionRef.current = recognition;
    recognition.start();
    setRecording(true);
    setMessage("Listening…");
  }

  function stop() { recognitionRef.current?.stop(); setRecording(false); }

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <button type="button" className="btn-link" onClick={recording ? stop : start}>
        {recording ? "Stop voice input" : "Use voice complaint"}
      </button>
      {message && <small style={{ display: "block", marginTop: "0.25rem" }}>{message}</small>}
    </div>
  );
}
