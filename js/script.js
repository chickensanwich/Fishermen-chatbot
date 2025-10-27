// Global variables for DOM elements
let loginForm, signupForm, chatForm, feedbackForm;
let loginContainer, signupContainer, chatContainer, feedbackPopup, overlay;
let chatMessages, chatInput, chatHistory, newChatBtn, searchChats, userNameDisplay;
let languageSelect, micBtn, responseAudio;

// DOM Elements
document.addEventListener('DOMContentLoaded', () => {
    // Form elements
    loginForm = document.getElementById('login-form');
    signupForm = document.getElementById('signup-form');
    chatForm = document.getElementById('chat-form');
    feedbackForm = document.getElementById('feedback-form');
    
    // Container elements
    loginContainer = document.getElementById('login-container');
    signupContainer = document.getElementById('signup-container');
    chatContainer = document.getElementById('chat-container');
    feedbackPopup = document.getElementById('feedback-popup');
    overlay = document.getElementById('overlay');
    
    // Chat elements
    chatMessages = document.getElementById('chat-messages');
    chatInput = document.getElementById('chat-input');
    chatHistory = document.getElementById('chat-history');
    newChatBtn = document.getElementById('new-chat-btn');
    searchChats = document.getElementById('search-chats');
    userNameDisplay = document.getElementById('user-name-display');
    languageSelect = document.getElementById('language-select');
    micBtn = document.getElementById('mic-btn');
    responseAudio = document.getElementById('response-audio');
    
    // Initialize the application
    initApp();
    
    // Event Listeners
    if (loginForm) loginForm.addEventListener('submit', handleLogin);
    if (signupForm) signupForm.addEventListener('submit', handleSignup);
    if (chatForm) chatForm.addEventListener('submit', handleChatSubmit);
    if (feedbackForm) feedbackForm.addEventListener('submit', handleFeedbackSubmit);
    if (newChatBtn) newChatBtn.addEventListener('click', createNewChat);
    if (searchChats) searchChats.addEventListener('input', searchChatHistory);
    if (micBtn) micBtn.addEventListener('click', startSpeechRecognition);
    
    // Add event listener for closing feedback popup
    document.addEventListener('click', function(e) {
        if (e.target.matches('.btn-secondary') && e.target.textContent === 'Cancel') {
            closeFeedbackPopup();
        }
    });
    
    // Auto-resize textarea
    if (chatInput) {
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            chatInput.style.height = (chatInput.scrollHeight) + 'px';
        });
    }
});

// Initialize the application
function initApp() {
    // Check if user is logged in
    const currentUser = localStorage.getItem('currentUser');
    if (currentUser) {
        const user = JSON.parse(currentUser);
        showChatInterface(user);
        loadChatHistory();
    } else {
        showLogin();
    }
}

// Authentication Functions
function handleLogin(e) {
    e.preventDefault();
    
    const name = document.getElementById('login-name').value.trim();
    const fishermanId = document.getElementById('login-fisherman-id').value.trim();
    const password = document.getElementById('login-password').value.trim();
    
    if (!name || !fishermanId || !password) {
        alert("Please fill out all fields.");
        return;
    }
    
    // In a real application, you would validate credentials against a server
    // For this demo, we'll simulate a successful login
    const user = {
        name,
        fishermanId,
        location: 'Unknown' // In a real app, this would come from the server
    };
    
    // Save user to local storage
    localStorage.setItem('currentUser', JSON.stringify(user));
    
    // Show chat interface
    showChatInterface(user);
    appendSystemMessage(`Welcome back, ${name}! 👋`);
}

function handleSignup(e) {
    e.preventDefault();
    
    const name = document.getElementById('signup-name').value.trim();
    const fishermanId = document.getElementById('signup-fisherman-id').value.trim();
    const location = document.getElementById('signup-location').value.trim();
    const password = document.getElementById('signup-password').value.trim();
    const confirmPassword = document.getElementById('signup-confirm-password').value.trim();
    
    if (!name || !fishermanId || !location || !password || !confirmPassword) {
        alert("Please fill out all fields.");
        return;
    }
    
    // Validate passwords match
    if (password !== confirmPassword) {
        alert('Passwords do not match!');
        return;
    }
    
    // In a real application, you would send this data to a server
    // For this demo, we'll simulate a successful signup
    const user = {
        name,
        fishermanId,
        location
    };
    
    // Save user to local storage
    localStorage.setItem('currentUser', JSON.stringify(user));
    
    // Show chat interface
    showChatInterface(user);
    appendSystemMessage(`Welcome aboard, ${name}! 🎣`);
}

function logout() {
    // Clear user data
    localStorage.removeItem('currentUser');
    localStorage.removeItem('chatHistory');
    
    // Append system message (though chat is hidden, for consistency)
    appendSystemMessage("You have logged out successfully.");
    
    // Show login screen
    showLogin();
}

// UI Navigation Functions
function showLogin() {
    document.getElementById('login-container').classList.remove('hidden');
    document.getElementById('signup-container').classList.add('hidden');
    document.getElementById('chat-container').classList.add('hidden');
}

function showSignup() {
    document.getElementById('login-container').classList.add('hidden');
    document.getElementById('signup-container').classList.remove('hidden');
    document.getElementById('chat-container').classList.add('hidden');
}

function showChatInterface(user) {
    document.getElementById('login-container').classList.add('hidden');
    document.getElementById('signup-container').classList.add('hidden');
    document.getElementById('chat-container').classList.remove('hidden');
    
    // Update user name display
    document.getElementById('user-name-display').textContent = user.name;
}

// Chat Functions
async function handleChatSubmit(e) {
    e.preventDefault();
    
    const message = chatInput.value.trim();
    if (!message) return;
    
    // Add user message to chat
    addMessage(message, 'user');
    
    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';
    
    // Send message
    await sendMessage(message);
}

async function sendMessage(message) {
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });

        if (!response.ok) {
            throw new Error(`Server error ${response.status}`);
        }

        const data = await response.json();
        removeTypingIndicator();
        addMessage(data.reply, 'bot');
        
        // Handle audio response
        handleAudioResponse(data);
        
        // Save chat to history
        saveChatToHistory(message, data.reply);
    } catch (err) {
        console.error("Chatbot fetch error:", err);
        removeTypingIndicator();
        addMessage("⚠️ Couldn't reach the chatbot server. Please ensure it's running.", 'bot');
    }
}

function addMessage(content, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    
    const messageContent = document.createElement('div');
    messageContent.classList.add('message-content');
    messageContent.textContent = content;
    
    messageDiv.appendChild(messageContent);
    
    const timestampSpan = document.createElement('span');
    timestampSpan.classList.add('timestamp');
    timestampSpan.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    messageDiv.appendChild(timestampSpan);
    
    // Add feedback buttons for bot messages
    if (sender === 'bot') {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.classList.add('message-feedback');
        
        const thumbsUpBtn = document.createElement('button');
        thumbsUpBtn.classList.add('feedback-btn', 'thumbs-up');
        thumbsUpBtn.innerHTML = '<i class="fas fa-thumbs-up"></i>';
        thumbsUpBtn.addEventListener('click', () => handleFeedback(messageDiv, true));
        
        const thumbsDownBtn = document.createElement('button');
        thumbsDownBtn.classList.add('feedback-btn', 'thumbs-down');
        thumbsDownBtn.innerHTML = '<i class="fas fa-thumbs-down"></i>';
        thumbsDownBtn.addEventListener('click', () => handleFeedback(messageDiv, false));
        
        feedbackDiv.appendChild(thumbsUpBtn);
        feedbackDiv.appendChild(thumbsDownBtn);
        messageDiv.appendChild(feedbackDiv);
    }
    
    chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.classList.add('message', 'bot-message', 'typing-indicator');
    
    const typingContent = document.createElement('div');
    typingContent.classList.add('message-content');
    typingContent.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    
    typingDiv.appendChild(typingContent);
    chatMessages.appendChild(typingDiv);
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const typingIndicator = document.querySelector('.typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Speech Recognition (STT)
let recognition;
function startSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Speech Recognition not supported in this browser.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = languageSelect.value;
    recognition.interimResults = false;

    recognition.onresult = async (event) => {
        const transcript = event.results[0][0].transcript;
        addMessage(transcript, 'user');
        await sendMessage(transcript);
    };

    recognition.onerror = (event) => {
        console.error("Speech Recognition Error:", event.error);
        alert("Error with speech recognition: " + event.error);
    };

    recognition.start();
}

// Text-to-Speech (TTS) for English
function speak(text, lang) {
    if (!("speechSynthesis" in window)) {
        console.warn("Speech Synthesis not supported in this browser.");
        return;
    }

    const synth = window.speechSynthesis;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1;

    // Wait for voices
    let voices = synth.getVoices();
    if (voices.length === 0) {
        synth.onvoiceschanged = () => speak(text, lang);
        return;
    }

    const matchVoice = voices.find(v => v.lang.startsWith(lang.split('-')[0])) || voices[0];
    utterance.voice = matchVoice;

    synth.cancel(); // Cancel any ongoing speech
    synth.speak(utterance);
}

// Handle Audio Response from Server
function handleAudioResponse(data) {
    if (data.audio_url) {
        // For Bengali: Play server-generated audio
        responseAudio.src = data.audio_url;
        responseAudio.load();
        responseAudio.play().catch(err => console.warn("Autoplay blocked:", err));
    } else if (data.lang === "en") {
        // For English: Use browser TTS
        speak(data.reply, languageSelect.value);
    }
}

// Feedback Functions
function handleFeedback(messageDiv, isPositive) {
    const thumbsUp = messageDiv.querySelector('.thumbs-up');
    const thumbsDown = messageDiv.querySelector('.thumbs-down');
    
    // Reset both buttons
    thumbsUp.classList.remove('active', 'thumbs-up-animation');
    thumbsDown.classList.remove('active', 'thumbs-down-animation');
    
    if (isPositive) {
        // Thumbs up was clicked
        thumbsUp.classList.add('active', 'thumbs-up-animation');
        thumbsUp.style.color = 'var(--secondary-color)';
    } else {
        // Thumbs down was clicked
        thumbsDown.classList.add('active', 'thumbs-down-animation');
        thumbsDown.style.color = 'var(--danger-color)';
        
        // Show feedback popup
        showFeedbackPopup(messageDiv.querySelector('.message-content').textContent);
    }
}

function showFeedbackPopup(message) {
    // Store the message being reported
    feedbackPopup.dataset.reportedMessage = message;
    
    // Show popup and overlay
    feedbackPopup.classList.remove('hidden');
    overlay.classList.remove('hidden');
}

function closeFeedbackPopup() {
    // Hide popup and overlay
    feedbackPopup.classList.add('hidden');
    overlay.classList.add('hidden');
    
    // Reset form
    document.getElementById('feedback-form').reset();
}

function handleFeedbackSubmit(e) {
    e.preventDefault();
    
    // Get selected feedback option
    const feedbackOption = document.querySelector('input[name="feedback"]:checked');
    const feedbackText = document.getElementById('feedback-text').value;
    const reportedMessage = feedbackPopup.dataset.reportedMessage;
    
    // In a real application, you would send this feedback to a server
    console.log('Feedback submitted:', {
        message: reportedMessage,
        reason: feedbackOption ? feedbackOption.value : 'not specified',
        additionalComments: feedbackText
    });
    
    // Close popup
    closeFeedbackPopup();
    
    // Show thank you message
    alert('Thank you for your feedback!');
}

// Chat History Functions
function createNewChat() {
    // Clear current chat
    chatMessages.innerHTML = '';
    
    // Add welcome message
    const welcomeDiv = document.createElement('div');
    welcomeDiv.classList.add('welcome-message');
    welcomeDiv.innerHTML = '<h1>Welcome to FisherMen Chatbot</h1><p>How can I assist you today?</p>';
    chatMessages.appendChild(welcomeDiv);
    
    // Add new chat to history
    const chatId = 'chat_' + Date.now();
    const newChat = {
        id: chatId,
        title: 'New Chat',
        timestamp: Date.now(),
        messages: []
    };
    
    // Save to local storage
    const chatHistory = getChatHistory();
    chatHistory.unshift(newChat);
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory));
    
    // Update chat history UI
    updateChatHistoryUI();
}

function saveChatToHistory(userMessage, botResponse) {
    let chatHistory = getChatHistory();
    
    // If no chats exist, create a new one
    if (chatHistory.length === 0) {
        createNewChat();
        chatHistory = getChatHistory();
    }
    
    // Add messages to the most recent chat
    const currentChat = chatHistory[0];
    currentChat.messages.push(
        { sender: 'user', content: userMessage },
        { sender: 'bot', content: botResponse }
    );
    
    // Update chat title based on first user message if it's still "New Chat"
    if (currentChat.title === 'New Chat' && currentChat.messages.length === 2) {
        currentChat.title = userMessage.substring(0, 30) + (userMessage.length > 30 ? '...' : '');
    }
    
    // Save to local storage
    localStorage.setItem('chatHistory', JSON.stringify(chatHistory));
    
    // Update chat history UI
    updateChatHistoryUI();
}

function loadChatHistory() {
    const chatHistory = getChatHistory();
    
    if (chatHistory.length === 0) {
        // If no chat history, create a new chat
        createNewChat();
    } else {
        // Load the most recent chat
        loadChat(chatHistory[0]);
        
        // Update chat history UI
        updateChatHistoryUI();
    }
}

function loadChat(chat) {
    // Clear current chat
    chatMessages.innerHTML = '';
    
    // Load messages
    if (chat.messages && chat.messages.length > 0) {
        chat.messages.forEach(message => {
            addMessage(message.content, message.sender);
        });
    } else {
        // Add welcome message if no messages
        const welcomeDiv = document.createElement('div');
        welcomeDiv.classList.add('welcome-message');
        welcomeDiv.innerHTML = '<h1>Welcome to FisherMen Chatbot</h1><p>How can I assist you today?</p>';
        chatMessages.appendChild(welcomeDiv);
    }
}

function updateChatHistoryUI() {
    const chatHistory = getChatHistory();
    chatHistory.sort((a, b) => b.timestamp - a.timestamp);
    
    // Clear current history
    document.getElementById('chat-history').innerHTML = '';
    
    // Add each chat to the sidebar
    chatHistory.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.classList.add('chat-item');
        chatItem.dataset.chatId = chat.id;
        
        chatItem.innerHTML = `
            <i class="fas fa-comment"></i>
            <div class="chat-item-title">${chat.title}</div>
        `;
        
        chatItem.addEventListener('click', () => {
            // Load this chat
            loadChat(chat);
            
            // Update active state
            document.querySelectorAll('.chat-item').forEach(item => {
                item.classList.remove('active');
            });
            chatItem.classList.add('active');
        });
        
        document.getElementById('chat-history').appendChild(chatItem);
    });
    
    // Set first chat as active
    if (chatHistory.length > 0) {
        document.querySelector('.chat-item').classList.add('active');
    }
}

function searchChatHistory() {
    const searchTerm = document.getElementById('search-chats').value.toLowerCase();
    const chatHistory = getChatHistory();
    
    // Filter chats based on search term
    const filteredChats = chatHistory.filter(chat => 
        chat.title.toLowerCase().includes(searchTerm) || 
        chat.messages.some(msg => msg.content.toLowerCase().includes(searchTerm))
    );
    
    // Clear current history
    document.getElementById('chat-history').innerHTML = '';
    
    // Add filtered chats to the sidebar
    filteredChats.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.classList.add('chat-item');
        chatItem.dataset.chatId = chat.id;
        
        chatItem.innerHTML = `
            <i class="fas fa-comment"></i>
            <div class="chat-item-title">${chat.title}</div>
        `;
        
        chatItem.addEventListener('click', () => {
            // Load this chat
            loadChat(chat);
            
            // Update active state
            document.querySelectorAll('.chat-item').forEach(item => {
                item.classList.remove('active');
            });
            chatItem.classList.add('active');
        });
        
        document.getElementById('chat-history').appendChild(chatItem);
    });
}

function getChatHistory() {
    const chatHistory = localStorage.getItem('chatHistory');
    return chatHistory ? JSON.parse(chatHistory) : [];
}

// Utility Functions
function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    const icon = input.nextElementSibling.querySelector('i');
    
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

function appendSystemMessage(text) {
    const sysMsg = document.createElement("div");
    sysMsg.classList.add("system-message");
    sysMsg.textContent = text;
    chatMessages.appendChild(sysMsg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Helper Functions for Window
window.togglePasswordVisibility = togglePasswordVisibility;
window.showSignup = showSignup;
window.showLogin = showLogin;
window.logout = logout;