# Import necessary modules
import eel  # For the frontend communication with the Python backend
import speech_recognition as sr  # For speech recognition
from openai import OpenAI  # For interacting with OpenAI's GPT model
import threading  # For handling concurrent tasks
import json  # For handling JSON data
import os  # For interacting with the file system
import base64  # For encoding audio responses into base64
import time  # For time-related tasks like sleep and cooldown
import re  # For regular expressions (used to check if a string is a question)

# Initialize eel (web interface)
eel.init('web')

class AudioAssistant:
    def __init__(self):
        # Initialize the assistant's parameters and set up the audio system
        self.setup_audio()
        self.is_listening = False  # Flag indicating whether the assistant is listening
        self.client = None  # OpenAI client, initially None
        self.api_key = None  # The API key for OpenAI, initially None
        self.tts_enabled = True  # Set text-to-speech as enabled by default
        self.is_speaking = False  # Flag indicating whether the assistant is speaking
        self.audio_playing = False  # Flag indicating whether audio is being played
        self.load_api_key()  # Attempt to load an API key from config.json

    def setup_audio(self):
        # Set up the microphone and recognizer for speech input
        self.recognizer = sr.Recognizer()  # Create a recognizer object
        self.mic = sr.Microphone()  # Create a microphone object
        with self.mic as source:
            # Adjust the recognizer for ambient noise in the environment
            self.recognizer.adjust_for_ambient_noise(source)

    def load_api_key(self):
        # Load the API key from a config file if it exists
        if os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                config = json.load(f)  # Load the configuration from the file
                self.set_api_key(config.get('api_key'))  # Set the API key if found

    def set_api_key(self, api_key):
        # Set the API key for OpenAI and store it in a configuration file
        self.api_key = api_key
        self.client = OpenAI(api_key=self.api_key)  # Initialize OpenAI client
        with open('config.json', 'w') as f:
            json.dump({'api_key': api_key}, f)  # Save the API key to config.json

    def delete_api_key(self):
        # Delete the stored API key and remove the configuration file
        self.api_key = None
        self.client = None
        if os.path.exists('config.json'):
            os.remove('config.json')  # Delete the configuration file

    def has_api_key(self):
        # Check if the API key exists
        return self.api_key is not None

    def toggle_listening(self):
        # Toggle the listening state (start or stop listening)
        if not self.client:
            return False  # If there's no client, return False
        self.is_listening = not self.is_listening  # Toggle the listening flag
        if self.is_listening:
            # Start listening in a separate thread
            threading.Thread(target=self.listen_and_process, daemon=True).start()
        return self.is_listening

    def listen_and_process(self):
        # Main loop for listening to audio and processing the input
        cooldown_time = 2  # Cooldown period in seconds between speech
        last_speak_time = 0  # Track the last time the assistant spoke
        
        while self.is_listening:
            current_time = time.time()  # Get the current time
            if not self.is_speaking and not self.audio_playing and (current_time - last_speak_time) > cooldown_time:
                try:
                    # Listen for audio input from the microphone
                    with self.mic as source:
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                    # Convert audio to text using Google Speech Recognition
                    text = self.recognizer.recognize_google(audio)
                    if self.is_question(text):  # Check if the text is a question
                        # Capitalize the first letter and ensure it ends with a question mark
                        capitalized_text = text[0].upper() + text[1:]
                        if not capitalized_text.endswith('?'):
                            capitalized_text += '?'
                        eel.update_ui(f"Q: {capitalized_text}", "")  # Update UI with the question
                        self.is_speaking = True
                        response = self.get_ai_response(capitalized_text)  # Get AI's response
                        eel.update_ui("", f"{response}")  # Update UI with the AI response
                        self.is_speaking = False
                        last_speak_time = time.time()  # Update the last speak time
                except sr.WaitTimeoutError:
                    pass  # Handle timeout error
                except sr.UnknownValueError:
                    pass  # Handle unrecognized speech
                except Exception as e:
                    eel.update_ui(f"An error occurred: {str(e)}", "")  # Handle general errors
            else:
                time.sleep(0.1)  # Short sleep to prevent busy waiting

    def is_question(self, text):
        # Check if the text is a question
        text = text.lower().strip()  # Convert to lowercase and remove extra spaces
        
        # List of question words and phrases
        question_starters = [
            "what", "why", "how", "when", "where", "who", "which",
            "can", "could", "would", "should", "is", "are", "do", "does",
            "am", "was", "were", "have", "has", "had", "will", "shall"
        ]
        
        # Check if the text starts with a question word
        if any(text.startswith(starter) for starter in question_starters):
            return True
        
        # Check for a question mark at the end
        if text.endswith('?'):
            return True
        
        # Check for inverted word order (e.g., "Are you...?", "Can we...?")
        if re.match(r'^(are|can|could|do|does|have|has|will|shall|should|would|am|is)\s', text):
            return True
        
        # Check for specific phrases that indicate a question
        question_phrases = [
            "tell me about", "i'd like to know", "can you explain",
            "i was wondering", "do you know", "what about", "how about"
        ]
        if any(phrase in text for phrase in question_phrases):
            return True
        
        # If none of the above conditions are met, it's probably not a question
        return False

    def get_ai_response(self, question):
        # Send the question to the OpenAI model and get the response
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Use GPT-3.5 model
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},  # Set system message
                    {"role": "user", "content": question}  # Send the user's question
                ]
            )
            # Extract the response text
            text_response = response.choices[0].message.content.strip()
            
            # If text-to-speech is enabled, generate speech from the text
            if self.tts_enabled:
                speech_response = self.client.audio.speech.create(
                    model="tts-1",  # Use the text-to-speech model
                    voice="alloy",  # Set the voice model
                    input=text_response  # Provide the text to convert to speech
                )
                
                # Encode the speech in base64 and return both text and audio
                audio_base64 = base64.b64encode(speech_response.content).decode('utf-8')
                return json.dumps({"text": text_response, "audio": audio_base64})
            
            # If TTS is not enabled, only return the text
            return json.dumps({"text": text_response, "audio": None})
        except Exception as e:
            print(f"Error in get_ai_response: {str(e)}")  # Debugging line
            return json.dumps({"text": f"Error getting AI response: {str(e)}", "audio": None})

# Initialize the AudioAssistant class
assistant = AudioAssistant()

# Expose functions to the front-end via eel
@eel.expose
def toggle_listening():
    return assistant.toggle_listening()

@eel.expose
def save_api_key(api_key):
    try:
        assistant.set_api_key(api_key)  # Save the API key
        return True
    except Exception as e:
        print(f"Error saving API key: {str(e)}")  # Error handling
        return False

@eel.expose
def delete_api_key():
    try:
        assistant.delete_api_key()  # Delete the API key
        return True
    except Exception as e:
        print(f"Error deleting API key: {str(e)}")  # Error handling
        return False

@eel.expose
def has_api_key():
    return assistant.has_api_key()  # Check if an API key is set

@eel.expose
def toggle_tts():
    assistant.tts_enabled = not assistant.tts_enabled  # Toggle text-to-speech state
    return assistant.tts_enabled

@eel.expose
def speaking_ended():
    assistant.is_speaking = False  # Indicate that speaking has ended

@eel.expose
def audio_playback_started():
    assistant.audio_playing = True  # Indicate that audio playback has started

@eel.expose
def audio_playback_ended():
    assistant.audio_playing = False  # Indicate that audio playback has ended
    assistant.is_speaking = False  # Reset speaking state

# Start the eel web interface
eel.start('index.html', size=(960, 840))
