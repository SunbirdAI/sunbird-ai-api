import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BookOpen,
  ExternalLink,
  FileText,
  Globe,
  Info,
  KeyRound,
  Languages,
  Mic,
  MessageSquare,
  Radio,
  Sparkles,
  Upload,
  Volume2,
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

const translationPairs = [
  'English ↔ Acholi',
  'English ↔ Ateso',
  'English ↔ Luganda',
  'English ↔ Lugbara',
  'English ↔ Runyankole',
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

const speakerVoices = [
  { id: 241, voice: 'Acholi (female)' },
  { id: 242, voice: 'Ateso (female)' },
  { id: 243, voice: 'Runyankore (female)' },
  { id: 245, voice: 'Lugbara (female)' },
  { id: 246, voice: 'Swahili (male)' },
  { id: 248, voice: 'Luganda (female)' },
];

const responseModes = [
  { mode: 'url', description: 'Generate audio, upload to GCP, return signed URL (valid for 30 minutes)' },
  { mode: 'stream', description: 'Stream raw audio chunks directly' },
  { mode: 'both', description: 'Stream audio AND return final signed URL' },
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

const translationLanguageCodes = `language_codes: {
    "English": "eng",
    "Luganda": "lug",
    "Runyankole": "nyn",
    "Acholi": "ach",
    "Ateso": "teo",
    "Lugbara": "lgg"
}`;

const modalSttCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/modal/stt"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

# Replace with your audio file path
audio_file_path = "/path/to/audio_file.wav"

files = {
    "audio": (
        "recording.wav",
        open(audio_file_path, "rb"),
        "audio/wav",
    ),
}

# Without language (auto-detect)
response = requests.post(url, headers=headers, files=files)
result = response.json()
print(f"Transcription: {result['audio_transcription']}")`;

const modalSttWithLangCode = `files = {
    "audio": (
        "recording.wav",
        open(audio_file_path, "rb"),
        "audio/wav",
    ),
}

# Using a 3-letter code
data = {"language": "lug"}
response = requests.post(url, headers=headers, files=files, data=data)

# Or using a full language name
data = {"language": "Luganda"}
response = requests.post(url, headers=headers, files=files, data=data)`;

const runpodSttCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/stt"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
}

# Replace with your audio file path
audio_file_path = "/path/to/audio_file.mp3"

files = {
    "audio": (
        "recording.mp3",
        open(audio_file_path, "rb"),
        "audio/mpeg",
    ),
}

data = {
    "language": "lug",  # Language code (eng, ach, teo, lug, lgg, nyn)
    "adapter": "lug",   # Model adapter to use
    "whisper": True,    # Use Whisper model
}

response = requests.post(url, headers=headers, files=files, data=data)
print(response.json())`;

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

const ttsCode = `import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.sunbird.ai/tasks/modal/tts"
access_token = os.getenv("AUTH_TOKEN")

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

payload = {
    "response_mode": "url",
    "speaker_id": 248,
    "text": "I am a nurse who takes care of many people.",
}

response = requests.post(url, headers=headers, json=payload)

print(response.status_code)
print(response.json())`;

const ttsResponse = `{
  "success": true,
  "audio_url": "https://storage.googleapis.com/sb-asr-audio-content-sb-gcp-project-01/tts_audio/20260212_222936_2a9f1f83_da308cdb.wav?...",
  "expires_at": "2026-02-12T22:59:36.954061Z",
  "file_name": "tts_audio/20260212_222936_2a9f1f83_da308cdb.wav",
  "duration_estimate_seconds": 4,
  "text_length": 43,
  "speaker_id": 248,
  "speaker_name": "Luganda (female)"
}`;

const sunflowerChatCode = `import requests

url = "https://api.sunbird.ai/tasks/sunflower_inference"

headers = {
    "accept": "application/json",
    "Authorization": "Bearer <your-access-token>",
    "Content-Type": "application/json",
}

payload = {
    "messages": [
        {
            "role": "user",
            "content": "Good morning, what is weather today?",
        }
    ],
    "model_type": "qwen",
    "temperature": 0.3,
    "stream": False,
    "system_message": "string",
}

response = requests.post(url, headers=headers, json=payload)

print(response.status_code)
print(response.json())`;

const sunflowerChatResponse = `{
  "content": "I'm glad you're up! While I can't provide real-time weather updates, I can help you understand how to interpret weather forecasts or explain common weather patterns in Uganda. Could you share the current weather conditions you're experiencing?",
  "model_type": "qwen",
  "usage": {
    "completion_tokens": 47,
    "prompt_tokens": 22,
    "total_tokens": 69
  },
  "processing_time": 4.802350997924805,
  "inference_time": 4.792236804962158,
  "message_count": 2
}`;

const sunflowerSimpleCode = `import requests

url = "https://api.sunbird.ai/tasks/sunflower_simple"

headers = {
    "accept": "application/json",
    "Authorization": "Bearer <your-access-token>",
}

data = {
    "instruction": "translate from english to luganda: i am very hungry they should serve food in time",
    "model_type": "qwen",
    "temperature": "0.1",
    "system_message": "",
}

response = requests.post(url, headers=headers, data=data)

print(response.status_code)
print(response.json())`;

const sunflowerSimpleResponse = `{
  "response": "Ndi muyala nnyo, emmere erina okugabibwa mu budde.",
  "model_type": "qwen",
  "processing_time": 3.2431752681732178,
  "usage": {
    "completion_tokens": 19,
    "prompt_tokens": 54,
    "total_tokens": 73
  },
  "success": true
}`;

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
              synthesize speech, and chat in 25+ African languages.
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
                  Sunbird AI provides AI services across English and a growing catalog of African languages. The
                  endpoints below accept a 3-letter ISO code to target a specific language.
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
                  title="Translation (NLLB Model)"
                />
                <Paragraph>
                  Translate text between English and local languages using the NLLB model. Supports bidirectional
                  translation.
                </Paragraph>
                <CodeBlock code={translateCode} language="python" label="Python — translate" />

                <MutedHeading>Supported Language Pairs</MutedHeading>
                <BulletList items={translationPairs} />

                <Paragraph>
                  The dictionary below represents the language codes available now for the translate endpoint:
                </Paragraph>
                <CodeBlock
                  code={translationLanguageCodes}
                  language="python"
                  label="Python — language codes"
                />
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
                  Convert speech audio to text for supported languages. The API supports various audio formats
                  including MP3, WAV, and M4A.
                </Paragraph>

                <SubHeading>Modal STT (Recommended)</SubHeading>
                <Paragraph>
                  The Modal-based STT endpoint uses the Whisper large-v3 model for high-quality transcription.
                  Simply upload an audio file and get the transcription back. You can optionally specify a{' '}
                  <InlineCode>language</InlineCode> to improve accuracy; if omitted the model auto-detects the
                  language.
                </Paragraph>
                <CodeBlock code={modalSttCode} language="python" label="Python — Modal STT" />

                <MutedHeading>Specifying a language</MutedHeading>
                <Paragraph>
                  Pass a <InlineCode>language</InlineCode> field to guide the model. Accepts either a 3-letter ISO
                  639-2 code or a full language name (case-insensitive).
                </Paragraph>
                <CodeBlock code={modalSttWithLangCode} language="python" label="Python — with language" />

                <MutedHeading>Supported languages</MutedHeading>
                <div className="flex flex-wrap gap-2 my-4">
                  {sttLanguages.slice(0, 10).map((l) => (
                    <div
                      key={l.code}
                      className="px-3 py-1 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-xs text-gray-800 dark:text-gray-100"
                    >
                      {l.name} <span className="text-gray-400 font-mono">({l.code})</span>
                    </div>
                  ))}
                </div>

                <SubHeading>RunPod STT (with language selection)</SubHeading>
                <Paragraph>
                  The RunPod-based STT endpoint allows you to specify a target language and adapter for
                  transcription.
                </Paragraph>
                <CodeBlock code={runpodSttCode} language="python" label="Python — RunPod STT" />

                <MutedHeading>Supported Languages</MutedHeading>
                <Paragraph>
                  English, Acholi, Ateso, Luganda, Lugbara, Runyankole, Lusoga, Rutooro, Lumasaba, Kinyarwanda,
                  Swahili.
                </Paragraph>

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
                  Convert text to audio using Ugandan language voices. The API supports multiple response modes
                  including streaming and signed URLs.
                </Paragraph>
                <CodeBlock code={ttsCode} language="python" label="Python — TTS" />

                <SubHeading>Speaker IDs</SubHeading>
                <div className="overflow-hidden rounded-2xl border border-gray-200 dark:border-white/10 my-4">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-white/5">
                      <tr>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Speaker ID
                        </th>
                        <th className="text-left px-4 py-3 font-semibold text-gray-700 dark:text-gray-200">
                          Voice
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {speakerVoices.map((s, i) => (
                        <tr
                          key={s.id}
                          className={
                            i % 2 === 0
                              ? 'bg-white dark:bg-transparent'
                              : 'bg-gray-50/50 dark:bg-white/[0.02]'
                          }
                        >
                          <td className="px-4 py-3 font-mono text-primary-700 dark:text-primary-400">
                            {s.id}
                          </td>
                          <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{s.voice}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <SubHeading>Response Modes</SubHeading>
                <BulletList
                  items={responseModes.map((r) => (
                    <>
                      <InlineCode>{r.mode}</InlineCode> — {r.description}
                    </>
                  ))}
                />

                <MutedHeading>Example Response</MutedHeading>
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
                  The Sunflower model provides conversational AI capabilities with support for chat history and
                  context. Supports 20+ Ugandan languages.
                </Paragraph>

                <SubHeading>Chat with History</SubHeading>
                <CodeBlock code={sunflowerChatCode} language="python" label="Python — sunflower chat" />

                <MutedHeading>Example Response</MutedHeading>
                <CodeBlock code={sunflowerChatResponse} language="json" label="JSON — response" />

                <SubHeading>Simple Text Generation</SubHeading>
                <CodeBlock
                  code={sunflowerSimpleCode}
                  language="python"
                  label="Python — sunflower simple"
                />

                <MutedHeading>Example Response</MutedHeading>
                <CodeBlock code={sunflowerSimpleResponse} language="json" label="JSON — response" />
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
