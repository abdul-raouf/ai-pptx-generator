const API = '/api/v1';
let jobId = null;
let eventSource = null;

const chatWindow = document.getElementById('chat-window');
const userInput  = document.getElementById('user-input');
const sendBtn    = document.getElementById('send-btn');

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `message ${role}`;

  // Render download links if present
  const urlPattern = /(\/api\/v1\/jobs\/[^\s]+\/download)/g;
  if (role === 'assistant' && urlPattern.test(text)) {
    div.innerHTML = text.replace(urlPattern, '<a href="$1" target="_blank">Download your PPTX</a>');
  } else {
    div.textContent = text;
  }

  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addStatus(text) {
  const div = document.createElement('div');
  div.className = 'message status';
  div.textContent = text;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setLoading(loading) {
  sendBtn.disabled = loading;
  userInput.disabled = loading;
}

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text) return;

  addMessage('user', text);
  userInput.value = '';
  setLoading(true);

  try {
    let res, data;

    if (!jobId) {
      // First message — start a new job
      res = await fetch(`${API}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      data = await res.json();
      jobId = data.job_id;
      addMessage('assistant', data.reply);

      // If job is now generating, open SSE stream
      if (data.stage === 'storyboard_generation') {
        openStream();
      } else {
        setLoading(false);
      }

    } else {
      // Subsequent messages
      res = await fetch(`${API}/jobs/${jobId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      data = await res.json();
      addMessage('assistant', data.reply);

      if (
        data.stage === 'storyboard_generation' ||
        data.stage === 'storyboard_verification' ||
        data.stage === 'pptx_generation'
      ) {
        openStream();
      } else {
        setLoading(false);
      }
    }

  } catch (err) {
    addMessage('assistant', 'Something went wrong. Please try again.');
    setLoading(false);
  }
}

function openStream() {
  if (eventSource) eventSource.close();

  addStatus('Generating your presentation...');

  eventSource = new EventSource(`${API}/jobs/${jobId}/stream`);

  eventSource.onmessage = (e) => {
    const payload = JSON.parse(e.data);

    if (payload.type === 'ping') return;

    if (payload.type === 'complete') {
      eventSource.close();
      addMessage('assistant', `Your presentation is ready — ${payload.message}\n\n${payload.download_url}`);
      setLoading(false);
      jobId = null; // Reset for a new conversation
    }

    if (payload.type === 'error') {
      eventSource.close();
      addMessage('assistant', `Something went wrong: ${payload.message}`);
      setLoading(false);
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    addMessage('assistant', 'Lost connection. Please refresh and try again.');
    setLoading(false);
  };
}

// Send on button click
sendBtn.addEventListener('click', sendMessage);

// Send on Enter (Shift+Enter for new line)
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});