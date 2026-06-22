import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  Check,
  ExternalLink,
  FileText,
  Globe,
  Info,
  KeyRound,
  Languages,
  ListChecks,
  Mic,
  MessageSquare,
  Radio,
  Sparkles,
  Upload,
  Volume2,
  X,
} from 'lucide-react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import CodeBlock from '../components/CodeBlock';

interface Section {
  id: string;
  label: string;
  part?: string;
}

const sections: Section[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'language-support', label: 'Language Support' },
  { id: 'authentication', label: 'Authentication', part: 'Part 1' },
  { id: 'translation', label: 'Translation', part: 'Part 2' },
  { id: 'speech-to-text', label: 'Speech-to-Text', part: 'Part 3' },
  { id: 'language-detection', label: 'Language Detection', part: 'Part 4' },
  { id: 'text-to-speech', label: 'Text-to-Speech', part: 'Part 5' },
  { id: 'conversational-ai', label: 'Conversational AI', part: 'Part 6' },
  { id: 'file-upload', label: 'File Upload', part: 'Part 7' },
  { id: 'resources', label: 'Resources' },
];

const supportedLanguages = [
  { name: 'English', code: 'eng' },
  { name: 'Acholi', code: 'ach' },
  { name: 'Ateso', code: 'teo' },
  { name: 'Luganda', code: 'lug' },
  { name: 'Lugbara', code: 'lgg' },
  { name: 'Runyankole', code: 'nyn' },
  { name: 'Swahili', code: 'swa' },
];

interface LanguageSupportRow {
  name: string;
  code: string;
  speech: boolean; // /tasks/audio/speech (orpheus-3b-tts)
  transcription: boolean; // /tasks/audio/transcriptions (Whisper language IDs)
  chat: boolean; // /tasks/chat/completions (Sunflower) — same set as /tasks/translate
  ttsVoiceless?: boolean; // covered by the TTS training mix but no voice IDs yet
}

// Union of every language served by at least one of the three endpoints, sorted
// by name. Languages outside these sets (e.g. Zulu) are intentionally omitted.
const languageSupport: LanguageSupportRow[] = [
  { name: 'Acholi', code: 'ach', speech: true, transcription: true, chat: true },
  { name: 'Afrikaans', code: 'afr', speech: true, transcription: false, chat: false },
  { name: 'Alur', code: 'alz', speech: false, transcription: false, chat: true },
  { name: 'Aringa', code: 'luc', speech: false, transcription: false, chat: true },
  { name: 'Ateso', code: 'teo', speech: true, transcription: true, chat: true },
  { name: 'Bari', code: 'bfa', speech: false, transcription: false, chat: true },
  { name: 'English', code: 'eng', speech: true, transcription: true, chat: true },
  { name: 'Ewe', code: 'ewe', speech: true, transcription: false, chat: false },
  { name: 'Fulah', code: 'ful', speech: true, transcription: false, chat: false },
  { name: 'Hausa', code: 'hau', speech: true, transcription: false, chat: false },
  { name: 'Igbo', code: 'ibo', speech: true, transcription: false, chat: false },
  { name: 'Jopadhola', code: 'adh', speech: false, transcription: false, chat: true },
  { name: 'Kakwa', code: 'keo', speech: false, transcription: false, chat: true },
  { name: 'Karamojong', code: 'kdj', speech: false, transcription: false, chat: true },
  { name: 'Kikuyu', code: 'kik', speech: true, transcription: false, chat: false },
  { name: 'Kinyarwanda', code: 'kin', speech: true, transcription: true, chat: true },
  { name: 'Kumam', code: 'kdi', speech: false, transcription: false, chat: true },
  { name: 'Kupsabiny', code: 'kpz', speech: false, transcription: false, chat: true },
  { name: 'Kwamba', code: 'rwm', speech: false, transcription: false, chat: true },
  { name: 'Lango', code: 'laj', speech: false, transcription: false, chat: true },
  { name: 'Lingala', code: 'lin', speech: true, transcription: false, chat: false },
  { name: 'Lubwisi', code: 'tlj', speech: false, transcription: false, chat: true },
  { name: 'Lugbara', code: 'lgg', speech: true, transcription: true, chat: true, ttsVoiceless: true },
  { name: 'Lugungu', code: 'rub', speech: false, transcription: false, chat: true },
  { name: 'Lugwere', code: 'gwr', speech: false, transcription: false, chat: true },
  { name: 'Luganda', code: 'lug', speech: true, transcription: true, chat: true },
  { name: 'Lumasaba', code: 'myx', speech: false, transcription: true, chat: true },
  { name: 'Lunyole', code: 'nuj', speech: false, transcription: false, chat: true },
  { name: 'Luo (Dholuo)', code: 'luo', speech: true, transcription: false, chat: false },
  { name: 'Lusoga', code: 'xog', speech: false, transcription: true, chat: true },
  { name: "Ma'di", code: 'mhi', speech: false, transcription: false, chat: true },
  { name: 'Pokot', code: 'pok', speech: false, transcription: false, chat: true },
  { name: 'Rukiga', code: 'cgg', speech: false, transcription: false, chat: true },
  { name: 'Rukonjo', code: 'koo', speech: false, transcription: false, chat: true },
  { name: 'Runyankole', code: 'nyn', speech: true, transcription: true, chat: true },
  { name: 'Runyoro', code: 'nyo', speech: false, transcription: false, chat: true },
  { name: 'Ruruuli', code: 'ruc', speech: false, transcription: false, chat: true },
  { name: 'Rutooro', code: 'ttj', speech: false, transcription: true, chat: true },
  { name: 'Samia', code: 'lsm', speech: false, transcription: false, chat: true },
  { name: 'Sesotho', code: 'sot', speech: true, transcription: false, chat: false, ttsVoiceless: true },
  { name: 'Setswana', code: 'tsn', speech: true, transcription: false, chat: false, ttsVoiceless: true },
  { name: 'Swahili', code: 'swa', speech: true, transcription: true, chat: true },
  { name: 'Xhosa', code: 'xho', speech: true, transcription: false, chat: false },
  { name: 'Yoruba', code: 'yor', speech: true, transcription: false, chat: false },
];

const sttLanguages = [
  { code: 'eng', name: 'English (Ugandan)' },
  { code: 'swa', name: 'Swahili' },
  { code: 'ach', name: 'Acholi' },
  { code: 'lgg', name: 'Lugbara' },
  { code: 'lug', name: 'Luganda' },
  { code: 'nyn', name: 'Runyankole' },
  { code: 'teo', name: 'Ateso' },
  { code: 'xog', name: 'Lusoga' },
  { code: 'ttj', name: 'Rutooro' },
  { code: 'kin', name: 'Kinyarwanda' },
  { code: 'myx', name: 'Lumasaba' },
];

// orpheus-3b-tts languages covered. Speaker IDs encode both the source corpus
// (salt_*, waxal_*, slr32_*, slr129_*, bateesa_*) and the language. An empty
// speakers list means the language is in the training mix but exposes no
// individual voice IDs in this checkpoint (rendered as an em dash).
const orpheusLanguages = [
  {
    config: 'ach',
    language: 'Acholi',
    iso: '—',
    region: 'Uganda, South Sudan',
    speakers: ['salt_ach_0001', 'waxal_ach_0001', 'waxal_ach_0005', 'waxal_ach_0006', 'waxal_ach_0008'],
  },
  { config: 'afr', language: 'Afrikaans', iso: 'af', region: 'South Africa, Namibia', speakers: ['slr32_afr_0009'] },
  {
    config: 'eng',
    language: 'English',
    iso: 'en',
    region: '(control language)',
    speakers: ['salt_eng_0001', 'salt_eng_0002', 'salt_eng_0003'],
  },
  { config: 'ewe', language: 'Ewe', iso: 'ee', region: 'Ghana, Togo', speakers: ['slr129_ewe_0001'] },
  {
    config: 'ful',
    language: 'Fulah',
    iso: 'ff',
    region: 'West Africa (Sahel)',
    speakers: ['waxal_ful_0003', 'waxal_ful_0004', 'waxal_ful_0006'],
  },
  {
    config: 'hau',
    language: 'Hausa',
    iso: 'ha',
    region: 'Nigeria, Niger, Chad',
    speakers: ['waxal_hau_0004', 'waxal_hau_0006', 'waxal_hau_0007', 'waxal_hau_0008'],
  },
  {
    config: 'ibo',
    language: 'Igbo',
    iso: 'ig',
    region: 'Nigeria',
    speakers: ['waxal_ibo_0003', 'waxal_ibo_0005', 'waxal_ibo_0008'],
  },
  { config: 'kik', language: 'Kikuyu', iso: 'ki', region: 'Kenya', speakers: ['waxal_kik_0003', 'waxal_kik_0004'] },
  { config: 'kin', language: 'Kinyarwanda', iso: 'rw', region: 'Rwanda', speakers: ['bateesa_kin_0001'] },
  { config: 'lgg', language: 'Lugbara', iso: '—', region: 'Uganda, DRC', speakers: [] },
  { config: 'lin', language: 'Lingala', iso: 'ln', region: 'DRC, Republic of Congo', speakers: ['slr129_lin_0001'] },
  {
    config: 'lug',
    language: 'Luganda',
    iso: 'lg',
    region: 'Uganda',
    speakers: [
      'salt_lug_0001',
      'waxal_lug_0002',
      'waxal_lug_0003',
      'waxal_lug_0004',
      'waxal_lug_0005',
      'waxal_lug_0006',
      'waxal_lug_0007',
      'waxal_lug_0008',
    ],
  },
  {
    config: 'luo',
    language: 'Luo (Dholuo)',
    iso: '—',
    region: 'Kenya, Tanzania',
    speakers: ['waxal_luo_0001', 'waxal_luo_0002', 'waxal_luo_0003', 'waxal_luo_0004'],
  },
  {
    config: 'nyn',
    language: 'Runyankole',
    iso: '—',
    region: 'Uganda',
    speakers: ['salt_nyn_0001', 'waxal_nyn_0003', 'waxal_nyn_0004', 'waxal_nyn_0007', 'waxal_nyn_0008'],
  },
  { config: 'sot', language: 'Sesotho', iso: 'st', region: 'Lesotho, South Africa', speakers: [] },
  { config: 'swa', language: 'Swahili', iso: 'sw', region: 'East Africa', speakers: ['waxal_swa_0006', 'waxal_swa_0007'] },
  { config: 'teo', language: 'Ateso', iso: '—', region: 'Uganda, Kenya', speakers: ['salt_teo_0001'] },
  { config: 'tsn', language: 'Setswana', iso: 'tn', region: 'Botswana, South Africa', speakers: [] },
  { config: 'xho', language: 'Xhosa', iso: 'xh', region: 'South Africa', speakers: ['slr32_xho_0012'] },
  {
    config: 'yor',
    language: 'Yoruba',
    iso: 'yo',
    region: 'Nigeria, Benin',
    speakers: ['waxal_yor_0002', 'waxal_yor_0006', 'waxal_yor_0008'],
  },
];

const sparkVoices = [
  { name: 'acholi_female', id: 241, description: 'Acholi (female)' },
  { name: 'ateso_female', id: 242, description: 'Ateso (female)' },
  { name: 'runyankore_female', id: 243, description: 'Runyankore (female)' },
  { name: 'lugbara_female', id: 245, description: 'Lugbara (female)' },
  { name: 'swahili_male', id: 246, description: 'Swahili (male)' },
  { name: 'luganda_female', id: 248, description: 'Luganda (female)' },
];

const responseModes = [
  { mode: 'url', description: 'Generate audio, upload to GCP, return a signed URL (valid ~30 minutes) — default' },
  { mode: 'stream', description: 'Stream raw audio chunks directly' },
  { mode: 'both', description: 'Stream audio and return a final signed URL' },
];

const uploadFeatures = [
  'Temporary signed URLs (valid for 30 minutes)',
  'Direct upload to Google Cloud Storage',
  'Path traversal protection',
  'Support for multiple content types',
];

const registerCode = `import requests

url = "https://api.sunbird.ai/auth/register"
data = {
    "username": "your_username",
    "email": "your_email@example.com",
    "password": "your_secure_password"
}

response = requests.post(url, json=data)
print(response.json())`;

const tokenCode = `import requests

url = "https://api.sunbird.ai/auth/token"
data = {
    "username": "your_username",
    "password": "your_password"
}

response = requests.post(url, data=data)
token_data = response.json()
access_token = token_data["access_token"]
print(f"Your token: {access_token}")`;

const translateCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/translate"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

# Example: Translate from Luganda to English
data = {
    "source_language": "lug",
    "target_language": "eng",
    "text": "Ekibiina ekiddukanya omuzannyo gw'emisinde mu ggwanga ekya Uganda Athletics Federation kivuddeyo nekitegeeza nga lawundi esooka eyemisinde egisunsulamu abaddusi abanakiika mu mpaka ezenjawulo ebweru w'eggwanga egya National Athletics Trials nga bwegisaziddwamu.",
}

response = requests.post(url, headers=headers, json=data)
print(response.json())`;

const translateFullNameCode = `data = {
    "target_language": "Luganda",
    "text": "How are you?",
}

response = requests.post(url, headers=headers, json=data)
print(response.json())`;

const translationLanguageCodes = `language_codes = {
    "ach": "Acholi",
    "adh": "Jopadhola",
    "alz": "Alur",
    "bfa": "Bari",
    "cgg": "Rukiga",
    "eng": "English",
    "gwr": "Lugwere",
    "kdi": "Kumam",
    "kdj": "Karamojong",
    "keo": "Kakwa",
    "kin": "Kinyarwanda",
    "koo": "Rukonjo",
    "kpz": "Kupsabiny",
    "laj": "Lango",
    "lgg": "Lugbara",
    "lsm": "Samia",
    "luc": "Aringa",
    "lug": "Luganda",
    "mhi": "Ma'di",
    "myx": "Lumasaba",
    "nuj": "Lunyole",
    "nyn": "Runyankole",
    "nyo": "Runyoro",
    "pok": "Pokot",
    "rub": "Lugungu",
    "ruc": "Ruruuli",
    "rwm": "Kwamba",
    "swa": "Swahili",
    "teo": "Ateso",
    "tlj": "Lubwisi",
    "ttj": "Rutooro",
    "xog": "Lusoga",
}`;

const translateResponse = `{
    "id": "trans-1a2b3c...",
    "status": "COMPLETED",
    "output": {
        "translated_text": "Oli otya?",
        "source_language": "lug",
        "target_language": "eng"
    }
}`;

const modalTranscribeCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/audio/transcriptions"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

audio_file_path = "/path/to/audio_file.wav"

files = {
    "audio": ("recording.wav", open(audio_file_path, "rb"), "audio/wav"),
}
data = {
    "language": "lug",     # required: 3-letter code or full name (e.g. "Luganda")
    "platform": "modal",   # "modal" (default, Whisper) or "runpod"
}

response = requests.post(url, headers=headers, files=files, data=data)
result = response.json()
print(f"Transcription: {result['audio_transcription']}")`;

const runpodTranscribeCode = `files = {
    "audio": ("recording.mp3", open("/path/to/audio_file.mp3", "rb"), "audio/mpeg"),
}
data = {
    "language": "lug",
    "platform": "runpod",
    "adapter": "lug",             # optional; defaults to language
    "whisper": True,             # RunPod only
    "recognise_speakers": False,  # RunPod only — speaker diarization
}

response = requests.post(url, headers=headers, files=files, data=data)
print(response.json())`;

const transcribeResponse = `{
  "audio_transcription": "Ekibiina ekiddukanya ...",
  "language": "lug",
  "audio_url": "https://storage.googleapis.com/.../audio.wav?...",
  "audio_transcription_id": 123,
  "diarization_output": null,
  "formatted_diarization_output": null,
  "was_audio_trimmed": false,
  "original_duration_minutes": null
}`;

const saltWhisperCode = `SALT_LANGUAGE_IDS_WHISPER = {
    'eng': "English (Ugandan)",
    'swa': "Swahili",
    'ach': "Acholi",
    'lgg': "Lugbara",
    'lug': "Luganda",
    'nyn': "Runyankole",
    'teo': "Ateso",
    'xog': "Lusoga",
    'ttj': "Rutooro",
    'kin': "Kinyarwanda",
    'myx': "Lumasaba",
}`;

const languageDetectCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/language_id"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

text = "Oli otya? Webale nnyo ku kujja wano."

data = {"text": text}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(f"Detected language: {result}")`;

const orpheusTtsCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/audio/speech"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

payload = {
    "text": "I am a nurse who takes care of many people.",
    "model": "orpheus-3b-tts",   # default
    "voice": "salt_lug_0001",     # catalog tag; see GET /tasks/voice/speakers
    "language": "eng",            # required for orpheus-3b-tts (ISO code or full name)
}

response = requests.post(url, headers=headers, json=payload)
print(response.status_code)
print(response.json())`;

const sparkTtsCode = `payload = {
    "text": "I am a nurse who takes care of many people.",
    "model": "spark-tts",
    "voice": "luganda_female",   # voice name, or the numeric id as a string e.g. "248"
    "response_mode": "url",       # "url" (default), "stream", or "both"
}
response = requests.post(url, headers=headers, json=payload)
print(response.json())`;

const listVoicesCode = `auth = {"Authorization": f"Bearer {access_token}"}

# Orpheus voices grouped by language (default)
print(requests.get("https://api.sunbird.ai/tasks/voice/speakers", headers=auth).json())

# spark-tts fixed voices
print(requests.get(
    "https://api.sunbird.ai/tasks/voice/speakers",
    headers=auth,
    params={"model": "spark-tts"},
).json())`;

const batchTtsCode = `url = "https://api.sunbird.ai/tasks/audio/speech/batch"
payload = {
    "items": [
        {"text": "Good morning.", "voice": "salt_lug_0001"},
        {"text": "How are you?", "voice": "salt_eng_0001"},
    ]
}
response = requests.post(url, headers=headers, json=payload)
print(response.json())`;

const refreshUrlCode = `print(requests.get(
    "https://api.sunbird.ai/tasks/audio/speech/url",
    headers={"Authorization": f"Bearer {access_token}"},
    params={"gcs_object": "orpheus_tts/2026-06-03/abc.wav"},
).json())`;

const ttsResponse = `{
  "audio_url": "https://storage.googleapis.com/.../tts_audio/....wav?...",
  "model": "orpheus-3b-tts",
  "platform": "modal",
  "voice": "salt_lug_0001",
  "audio_url_expires_at": "2026-06-03T22:59:36.954061Z",
  "language": "lug",
  "sample_rate": 24000,
  "duration_seconds": 4.0,
  "gcs_object": "orpheus_tts/2026-06-03/....wav",
  "request_id": "0f1e2d3c4b5a...",
  "timings_ms": {"inference_ms": 1820.5, "upload_ms": 234.1, "total_ms": 2095.6}
}`;

const chatCompletionCode = `import requests

url = "https://api.sunbird.ai/tasks/chat/completions"

headers = {
    "accept": "application/json",
    "Authorization": "Bearer <your-access-token>",
    "Content-Type": "application/json",
}

payload = {
    "model": "Sunbird/Sunflower-14B",
    "messages": [
        {
            "role": "user",
            "content": "Good morning, what is the weather today?",
        }
    ],
    "temperature": 0.3,
}

response = requests.post(url, headers=headers, json=payload)

print(response.status_code)
print(response.json())`;

const chatCompletionResponse = `{
  "id": "chatcmpl-8f14e45fceea167a5a36dedd4bea2543",
  "object": "chat.completion",
  "created": 1718000000,
  "model": "Sunbird/Sunflower-14B",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "I'm glad you're up! While I can't provide real-time weather updates, I can help you understand weather forecasts or explain common weather patterns in Uganda."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 22,
    "completion_tokens": 47,
    "total_tokens": 69
  }
}`;

const openaiSdkCode = `from openai import OpenAI

client = OpenAI(
    api_key="<your-access-token>",
    base_url="https://api.sunbird.ai/tasks",
)

completion = client.chat.completions.create(
    model="Sunbird/Sunflower-14B",
    messages=[
        {
            "role": "user",
            "content": "translate from english to luganda: i am very hungry they should serve food in time",
        }
    ],
    temperature=0.1,
)

print(completion.choices[0].message.content)
# Ndi muyala nnyo, emmere erina okugabibwa mu budde.`;

const multiTurnCode = `payload = {
    "model": "Sunbird/Sunflower-14B",
    "messages": [
        {"role": "system", "content": "You are a helpful multilingual assistant."},
        {"role": "user", "content": "Translate 'hello' to Luganda."},
        {"role": "assistant", "content": "'Hello' is 'Gyebaleko'."},
        {"role": "user", "content": "And to Acholi?"},
    ],
}`;

const streamingCode = `stream = client.chat.completions.create(
    model="Sunbird/Sunflower-14B",
    messages=[{"role": "user", "content": "Tell me about Uganda."}],
    stream=True,
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)`;

const uploadCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Step 1: Generate upload URL
url = "https://api.sunbird.ai/tasks/generate-upload-url"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

data = {
    "file_name": "recording.wav",
    "content_type": "audio/wav"
}

response = requests.post(url, headers=headers, json=data)
result = response.json()

upload_url = result["upload_url"]
file_id = result["file_id"]

print(f"Upload URL: {upload_url}")
print(f"File ID: {file_id}")
print(f"Expires at: {result['expires_at']}")

# Step 2: Upload file directly to GCS
with open("/path/to/your/recording.wav", "rb") as f:
    upload_response = requests.put(
        upload_url,
        data=f,
        headers={"Content-Type": "audio/wav"}
    )

if upload_response.status_code == 200:
    print("File uploaded successfully!")`;

function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string>(ids[0] ?? '');

  useEffect(() => {
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);

    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0) {
          setActive(visible[0].target.id);
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] },
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [ids]);

  return active;
}

function SectionHeading({
  id,
  icon: Icon,
  part,
  title,
}: {
  id: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  part?: string;
  title: string;
}) {
  return (
    <div id={id} className="scroll-mt-24 mb-6">
      {part && (
        <div className="text-xs font-semibold tracking-widest uppercase text-primary-600 dark:text-primary-400 mb-2">
          {part}
        </div>
      )}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-900/20 flex items-center justify-center text-primary-600 dark:text-primary-400 shrink-0">
          <Icon size={20} />
        </div>
        <h2 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">{title}</h2>
      </div>
    </div>
  );
}

function InfoNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 p-4 my-4 rounded-xl border border-primary-200 dark:border-primary-900/40 bg-primary-50/60 dark:bg-primary-900/10 text-sm text-gray-700 dark:text-gray-200">
      <Info size={18} className="text-primary-600 dark:text-primary-400 shrink-0 mt-0.5" />
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xl font-semibold text-gray-900 dark:text-white mt-8 mb-3">{children}</h3>
  );
}

function MutedHeading({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-base font-semibold text-gray-800 dark:text-gray-100 mt-6 mb-2">
      {children}
    </h4>
  );
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-gray-700 dark:text-gray-300 leading-relaxed">{children}</p>
  );
}

function BulletList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="space-y-2 my-4">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2 text-gray-700 dark:text-gray-300">
          <span className="mt-2 w-1.5 h-1.5 rounded-full bg-primary-500 shrink-0" />
          <span className="leading-relaxed">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 rounded-md bg-gray-100 dark:bg-white/10 text-primary-700 dark:text-primary-300 text-[0.9em] font-mono">
      {children}
    </code>
  );
}

function Availability({ available, dagger = false }: { available: boolean; dagger?: boolean }) {
  if (!available) {
    return <X size={16} className="inline text-gray-300 dark:text-gray-600" aria-label="Not supported" />;
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-green-600 dark:text-green-400">
      <Check size={16} aria-label="Available" />
      {dagger && <sup className="text-amber-600 dark:text-amber-400">†</sup>}
    </span>
  );
}

export default function Tutorial() {
  const activeId = useActiveSection(sections.map((s) => s.id));

  return (
    <div className="min-h-screen bg-white dark:bg-black transition-colors duration-300 selection:bg-primary-500 selection:text-white flex flex-col">
      <Header />

      <main className="flex-1 pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          {/* Hero */}
          <div className="max-w-4xl mx-auto text-center mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 text-xs font-semibold tracking-wider uppercase mb-4">
              <Sparkles size={14} />
              Tutorial
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-gray-900 dark:text-white mb-4">
              Sunbird AI API Tutorial
            </h1>
            <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl mx-auto leading-relaxed">
              A comprehensive guide for using the Sunbird AI API with Python code samples — translate, transcribe,
              synthesize speech, and chat across 30+ African languages.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] gap-10">
            {/* Table of Contents */}
            <aside className="hidden lg:block">
              <nav className="sticky top-24 py-2">
                <div className="text-xs font-semibold tracking-widest uppercase text-gray-500 dark:text-gray-400 mb-3 px-3">
                  On this page
                </div>
                <ul className="space-y-1">
                  {sections.map((section) => {
                    const isActive = activeId === section.id;
                    return (
                      <li key={section.id}>
                        <a
                          href={`#${section.id}`}
                          className={`block px-3 py-2 rounded-lg text-sm transition-colors border-l-2 ${
                            isActive
                              ? 'border-primary-500 text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/10 font-medium'
                              : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-white/5'
                          }`}
                        >
                          {section.part && (
                            <span className="block text-[10px] font-semibold tracking-wider uppercase opacity-70">
                              {section.part}
                            </span>
                          )}
                          {section.label}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            </aside>

            {/* Content */}
            <article className="max-w-3xl space-y-16">
              {/* Overview */}
              <section>
                <SectionHeading id="overview" icon={Globe} title="Supported Languages" />
                <Paragraph>
                  Sunbird AI provides AI services across English and a growing catalog of African languages.
                  Languages are accepted as a 3-letter ISO code or a full language name; translation alone covers
                  32 languages.
                </Paragraph>
                <div className="flex flex-wrap gap-2 mt-6">
                  {supportedLanguages.map((lang) => (
                    <div
                      key={lang.code}
                      className="px-3 py-1.5 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-sm text-gray-800 dark:text-gray-100"
                    >
                      {lang.name}{' '}
                      <span className="text-gray-400 dark:text-gray-500 font-mono text-xs">({lang.code})</span>
                    </div>
                  ))}
                  <div className="px-3 py-1.5 rounded-full bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-900/40 text-sm text-primary-700 dark:text-primary-300 font-medium">
                    + 20 more
                  </div>
                </div>
              </section>

              {/* Language Support */}
              <section>
                <SectionHeading
                  id="language-support"
                  icon={ListChecks}
                  title="Language Support by Endpoint"
                />
                <Paragraph>
                  Which languages each task endpoint currently serves. <strong>Code</strong> is the canonical
                  ISO/SALT code the API accepts (full language names also work where an endpoint takes a{' '}
                  <InlineCode>language</InlineCode> or <InlineCode>voice</InlineCode>).{' '}
                  <InlineCode>/tasks/translate</InlineCode> shares the same 32-language set as{' '}
                  <InlineCode>/tasks/chat/completions</InlineCode>.
                </Paragraph>
                <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-white/10 my-4">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-white/5">
                      <tr>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Language
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Code
                        </th>
                        <th className="px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          <div className="text-center">Text-to-Speech</div>
                          <div className="text-center font-mono font-normal text-[11px] text-gray-400 dark:text-gray-500">
                            /tasks/audio/speech
                          </div>
                        </th>
                        <th className="px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          <div className="text-center">Speech-to-Text</div>
                          <div className="text-center font-mono font-normal text-[11px] text-gray-400 dark:text-gray-500">
                            /tasks/audio/transcriptions
                          </div>
                        </th>
                        <th className="px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          <div className="text-center">Chat</div>
                          <div className="text-center font-mono font-normal text-[11px] text-gray-400 dark:text-gray-500">
                            /tasks/chat/completions
                          </div>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {languageSupport.map((row, i) => (
                        <tr
                          key={row.code}
                          className={
                            i % 2 === 0
                              ? 'bg-white dark:bg-transparent'
                              : 'bg-gray-50/50 dark:bg-white/[0.02]'
                          }
                        >
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                            {row.name}
                          </td>
                          <td className="px-4 py-3 font-mono text-primary-700 dark:text-primary-400">
                            {row.code}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Availability available={row.speech} dagger={row.ttsVoiceless} />
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Availability available={row.transcription} />
                          </td>
                          <td className="px-4 py-3 text-center">
                            <Availability available={row.chat} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Paragraph>
                  <strong>†</strong> Lugbara, Sesotho, and Setswana are in the orpheus-3b-tts training mix but
                  currently expose no individual voice IDs, so synthesis depends on a future voice release.
                  Languages outside these sets (for example Zulu) are not yet served by any endpoint.
                </Paragraph>
              </section>

              {/* Part 1: Authentication */}
              <section>
                <SectionHeading id="authentication" icon={KeyRound} part="Part 1" title="Authentication" />

                <SubHeading>Creating an Account</SubHeading>
                <ol className="space-y-3 my-4 list-none counter-reset-item">
                  <li className="flex items-start gap-3 text-gray-700 dark:text-gray-300">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary-600 text-white text-xs font-semibold shrink-0">
                      1
                    </span>
                    <span className="leading-relaxed">
                      If you don't already have an account, create one at{' '}
                      <a
                        href="https://api.sunbird.ai/register"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-1"
                      >
                        api.sunbird.ai/register
                        <ExternalLink size={12} />
                      </a>
                    </span>
                  </li>
                  <li className="flex items-start gap-3 text-gray-700 dark:text-gray-300">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary-600 text-white text-xs font-semibold shrink-0">
                      2
                    </span>
                    <span className="leading-relaxed">
                      Go to the{' '}
                      <a
                        href="https://api.sunbird.ai/keys"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-1"
                      >
                        tokens page
                        <ExternalLink size={12} />
                      </a>{' '}
                      to get your access token / API key.
                    </span>
                  </li>
                </ol>

                <SubHeading>Using the Authentication API</SubHeading>

                <MutedHeading>Register a New User</MutedHeading>
                <CodeBlock code={registerCode} language="python" label="Python — register" />

                <MutedHeading>Get Access Token</MutedHeading>
                <CodeBlock code={tokenCode} language="python" label="Python — get token" />
              </section>

              {/* Part 2: Translation */}
              <section>
                <SectionHeading
                  id="translation"
                  icon={Languages}
                  part="Part 2"
                  title="Translation (Sunflower Model)"
                />
                <Paragraph>
                  Translate text between 32 Ugandan and East African languages using the Sunflower model.
                  Languages are accepted as ISO 639-3 codes (<InlineCode>lug</InlineCode>) or full names
                  (<InlineCode>Luganda</InlineCode>), case-insensitively, and translation works between{' '}
                  <strong>any pair</strong> of supported languages. <InlineCode>source_language</InlineCode> is
                  optional — when omitted, Sunflower infers it from the text.
                </Paragraph>
                <CodeBlock code={translateCode} language="python" label="Python — translate" />

                <MutedHeading>Optional source, full names</MutedHeading>
                <Paragraph>
                  <InlineCode>source_language</InlineCode> is optional, and full language names work too:
                </Paragraph>
                <CodeBlock code={translateFullNameCode} language="python" label="Python — target only" />

                <MutedHeading>Supported languages (ISO code → name)</MutedHeading>
                <CodeBlock
                  code={translationLanguageCodes}
                  language="python"
                  label="Python — language codes"
                />

                <MutedHeading>Response</MutedHeading>
                <Paragraph>The response shape is unchanged from the previous NLLB-backed endpoint:</Paragraph>
                <CodeBlock code={translateResponse} language="json" label="JSON — response" />
              </section>

              {/* Part 3: Speech-to-Text */}
              <section>
                <SectionHeading
                  id="speech-to-text"
                  icon={Mic}
                  part="Part 3"
                  title="Speech-to-Text (STT)"
                />
                <Paragraph>
                  Convert speech audio to text. The unified{' '}
                  <InlineCode>POST /tasks/audio/transcriptions</InlineCode> endpoint accepts an uploaded audio file
                  (or a GCS object) and routes to the Modal (Whisper large-v3) or RunPod backend. Supports MP3,
                  WAV, M4A, and more.
                </Paragraph>

                <InfoNote>
                  <strong>Migrating from the legacy STT routes?</strong> <InlineCode>/tasks/modal/stt</InlineCode>,{' '}
                  <InlineCode>/tasks/stt</InlineCode>, <InlineCode>/tasks/stt_from_gcs</InlineCode>, and{' '}
                  <InlineCode>/tasks/org/stt</InlineCode> are <strong>deprecated</strong> (they still work but
                  return <InlineCode>Deprecation</InlineCode>/<InlineCode>Sunset</InlineCode> headers). Switch to{' '}
                  <InlineCode>/tasks/audio/transcriptions</InlineCode>.
                </InfoNote>

                <SubHeading>Transcribe a file (Modal / Whisper)</SubHeading>
                <Paragraph>
                  <InlineCode>language</InlineCode> is <strong>required</strong>.{' '}
                  <InlineCode>platform</InlineCode> defaults to <InlineCode>modal</InlineCode> (Whisper large-v3).
                </Paragraph>
                <CodeBlock code={modalTranscribeCode} language="python" label="Python — Modal / Whisper" />

                <SubHeading>Transcribe with RunPod (adapter, Whisper, diarization)</SubHeading>
                <Paragraph>
                  The RunPod backend adds a language <InlineCode>adapter</InlineCode>, the{' '}
                  <InlineCode>whisper</InlineCode> flag, and optional speaker diarization
                  (<InlineCode>recognise_speakers</InlineCode>).
                </Paragraph>
                <CodeBlock code={runpodTranscribeCode} language="python" label="Python — RunPod" />
                <Paragraph>
                  You can also transcribe audio already in GCS by passing{' '}
                  <InlineCode>gcs_blob_name</InlineCode> (with <InlineCode>platform="runpod"</InlineCode>) instead
                  of an <InlineCode>audio</InlineCode> file — see <strong>Part 7: File Upload</strong> for
                  generating upload URLs.
                </Paragraph>

                <MutedHeading>Example response</MutedHeading>
                <CodeBlock code={transcribeResponse} language="json" label="JSON — response" />

                <MutedHeading>Supported languages</MutedHeading>
                <div className="flex flex-wrap gap-2 my-4">
                  {sttLanguages.map((l) => (
                    <div
                      key={l.code}
                      className="px-3 py-1 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-xs text-gray-800 dark:text-gray-100"
                    >
                      {l.name} <span className="text-gray-400 font-mono">({l.code})</span>
                    </div>
                  ))}
                </div>

                <InfoNote>
                  <strong>Note:</strong> For files larger than 100MB, only the first 10 minutes will be
                  transcribed.
                </InfoNote>

                <Paragraph>
                  The dictionary below represents the language codes available now for the STT endpoint:
                </Paragraph>
                <CodeBlock code={saltWhisperCode} language="python" label="Python — Whisper language IDs" />
              </section>

              {/* Part 4: Language Detection */}
              <section>
                <SectionHeading
                  id="language-detection"
                  icon={Radio}
                  part="Part 4"
                  title="Language Detection"
                />
                <Paragraph>
                  Automatically detect the language of text input. Useful for routing text to appropriate
                  translation or processing pipelines.
                </Paragraph>
                <CodeBlock code={languageDetectCode} language="python" label="Python — language ID" />

                <MutedHeading>Supported Languages</MutedHeading>
                <Paragraph>Acholi, Ateso, English, Luganda, Lugbara, Runyankole.</Paragraph>
              </section>

              {/* Part 5: TTS */}
              <section>
                <SectionHeading
                  id="text-to-speech"
                  icon={Volume2}
                  part="Part 5"
                  title="Text-to-Speech (TTS)"
                />
                <Paragraph>
                  Synthesize speech from text. The unified <InlineCode>POST /tasks/audio/speech</InlineCode>{' '}
                  endpoint replaces <InlineCode>/tasks/modal/tts</InlineCode>,{' '}
                  <InlineCode>/tasks/runpod/tts</InlineCode>, and{' '}
                  <InlineCode>/tasks/modal/orpheus/tts</InlineCode>. Two models are available:
                </Paragraph>
                <BulletList
                  items={[
                    <>
                      <InlineCode>orpheus-3b-tts</InlineCode> (default) — multilingual, multi-speaker; voices are
                      catalog tags (e.g. <InlineCode>salt_lug_0001</InlineCode>). List them with{' '}
                      <InlineCode>GET /tasks/voice/speakers</InlineCode>.
                    </>,
                    <>
                      <InlineCode>spark-tts</InlineCode> — the six fixed Ugandan voices below; supports streaming
                      on Modal.
                    </>,
                  ]}
                />

                <InfoNote>
                  <strong>Migrating?</strong> The legacy TTS, streaming (<InlineCode>/stream</InlineCode>,{' '}
                  <InlineCode>/stream-with-url</InlineCode>), Orpheus batch, speaker-listing, and{' '}
                  <InlineCode>refresh-url</InlineCode> endpoints are <strong>deprecated</strong>. Use the unified
                  endpoints below.
                </InfoNote>

                <SubHeading>Single synthesis (orpheus-3b-tts, default)</SubHeading>
                <CodeBlock code={orpheusTtsCode} language="python" label="Python — orpheus-3b-tts" />

                <MutedHeading>orpheus-3b-tts: languages covered</MutedHeading>
                <Paragraph>
                  Speaker IDs encode both the source corpus (<InlineCode>salt_*</InlineCode>,{' '}
                  <InlineCode>waxal_*</InlineCode>, <InlineCode>slr32_*</InlineCode>,{' '}
                  <InlineCode>slr129_*</InlineCode>, <InlineCode>bateesa_*</InlineCode>) and the language.
                  Languages shown with an em dash in the Speaker IDs column are present in the model's training
                  mix but do not currently expose individual voice IDs in this checkpoint.
                </Paragraph>
                <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-white/10 my-4">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-white/5">
                      <tr>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Config
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Language
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          ISO 639-1
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Region
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Speaker IDs
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {orpheusLanguages.map((row, i) => (
                        <tr
                          key={row.config}
                          className={
                            i % 2 === 0
                              ? 'bg-white dark:bg-transparent'
                              : 'bg-gray-50/50 dark:bg-white/[0.02]'
                          }
                        >
                          <td className="px-4 py-3 align-top font-mono text-primary-700 dark:text-primary-400">
                            {row.config}
                          </td>
                          <td className="px-4 py-3 align-top text-gray-700 dark:text-gray-300 whitespace-nowrap">
                            {row.language}
                          </td>
                          <td className="px-4 py-3 align-top font-mono text-gray-500 dark:text-gray-400">
                            {row.iso}
                          </td>
                          <td className="px-4 py-3 align-top text-gray-600 dark:text-gray-400">{row.region}</td>
                          <td className="px-4 py-3 align-top text-gray-700 dark:text-gray-300">
                            {row.speakers.length === 0 ? (
                              <span className="text-gray-400 dark:text-gray-500">—</span>
                            ) : (
                              <div className="flex flex-wrap gap-1">
                                {row.speakers.map((s) => (
                                  <code
                                    key={s}
                                    className="px-1.5 py-0.5 rounded-md bg-gray-100 dark:bg-white/10 text-primary-700 dark:text-primary-300 text-xs font-mono"
                                  >
                                    {s}
                                  </code>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Paragraph>
                  Per-language quality scales with the amount of training data Sunbird collected for that
                  language. Audition the voices for each language before relying on a particular speaker — use the
                  discovery snippet under <strong>Listing voices</strong> below.
                </Paragraph>

                <SubHeading>Single synthesis (spark-tts, fixed voices)</SubHeading>
                <CodeBlock code={sparkTtsCode} language="python" label="Python — spark-tts" />

                <MutedHeading>spark-tts voices</MutedHeading>
                <div className="overflow-hidden rounded-2xl border border-gray-200 dark:border-white/10 my-4">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-white/5">
                      <tr>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Voice name
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          ID
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Description
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sparkVoices.map((s, i) => (
                        <tr
                          key={s.id}
                          className={
                            i % 2 === 0
                              ? 'bg-white dark:bg-transparent'
                              : 'bg-gray-50/50 dark:bg-white/[0.02]'
                          }
                        >
                          <td className="px-4 py-3 font-mono text-primary-700 dark:text-primary-400">
                            {s.name}
                          </td>
                          <td className="px-4 py-3 font-mono text-gray-700 dark:text-gray-300">{s.id}</td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.description}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <SubHeading>Response Modes</SubHeading>
                <Paragraph>
                  <InlineCode>response_mode</InlineCode> applies to <strong>spark-tts on Modal</strong>:
                </Paragraph>
                <BulletList
                  items={responseModes.map((r) => (
                    <>
                      <InlineCode>{r.mode}</InlineCode> — {r.description}
                    </>
                  ))}
                />

                <SubHeading>Listing voices</SubHeading>
                <CodeBlock code={listVoicesCode} language="python" label="Python — list voices" />

                <SubHeading>Batch synthesis (orpheus-3b-tts)</SubHeading>
                <Paragraph>Synthesize up to 128 items in a single request:</Paragraph>
                <CodeBlock code={batchTtsCode} language="python" label="Python — batch" />

                <SubHeading>Refreshing an expired URL</SubHeading>
                <Paragraph>
                  Signed URLs expire after ~30 minutes. Re-sign a stored object with{' '}
                  <InlineCode>GET /tasks/audio/speech/url</InlineCode>:
                </Paragraph>
                <CodeBlock code={refreshUrlCode} language="python" label="Python — refresh URL" />

                <MutedHeading>Example response (POST /tasks/audio/speech)</MutedHeading>
                <CodeBlock code={ttsResponse} language="json" label="JSON — response" />
              </section>

              {/* Part 6: Conversational AI */}
              <section>
                <SectionHeading
                  id="conversational-ai"
                  icon={MessageSquare}
                  part="Part 6"
                  title="Conversational AI (Sunflower)"
                />
                <Paragraph>
                  The Sunflower model provides conversational AI for 20+ Ugandan languages through an
                  OpenAI-compatible endpoint: <InlineCode>POST /tasks/chat/completions</InlineCode>. The request
                  and response formats mirror the OpenAI Chat Completions API, so you can move between the OpenAI
                  API and the Sunbird API by changing only the base URL and API key.
                </Paragraph>

                <InfoNote>
                  <strong>Deprecated:</strong> <InlineCode>POST /tasks/sunflower_inference</InlineCode> and{' '}
                  <InlineCode>POST /tasks/sunflower_simple</InlineCode> are deprecated and will be removed in a
                  future release. Use <InlineCode>POST /tasks/chat/completions</InlineCode> instead — a single
                  instruction is just a request with one user message.
                </InfoNote>

                <SubHeading>Chat Completion</SubHeading>
                <CodeBlock code={chatCompletionCode} language="python" label="Python — chat completions" />

                <MutedHeading>Example Response</MutedHeading>
                <CodeBlock code={chatCompletionResponse} language="json" label="JSON — response" />

                <SubHeading>Using the OpenAI SDK</SubHeading>
                <Paragraph>
                  Because the endpoint is OpenAI-compatible, the official OpenAI Python SDK works out of the box:
                </Paragraph>
                <CodeBlock code={openaiSdkCode} language="python" label="Python — OpenAI SDK" />

                <SubHeading>Multi-turn Conversations</SubHeading>
                <Paragraph>
                  Maintain context by sending the running message history. You can also set a custom{' '}
                  <InlineCode>system</InlineCode> message (when omitted, a default Sunflower system message is
                  applied):
                </Paragraph>
                <CodeBlock code={multiTurnCode} language="python" label="Python — multi-turn" />

                <SubHeading>Streaming</SubHeading>
                <Paragraph>
                  Set <InlineCode>"stream": true</InlineCode> to receive Server-Sent Events in OpenAI{' '}
                  <InlineCode>chat.completion.chunk</InlineCode> format, terminated by{' '}
                  <InlineCode>data: [DONE]</InlineCode>. With the OpenAI SDK:
                </Paragraph>
                <CodeBlock code={streamingCode} language="python" label="Python — streaming" />

                <InfoNote>
                  Supported request parameters: <InlineCode>model</InlineCode> (only{' '}
                  <InlineCode>Sunbird/Sunflower-14B</InlineCode>), <InlineCode>messages</InlineCode>,{' '}
                  <InlineCode>temperature</InlineCode> (0.0–2.0, default 0.3), <InlineCode>max_tokens</InlineCode>,{' '}
                  <InlineCode>top_p</InlineCode>, <InlineCode>stop</InlineCode>, and{' '}
                  <InlineCode>stream</InlineCode>.
                </InfoNote>
              </section>

              {/* Part 7: File Upload */}
              <section>
                <SectionHeading
                  id="file-upload"
                  icon={Upload}
                  part="Part 7"
                  title="File Upload (Signed URLs)"
                />
                <Paragraph>
                  Generate secure signed URLs for direct client uploads to GCP Storage. Useful for uploading audio
                  files before transcription.
                </Paragraph>
                <CodeBlock code={uploadCode} language="python" label="Python — signed URL upload" />

                <MutedHeading>Features</MutedHeading>
                <BulletList items={uploadFeatures} />
              </section>

              {/* Resources */}
              <section>
                <SectionHeading id="resources" icon={FileText} title="Additional Resources" />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 my-4">
                  <a
                    href="https://docs.sunbird.ai/introduction"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group p-5 rounded-2xl bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 hover:border-primary-500 dark:hover:border-primary-500 transition-all hover:shadow-lg"
                  >
                    <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold mb-1">
                      <BookOpen size={18} className="text-primary-600 dark:text-primary-400" />
                      API Documentation
                      <ExternalLink
                        size={14}
                        className="text-gray-400 group-hover:text-primary-500 transition-colors"
                      />
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                      docs.sunbird.ai/introduction
                    </div>
                  </a>

                  <a
                    href="https://api.sunbird.ai/openapi.json"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group p-5 rounded-2xl bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 hover:border-primary-500 dark:hover:border-primary-500 transition-all hover:shadow-lg"
                  >
                    <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold mb-1">
                      <FileText size={18} className="text-primary-600 dark:text-primary-400" />
                      OpenAPI Specification
                      <ExternalLink
                        size={14}
                        className="text-gray-400 group-hover:text-primary-500 transition-colors"
                      />
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                      api.sunbird.ai/openapi.json
                    </div>
                  </a>

                  <a
                    href="https://docs.sunbird.ai/api-reference/introduction"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group p-5 rounded-2xl bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 hover:border-primary-500 dark:hover:border-primary-500 transition-all hover:shadow-lg"
                  >
                    <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold mb-1">
                      <Sparkles size={18} className="text-primary-600 dark:text-primary-400" />
                      Usage Guide
                      <ExternalLink
                        size={14}
                        className="text-gray-400 group-hover:text-primary-500 transition-colors"
                      />
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400 font-mono">docs.sunbird.ai/api-reference/introduction</div>
                  </a>

                  <a
                    href="https://github.com/SunbirdAI/sunbird-ai-api/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group p-5 rounded-2xl bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 hover:border-primary-500 dark:hover:border-primary-500 transition-all hover:shadow-lg"
                  >
                    <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold mb-1">
                      <MessageSquare size={18} className="text-primary-600 dark:text-primary-400" />
                      Feedback & Issues
                      <ExternalLink
                        size={14}
                        className="text-gray-400 group-hover:text-primary-500 transition-colors"
                      />
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                      github.com/SunbirdAI
                    </div>
                  </a>
                </div>

                <SubHeading>Rate Limiting</SubHeading>
                <Paragraph>
                  API endpoints are rate-limited to ensure fair usage. If you need higher rate limits for
                  production use, please contact the Sunbird AI team.
                </Paragraph>

                <SubHeading>Feedback and Questions</SubHeading>
                <Paragraph>
                  Don't hesitate to leave us any feedback or questions by opening an{' '}
                  <a
                    href="https://github.com/SunbirdAI/sunbird-ai-api/issues"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 dark:text-primary-400 hover:underline"
                  >
                    issue on GitHub
                  </a>
                  .
                </Paragraph>
              </section>

              {/* Footer CTA */}
              <section className="mt-16 p-8 rounded-3xl bg-gradient-to-br from-primary-50 to-primary-100/40 dark:from-primary-900/20 dark:to-primary-900/5 border border-primary-200 dark:border-primary-900/40">
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                  Ready to build?
                </h3>
                <p className="text-gray-700 dark:text-gray-300 mb-5">
                  Get your access token and start calling the Sunbird AI API in minutes.
                </p>
                <div className="flex flex-col sm:flex-row gap-3">
                  <Link
                    to="/register"
                    className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary-600 hover:bg-primary-700 text-white font-semibold transition-all shadow-lg shadow-primary-500/20"
                  >
                    Create Account
                    <ArrowRight size={18} />
                  </Link>
                  <Link
                    to="/keys"
                    className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 border border-gray-200 dark:border-white/10 text-gray-900 dark:text-white font-semibold transition-all"
                  >
                    <KeyRound size={18} />
                    Get API Keys
                  </Link>
                </div>
              </section>
            </article>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
