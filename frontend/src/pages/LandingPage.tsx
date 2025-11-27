import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen, Terminal, Activity, Key } from 'lucide-react';
import { motion } from 'framer-motion';
import Header from '../components/Header';
import Footer from '../components/Footer';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-black transition-colors duration-300 selection:bg-primary-500 selection:text-white">
      <Header />

      {/* Hero Section */}
      <div className="relative pt-32 pb-16 sm:pt-40 sm:pb-24 lg:pb-32 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center overflow-hidden">
        {/* Background Gradients */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-full max-w-7xl pointer-events-none">
          <div className="absolute top-20 left-10 w-72 h-72 bg-primary-500/10 rounded-full blur-3xl mix-blend-multiply dark:mix-blend-screen animate-blob" />
          <div className="absolute top-20 right-10 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl mix-blend-multiply dark:mix-blend-screen animate-blob animation-delay-2000" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1 className="relative text-4xl sm:text-5xl lg:text-7xl font-extrabold tracking-tight text-gray-900 dark:text-white mb-6">
            Welcome to the <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-primary-500 to-orange-600 bg-clip-text text-transparent">Sunbird AI API</span>
          </h1>
          <p className="relative text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Get started with African language AI models. Translate, transcribe, and synthesize speech with state-of-the-art models designed for the continent.
          </p>
          <div className="relative flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/register" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-primary-600 hover:bg-primary-700 text-white font-semibold text-lg transition-all shadow-xl shadow-primary-500/20 hover:shadow-primary-500/30 flex items-center justify-center gap-2">
              Get Started
              <ArrowRight size={20} />
            </Link>
            <a href="https://sunbirdai.mintlify.app" target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto px-8 py-4 rounded-xl bg-white dark:bg-secondary hover:bg-gray-50 dark:hover:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-900 dark:text-white font-semibold text-lg transition-all backdrop-blur-sm flex items-center justify-center gap-2">
              <BookOpen size={20} />
              Read Docs
            </a>
          </div>
        </motion.div>
      </div>

      {/* What You Can Build Section */}
      <div className="px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto pb-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-4">
            What You Can Build
          </h2>
          <p className="text-lg text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
            Powerful AI capabilities for African languages at your fingertips
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <a 
            href="https://sunbirdai.mintlify.app/guides/translation" 
            target="_blank" 
            rel="noopener noreferrer"
            className="group p-8 rounded-2xl bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/20 dark:to-purple-950/20 border border-indigo-100 dark:border-indigo-900/20 hover:border-indigo-300 dark:hover:border-indigo-700/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-indigo-900/20 hover:-translate-y-1"
          >
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Translate Content</h3>
            <p className="text-gray-600 dark:text-gray-400">
              Translate text between English and 5+ local Ugandan languages with high accuracy.
            </p>
          </a>

          <a 
            href="https://sunbirdai.mintlify.app/guides/speech-to-text" 
            target="_blank" 
            rel="noopener noreferrer"
            className="group p-8 rounded-2xl bg-gradient-to-br from-blue-50 to-cyan-50 dark:from-blue-950/20 dark:to-cyan-950/20 border border-blue-100 dark:border-blue-900/20 hover:border-blue-300 dark:hover:border-blue-700/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-blue-900/20 hover:-translate-y-1"
          >
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Transcribe Audio</h3>
            <p className="text-gray-600 dark:text-gray-400">
              Convert speech audio into text for captioning, logging, or analysis.
            </p>
          </a>

          <a 
            href="https://sunbirdai.mintlify.app/guides/text-to-speech" 
            target="_blank" 
            rel="noopener noreferrer"
            className="group p-8 rounded-2xl bg-gradient-to-br from-orange-50 to-red-50 dark:from-orange-950/20 dark:to-red-950/20 border border-orange-100 dark:border-orange-900/20 hover:border-orange-300 dark:hover:border-orange-700/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-orange-900/20 hover:-translate-y-1"
          >
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-orange-500 to-red-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Generate Speech</h3>
            <p className="text-gray-600 dark:text-gray-400">
              Turn text into natural-sounding speech in local languages.
            </p>
          </a>

          <a 
            href="https://sunbirdai.mintlify.app/guides/sunflower-chat" 
            target="_blank" 
            rel="noopener noreferrer"
            className="group p-8 rounded-2xl bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-950/20 dark:to-emerald-950/20 border border-green-100 dark:border-green-900/20 hover:border-green-300 dark:hover:border-green-700/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-green-900/20 hover:-translate-y-1"
          >
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-green-500 to-emerald-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Conversational AI</h3>
            <p className="text-gray-600 dark:text-gray-400">
              Build chatbots that understand and respond in local cultural contexts.
            </p>
          </a>
        </div>
      </div>

      {/* Supported Languages Section */}
      <div className="px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto pb-16">
        <div className="text-center mb-8">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-4">
            Supported Languages
          </h2>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            We support translation between English and these Ugandan languages
          </p>
        </div>

        <div className="flex flex-wrap justify-center gap-4">
          {['Luganda', 'Acholi', 'Ateso', 'Lugbara', 'Runyankole'].map((lang) => (
            <div 
              key={lang}
              className="px-6 py-3 rounded-full bg-white dark:bg-white/5 border border-gray-200 dark:border-white/5 text-gray-900 dark:text-white font-medium hover:border-primary-500 dark:hover:border-primary-500/50 transition-colors shadow-sm dark:shadow-md dark:shadow-black/20"
            >
              {lang}
            </div>
          ))}
        </div>

        <div className="text-center mt-6">
          <a 
            href="https://sunbirdai.mintlify.app/languages" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium inline-flex items-center gap-2"
          >
            View all supported languages
            <ArrowRight size={16} />
          </a>
        </div>
      </div>

      {/* Quick Start Section */}
      <div className="px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto pb-24">
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 dark:text-white mb-4">
            Get Started in Minutes
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <a href="https://github.com/SunbirdAI/sunbird-ai-api/blob/main/tutorial.md" target="_blank" rel="noopener noreferrer" className="group p-6 rounded-2xl bg-white dark:bg-white/5 border border-gray-100 dark:border-white/5 hover:border-primary-500 dark:hover:border-primary-500/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-black/20 hover:-translate-y-1 backdrop-blur-sm">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
                <BookOpen size={24} />
              </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Tutorial</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">Learn how to use the API with step-by-step guides and best practices.</p>
          </a>

          <a href="https://github.com/SunbirdAI/translation-api-examples" target="_blank" rel="noopener noreferrer" className="group p-6 rounded-2xl bg-white dark:bg-white/5 border border-gray-100 dark:border-white/5 hover:border-primary-500 dark:hover:border-primary-500/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-black/20 hover:-translate-y-1 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <Terminal size={24} />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Examples</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">View code examples and SDK usage on GitHub for Python and JS.</p>
          </a>

          <Link to="/login" className="group p-6 rounded-2xl bg-white dark:bg-white/5 border border-gray-100 dark:border-white/5 hover:border-primary-500 dark:hover:border-primary-500/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-black/20 hover:-translate-y-1 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-red-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <Activity size={24} />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Usage Stats</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">Monitor your API usage, request volume, and limits in real-time.</p>
          </Link>

          <Link to="/login" className="group p-6 rounded-2xl bg-white dark:bg-white/5 border border-gray-100 dark:border-white/5 hover:border-primary-500 dark:hover:border-primary-500/50 transition-all hover:shadow-xl dark:shadow-lg dark:shadow-black/20 hover:-translate-y-1 backdrop-blur-sm">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500 to-emerald-500 flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform shadow-lg">
              <Key size={24} />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">API Tokens</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm leading-relaxed">Manage your access tokens and security keys securely.</p>
          </Link>
        </div>
      </div>

      <Footer />
    </div>
  );
}
