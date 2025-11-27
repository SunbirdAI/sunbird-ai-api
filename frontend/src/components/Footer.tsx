import { Link } from 'react-router-dom';
import { Github, Linkedin, Twitter, Mail } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8 mb-8">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2 font-bold text-xl text-gray-900 dark:text-white mb-4">
              <img src="/logo.png" className='w-8 h-8 object-cover' alt="Sunbird AI" />
              <span>Sunbird AI</span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 max-w-sm">
              Empowering African languages with state-of-the-art AI models for translation, transcription, and speech synthesis.
            </p>
            {/* Social Media Links */}
            <div className="flex gap-4">
              <a 
                href="https://twitter.com/sunbirdai" 
                target="_blank" 
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-gray-200 dark:bg-white/10 hover:bg-primary-500 dark:hover:bg-primary-500 text-gray-700 dark:text-gray-300 hover:text-white transition-colors"
                aria-label="Twitter"
              >
                <Twitter size={20} />
              </a>
              <a 
                href="https://github.com/SunbirdAI" 
                target="_blank" 
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-gray-200 dark:bg-white/10 hover:bg-primary-500 dark:hover:bg-primary-500 text-gray-700 dark:text-gray-300 hover:text-white transition-colors"
                aria-label="GitHub"
              >
                <Github size={20} />
              </a>
              <a 
                href="https://www.linkedin.com/company/sunbird-ai" 
                target="_blank" 
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-gray-200 dark:bg-white/10 hover:bg-primary-500 dark:hover:bg-primary-500 text-gray-700 dark:text-gray-300 hover:text-white transition-colors"
                aria-label="LinkedIn"
              >
                <Linkedin size={20} />
              </a>
              <a 
                href="mailto:info@sunbird.ai"
                className="p-2 rounded-lg bg-gray-200 dark:bg-white/10 hover:bg-primary-500 dark:hover:bg-primary-500 text-gray-700 dark:text-gray-300 hover:text-white transition-colors"
                aria-label="Email"
              >
                <Mail size={20} />
              </a>
            </div>
          </div>

          {/* Resources Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Resources</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://sunbirdai.mintlify.app" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Documentation
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/sunbird-ai-api" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  API Reference
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/translation-api-examples" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Code Examples
                </a>
              </li>
              <li>
                <a href="https://github.com/SunbirdAI/sunbird-ai-api/blob/main/tutorial.md" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Tutorial
                </a>
              </li>
            </ul>
          </div>

          {/* Products Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Products</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://sunflower.sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Sunflower
                </a>
              </li>
              <li>
                <Link to="/login" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Translation API
                </Link>
              </li>
              <li>
                <Link to="/login" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Speech API
                </Link>
              </li>
            </ul>
          </div>

          {/* Company Column */}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Company</h3>
            <ul className="space-y-3">
              <li>
                <a href="https://sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  About Us
                </a>
              </li>
              <li>
                <a href="https://sunbird.ai" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Blog
                </a>
              </li>
              <li>
                <Link to="/privacy-policy" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link to="/terms-of-service" className="text-sm text-gray-600 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-gray-200 dark:border-white/10">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              &copy; {new Date().getFullYear()} Sunbird AI. All rights reserved.
            </p>
            <div className="flex gap-6 text-sm text-gray-500 dark:text-gray-400">
              <a href="https://sunbird.ai" target="_blank" rel="noopener noreferrer" className="hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
                Made in Uganda 🇺🇬
              </a>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
